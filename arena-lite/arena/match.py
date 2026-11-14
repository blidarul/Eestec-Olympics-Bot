"""Runs one match (best-of-N + sudden death + tie-break) and writes the match JSON live.

See docs/ARCHITECTURE.md sections 4-6. Usage:

    doc = run_match(a, b, match_id="t1-r1-m1", picker=PoolPicker(seed, "t1-r1-m1", pool),
                    out_path=results/t1/matches/t1-r1-m1.json, log_dir=results/t1/logs)

The match JSON is rewritten (temp file + os.replace) after every step.
"""
from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import config, randomizer
from .chat import MatchChat, chat_text
from .protocol import EOF, INVALID, TIMEOUT, WRONG_TYPE, Bot, Reply


# --------------------------------------------------------------------- inputs
@dataclass
class Entrant:
    team: str
    name: str = ""
    image: str | None = None  # what `docker run` gets (digest ref preferred)
    cmd: str | list[str] | None = None  # local command instead of an image
    seed: int | None = None  # bracket seed, 1 = best
    env: dict[str, str] = field(default_factory=dict)  # extra / override env for the bot
    memory_dir: str | os.PathLike | None = None  # default memory/<team>
    network: str | None = config.NETWORK  # image mode only
    llm_base_url: str | None = None  # default: gateway URL for the mode
    labels: dict[str, str] = field(default_factory=dict)  # extra docker labels for its containers
    bot: Any = None  # an in-process player instead of a process (e.g. arena.human.HumanBot): no image, no cmd

    def __post_init__(self):
        if not self.name:
            self.name = self.team


class StaticKeys:
    """Key provider without a gateway: every bot gets the same static key, cost unknown."""

    def __init__(self, key: str | None = None, note: str = ""):
        if key is None:
            key = os.environ.get("ARENA_STATIC_LLM_KEY") or os.environ.get("LLM_API_KEY") or ""
        self.key = key
        self.note = note

    def acquire(self, team: str, match_id: str, model: str = config.MODEL) -> tuple[str, Any]:
        return self.key, None

    def release(self, handle: Any) -> float | None:
        return None


# Pickers: callable(game_index) -> (GameClass, randomizer.Pick)
class PoolPicker:
    """Tournament picks: seeded game + variant from a pool of game ids."""

    def __init__(self, tournament_seed: int, match_id: str, pool: list[str], registry=None):
        if registry is None:
            from . import registry as reg
            registry = reg.all_games()
        self.seed, self.match_id, self.pool, self.registry = tournament_seed, match_id, list(pool), registry
        missing = [g for g in self.pool if g not in registry]
        if missing:
            raise KeyError(f"unknown games in pool: {missing}")

    def __call__(self, index: int):
        pick = randomizer.pick_game(self.seed, self.match_id, index, self.pool, self.registry)
        return self.registry[pick.game_id], pick


class DuplicatePicker:
    """Duplicate boards (round robin): games 2k-1 and 2k are board k, the same game + variant; the
    match runner alternates seats, so the second game is the first with the seats swapped.

    The second game REPLAYS the first game's deal (same seed) only when the game is `duplicate_safe`
    (core.Game: nothing hidden, no hidden future randomness). A hidden-information game gets a FRESH
    deal for it (a different seed derived from the board), because the same warm container plays
    both games of the board and would remember the hidden cards, secrets or values of the first.
    Boards are drawn from the pool like PoolPicker draws games (no repeats within a cycle)."""

    def __init__(self, seed: int, match_id: str, pool: list[str], registry=None):
        if registry is None:
            from . import registry as reg
            registry = reg.all_games()
        self.seed, self.match_id, self.pool, self.registry = seed, match_id, list(pool), registry
        missing = [g for g in self.pool if g not in registry]
        if missing:
            raise KeyError(f"unknown games in pool: {missing}")

    @staticmethod
    def board_of(index: int) -> int:
        return (index + 1) // 2

    @staticmethod
    def replays(cls) -> bool:
        """May the second game of a board replay the first game's exact deal?"""
        return getattr(cls, "duplicate_safe", False) is True

    def fresh_seed(self, board: int, original: int) -> int:
        """The second game's seed on a hidden-information board: a pure function of (rr seed, match id,
        board), never equal to the first game's seed."""
        s = randomizer.derive_seed("fresh-deal", self.seed, self.match_id, board) % 2_147_483_647
        return s if s != original else (s + 1) % 2_147_483_647

    def __call__(self, index: int):
        board = self.board_of(index)
        pick = randomizer.pick_game(self.seed, self.match_id, board, self.pool, self.registry)
        cls = self.registry[pick.game_id]
        if index % 2 == 0 and not self.replays(cls):
            pick = dataclasses.replace(pick, game_seed=self.fresh_seed(board, pick.game_seed))
        return cls, pick

    def deal_of(self, index: int) -> str:
        """"first" (the board's first game), "replay" (the first game's exact deal, seats swapped) or
        "fresh" (same game and variant, seats swapped, a new deal)."""
        if index % 2 == 1:
            return "first"
        gid = randomizer.pick_game_id(self.seed, self.match_id, self.board_of(index), self.pool)
        return "replay" if self.replays(self.registry[gid]) else "fresh"

    def game_fields(self, index: int) -> dict:
        """Extra fields for the match file's game entry."""
        board = self.board_of(index)
        return {"board": board, "duplicate_of": None if index % 2 == 1 else index - 1, "deal": self.deal_of(index)}


class ListPicker:
    """Exhibition / practice picks: game i = games[(i-1) % len]; seeded variant."""

    def __init__(self, games: list, seed: int, match_id: str, registry=None):
        if registry is None and any(isinstance(g, str) for g in games):
            from . import registry as reg
            registry = reg.all_games()
        self.games = [registry[g] if isinstance(g, str) else g for g in games]
        if not self.games:
            raise ValueError("empty game list")
        self.seed, self.match_id = seed, match_id

    def __call__(self, index: int):
        cls = self.games[(index - 1) % len(self.games)]
        return cls, randomizer.pick_variant(self.seed, self.match_id, index, cls)


class FixedPicker:
    """Picks recorded by a stage draw: game i is `picks[i-1]` (1-based), with its variant and seed.

    A stage draw stores six slots per match (three regular games plus up to three sudden-death games).
    The match runner asks for index 1..6; the same draw is used by every replay and by both bots.
    """

    def __init__(self, picks: list[dict], registry=None, seed: int | None = None):
        if registry is None:
            from . import registry as reg
            registry = reg.all_games()
        if not picks:
            raise ValueError("empty stage draw")
        self.picks = [dict(p) for p in picks]
        self.registry = registry
        self.seed = seed
        self.match_id = None
        missing = [p.get("game_id") for p in self.picks if p.get("game_id") not in registry]
        if missing:
            raise KeyError(f"unknown games in stage draw: {missing}")

    def __call__(self, index: int):
        if index < 1 or index > len(self.picks):
            raise IndexError(f"{self.match_id or 'match'}: game {index} is outside the stage draw "
                             f"({len(self.picks)} slot(s))")
        p = self.picks[index - 1]
        cls = self.registry[p["game_id"]]
        pick = randomizer.Pick(game_id=p["game_id"], variant_index=int(p["variant_index"]),
                               variant=dict(p["variant"]), game_seed=int(p["seed"]))
        return cls, pick


# ------------------------------------------------------------------- helpers
def _parallel(calls: dict) -> dict:
    """Run callables concurrently (one thread each); returns {key: result}."""
    if len(calls) == 1:
        (k, fn), = calls.items()
        return {k: fn()}
    results: dict = {}
    errors: dict = {}

    def run(k, fn):
        try:
            results[k] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            errors[k] = exc

    threads = [threading.Thread(target=run, args=(k, fn), daemon=True) for k, fn in calls.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise next(iter(errors.values()))
    return results


def _num(x):
    return int(x) if float(x).is_integer() else float(x)


def _snap(game) -> dict:
    """Detached, JSON-safe copy of the spectator frame (games may return live lists)."""
    return json.loads(json.dumps(game.frame(), default=str))


_chat = chat_text  # backwards-compatible names (the chat lives in arena/chat.py)
_comment = chat_text


def turn_message(game, seat: int, *, game_index: int, turn: int, seconds, chat: list) -> dict:
    """The `turn` message for `seat` in the game's current state, exactly as bots receive it (the match
    runner and the prep's `sample_turn` both build it here). `turn` counts the game's decision steps
    from 1 (both seats share the count)."""
    return {"type": "turn", "game_index": game_index, "turn": turn, "observation": game.observation(seat),
            "legal_actions": game.legal_actions(seat), "seconds": seconds, "chat": chat}


# ------------------------------------------------------------------ tie-break
# A knockout match still level after best-of-N and sudden death is decided by these, in order (the same
# for every game; seeding and ranking play no part): fewer warnings, less thinking time, lower model
# cost, then a coin flip. The round robin (play_all) keeps draws as draws.
TIEBREAK_ORDER = ("warnings", "time", "cost", "lot")


def match_totals(doc: dict) -> dict[str, dict]:
    """Per team, over every game of the match (sudden death included):
    - "warnings": the warnings its bot received (each game's `warnings` count for the team's seat);
    - "time_ms": its total thinking time = the `ms` of every ACCEPTED answer of its bot: the `ready` of
      each game (a `study` entry without an error) plus every accepted action (a timeline `actions` entry
      with an action and no error; after a warning only the accepted retry is recorded, so the rejected
      answer adds nothing). Timeouts, crashes and rejected answers add nothing."""
    teams = [t for t in (doc.get("a"), doc.get("b")) if t]
    out = {t: {"warnings": 0, "time_ms": 0} for t in teams}
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)  # noqa: E731
    for g in doc.get("games") or []:
        if not isinstance(g, dict):
            continue
        for s, team in enumerate((g.get("seats") or [])[:2]):
            if team not in out:
                continue
            k = str(s)
            w = (g.get("warnings") or {}).get(k)
            if num(w):
                out[team]["warnings"] += int(w)
            st = (g.get("study") or {}).get(k)
            if isinstance(st, dict) and not st.get("error") and num(st.get("ms")):
                out[team]["time_ms"] += int(st["ms"])
            for step in g.get("timeline") or []:
                e = (step.get("actions") or {}).get(k) if isinstance(step, dict) else None
                if isinstance(e, dict) and e.get("action") is not None and not e.get("error") and num(e.get("ms")):
                    out[team]["time_ms"] += int(e["ms"])
    return out


def coin_flip(match_id: str, seed, teams) -> dict:
    """The last tie-break: a fair coin derived from the competition seed and the match id (a pure function:
    the same match always flips the same way). Heads = the team id first in alphabetical order."""
    heads, tails = sorted(teams)
    side = randomizer.derive_seed("tiebreak-coin", seed, match_id) % 2
    return {"result": "heads" if side == 0 else "tails", "heads": heads, "tails": tails,
            "winner": heads if side == 0 else tails}


def _cost_value(x) -> float | None:
    return round(float(x), 6) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def break_tie(a: str, b: str, totals: dict, costs: dict, coin: dict) -> tuple[str, str]:
    """(winner, decided_by) of a level knockout match: "warnings" (fewer warnings), "time" (less total
    thinking time), "cost" (lower model cost for the match; only when both costs are known), "lot" (the coin)."""
    wa, wb = totals[a]["warnings"], totals[b]["warnings"]
    if wa != wb:
        return (a if wa < wb else b), "warnings"
    ta, tb = totals[a]["time_ms"], totals[b]["time_ms"]
    if ta != tb:
        return (a if ta < tb else b), "time"
    ca, cb = _cost_value(costs.get(a)), _cost_value(costs.get(b))
    if ca is not None and cb is not None and ca != cb:
        return (a if ca < cb else b), "cost"
    return coin["winner"], "lot"


# bad answers to a `turn` that earn one warning (re-sent turn) before they lose the game
WARNABLE = (INVALID, WRONG_TYPE, "illegal", "missing")

_ERROR_WORDS = {TIMEOUT: "timed out", INVALID: "sent invalid JSON", WRONG_TYPE: "sent a wrong message type",
                EOF: "crashed (process exited)", "illegal": "made an illegal move",
                "missing": "sent no action"}


class MatchRunner:
    def __init__(self, a: Entrant, b: Entrant, *, match_id: str, picker: Callable,
                 out_path: str | os.PathLike, log_dir: str | os.PathLike | None = None,
                 tournament: str | None = None, round_no: int | None = None,
                 best_of: int = config.BEST_OF, max_sudden_death: int = config.MAX_SUDDEN_DEATH,
                 study: float = config.STUDY_SECONDS, move: float = config.MOVE_SECONDS,
                 keys=None, model: str = config.MODEL,
                 shutdown_grace: float = config.SHUTDOWN_GRACE, echo: Callable[[str], None] | None = None,
                 extra: dict | None = None, play_all: bool = False, pool=None,
                 warm_study: float = config.WARM_STUDY_SECONDS, clocks: dict[str, dict] | None = None):
        """play_all: play all `best_of` games (no early stop, no sudden death); a tied match is a
        draw (winner None, decided_by "draw"). Used by the round robin.

        Otherwise a match still level after `best_of` + sudden death is decided by the tie-break (after the
        keys are released, since the match cost is one of its steps): fewer warnings, less thinking time,
        lower cost, a coin flip (TIEBREAK_ORDER, `tiebreak` in the match file). Seeds play no part.

        pool (arena.warm.WarmPool): warm per-game containers. Each game is routed to the team's
        container for the drawn game (study clock `warm_study`); a team without a ready one gets a
        cold container for that game (study clock `study`), which the pool keeps afterwards. Without a
        pool each team has one container for the whole match (exhibitions, practice).

        clocks: per-seat clocks, {team id: {"study": seconds, "move": seconds | None}}; a key that is
        left out keeps the match's clock. "move": None = no move clock for that team (a person playing
        through arena.human.HumanBot): its `turn` messages carry "seconds": null and the wait is bounded
        only by the player's own idle limit (config.HUMAN_IDLE_SECONDS). Without `clocks` both teams
        play with `study` / `warm_study` / `move`, as before."""
        if a.team == b.team:
            raise ValueError("a match needs two different team ids")
        self.pool = pool
        self.warm_study = _num(warm_study)
        self.play_all = play_all
        if play_all:
            max_sudden_death = 0
        self.a, self.b = a, b
        self.side = {a.team: a, b.team: b}
        self.match_id = match_id
        self.picker = picker
        self.out_path = Path(out_path)
        self.log_dir = Path(log_dir) if log_dir else self.out_path.parent.parent / "logs"
        self.best_of = best_of
        self.max_sd = max_sudden_death
        self.study = _num(study)
        self.move = _num(move)
        # per-seat clocks: the move clock of each team (None = no clock) and a fixed study clock, if any
        self.move_of: dict[str, Any] = {a.team: self.move, b.team: self.move}
        self.study_fixed: dict[str, Any] = {}
        for team, c in (clocks or {}).items():
            if team not in self.move_of:
                raise ValueError(f"clocks: {team!r} is not in this match")
            if "move" in c:
                self.move_of[team] = None if c["move"] is None else _num(c["move"])
            if c.get("study") is not None:
                self.study_fixed[team] = _num(c["study"])
        self.tournament = tournament
        self.keys = keys or StaticKeys()
        self.model = model
        self.grace = shutdown_grace
        self.echo = echo or (lambda s: None)
        self.coin_seed = getattr(picker, "seed", None)  # the competition seed (tie-break coin), when the picker has one
        self.score = {a.team: 0.0, b.team: 0.0}
        self.bots: dict[str, Bot] = {}  # the container playing the current game, per team
        self.keyof: dict[str, str] = {}  # this match's LLM key per team
        self.held: dict[str, Any] = {}  # pool mode: the WarmBot checked out for the current game, per team
        self.study_of: dict[str, float] = {}  # study clock of the current game's container, per team
        self.chat = MatchChat(echo)  # the match's shared chat: one conversation across all its games
        self.doc: dict = {
            "match_id": match_id, "tournament": tournament, "round": round_no,
            "a": a.team, "b": b.team, "status": "running", "best_of": best_of,
            "score": {a.team: 0, b.team: 0}, "winner": None,
            "costs": {a.team: None, b.team: None}, "games": [],
            "names": {a.team: a.name, b.team: b.name},
            "seeds": {a.team: a.seed, b.team: b.seed},
            "decided_by": None,
            "clocks": {"study": self.study, "move": self.move, **({"warm_study": self.warm_study} if pool else {})},
            "started": config.now_iso(), "finished": None, "chat": self.chat.lines,
        }
        if clocks:
            self.doc["clocks"]["teams"] = {
                t: {"move": self.move_of[t], **({"study": self.study_fixed[t]} if t in self.study_fixed else {})}
                for t in (a.team, b.team)}
        if extra:
            self.doc.update(extra)

    # ----------------------------------------------------------------- I/O
    def write(self) -> None:
        self.doc["score"] = {t: (int(s) if float(s).is_integer() else s) for t, s in self.score.items()}
        self.doc["updated"] = config.now_iso()
        config.write_json_atomic(self.out_path, self.doc)

    def _study_clock(self, team: str, default):
        """The study clock of `team` for a game: its own fixed one (clocks=), else `default`."""
        return self.study_fixed.get(team, default)

    def _move_timeout(self, team: str) -> float:
        """How long the arena waits for `team`'s answer to a turn: its move clock, or, without one, the
        idle limit of its in-process player."""
        clock = self.move_of[team]
        if clock is not None:
            return clock
        return float(getattr(self.bots.get(team), "idle_seconds", None) or config.HUMAN_IDLE_SECONDS)

    def _make_bot(self, e: Entrant, key: str) -> Bot:
        if e.bot is not None:
            return e.bot
        from .warm import bot_env
        image_mode = e.image is not None
        env = bot_env(e, key, self.model)
        mem = Path(e.memory_dir) if e.memory_dir else config.MEMORY / config.safe_name(e.team)
        log = self.log_dir / f"{config.safe_name(self.match_id)}-{config.safe_name(e.team)}.log"
        label = f"{self.match_id}-{e.team}"
        if image_mode:
            labels = {"eestec-arena.tournament": self.tournament or "", "eestec-arena.match": self.match_id,
                      "eestec-arena.team": e.team, **e.labels}
            return Bot(label, image=e.image, env=env, log_path=log, memory_dir=mem,
                       network=e.network, labels=labels, shutdown_grace=self.grace)
        return Bot(label, cmd=e.cmd, env=env, log_path=log, memory_dir=mem, shutdown_grace=self.grace)

    # ----------------------------------------------------------- warm routing
    def _route(self, team: str, game_id: str, index: int) -> dict:
        """Pool mode: put the team's container for `game_id` in self.bots[team] for this game. A ready warm
        container plays with the warm study clock; otherwise a cold container starts now (normal study
        clock, this match's key in its environment) and the pool keeps it for the game afterwards."""
        e = self.side[team]
        if e.bot is not None:  # an in-process player has no container: it plays every game itself
            self.bots[team] = e.bot
            if not e.bot.alive():
                e.bot.start()
            self.study_of[team] = self._study_clock(team, self.study)
            return {"team": team, "warm": False, "origin": "in-process", "container": None,
                    "study_seconds": self.study_of[team]}
        wb = self.pool.checkout(e, game_id)
        warm = wb is not None
        if wb is None:
            wb = self.pool.make(e, game_id, self.keyof.get(team, ""), self.model, origin="cold")
            if not self.pool.register(wb, evict=True):
                wb.temporary = True  # over the cap with every container busy: play, then shut down
            wb.state = "busy"
            wb.bot.start()
        self.held[team] = wb
        self.bots[team] = wb.bot
        # the short warm clock is for containers prepared for this game; a kept cold container never got
        # `prep`, so it keeps the normal study clock for every later variant (PLATFORM-FINDINGS F5)
        self.study_of[team] = self._study_clock(team, self.warm_study if warm and wb.origin == "prep" else self.study)
        wb.matches.append(self.match_id)
        info = {"team": team, "warm": warm, "origin": wb.origin, "container": wb.bot.container,
                "study_seconds": self.study_of[team]}
        wb.bot.note(f"match {self.match_id} game {index}: {'warm' if warm else 'cold'} container, "
                    f"study {self.study_of[team]:g} s")
        self._match_note(team, f"game {index} ({game_id}): {'warm' if warm else 'cold'} {wb.origin} container "
                               f"{wb.bot.container or wb.bot.label} (log {wb.bot.log_path})")
        return info

    def _return_containers(self) -> None:
        """Pool mode: the current game's containers go back to the pool (idle, still alive)."""
        if self.pool is None:
            return
        held, self.held = self.held, {}
        for wb in held.values():
            self.pool.checkin(wb)

    def _match_note(self, team: str, text: str) -> None:
        """Per-match index log (pool mode): which container played which game; the bot's own stderr is in
        the container's log under logs/warm/."""
        try:
            path = self.log_dir / f"{config.safe_name(self.match_id)}-{config.safe_name(team)}.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"[arena {time.strftime('%H:%M:%S')}] {text}\n")
        except OSError:
            pass

    # ------------------------------------------------------------- the match
    def run(self) -> dict:
        handles: dict[str, Any] = {}
        ok = False
        tied = False  # level after every game: the tie-break decides once the costs are known
        try:
            acquired = _parallel({e.team: (lambda e=e: self.keys.acquire(e.team, self.match_id, self.model))
                                  for e in (self.a, self.b)})
            for e in (self.a, self.b):
                key, handles[e.team] = acquired[e.team]
                self.keyof[e.team] = key
                if self.pool is None:
                    self.bots[e.team] = self._make_bot(e, key)
            if any(h is None for h in handles.values()):
                self.doc["note"] = getattr(self.keys, "note", "") or "static LLM key: cost not tracked"
            self.write()
            for bot in self.bots.values():
                bot.start()
            index = 0
            while self._more_games(index):
                index += 1
                try:
                    self._play_game(index)
                finally:
                    self._return_containers()
            sa, sb = self.score[self.a.team], self.score[self.b.team]
            if sa != sb:
                self.doc["winner"] = self.a.team if sa > sb else self.b.team
                self.doc["decided_by"] = "score"
            elif self.play_all:
                self.doc["winner"] = None
                self.doc["decided_by"] = "draw"
            else:
                tied = True
            ok = True
        except BaseException as exc:
            self.doc["status"] = "error"
            self.doc["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            grace = self.grace if ok else min(self.grace, 2.0)
            if self.pool is None:  # one container per team for the match: its life ends with the match
                _parallel({t: (lambda b=b: b.shutdown(grace)) for t, b in self.bots.items()})
            else:  # warm containers stay with the pool (they wait for the next match drawing their game)
                self._return_containers()
                for e in (self.a, self.b):
                    if e.bot is not None:  # an in-process player lives for one match
                        e.bot.shutdown(grace)
            def release(team, handle):
                try:
                    return self.keys.release(handle)
                except Exception as exc:  # noqa: BLE001 - cost is best effort
                    self.doc.setdefault("warnings", []).append(f"cost for {team}: {exc}")
                    return None
            if handles:
                costs = _parallel({t: (lambda t=t, h=h: release(t, h)) for t, h in handles.items()})
                self.doc["costs"].update(costs)
            if ok:
                if tied:
                    self._break_tie()
                sa, sb = self.score[self.a.team], self.score[self.b.team]
                self.echo(f"match {self.match_id}: winner {self.doc['winner']} "
                          f"({self._fmt(sa)}-{self._fmt(sb)}, by {self.doc['decided_by']})")
                self.doc["status"] = "done"
            self.doc["finished"] = config.now_iso()
            self.write()
        return self.doc

    def _break_tie(self) -> None:
        """Knockout match level after every game: fewer warnings, then less thinking time, then lower cost
        (doc["costs"], known now: the keys were released), then the coin. Records `tiebreak`."""
        a, b = self.a.team, self.b.team
        totals = match_totals(self.doc)
        costs = self.doc.get("costs") or {}
        coin = coin_flip(self.match_id, self.coin_seed, (a, b))
        winner, how = break_tie(a, b, totals, costs, coin)
        self.doc["winner"] = winner
        self.doc["decided_by"] = how
        self.doc["tiebreak"] = {"order": list(TIEBREAK_ORDER), "decided_by": how, "winner": winner,
                                "warnings": {t: totals[t]["warnings"] for t in (a, b)},
                                "time_ms": {t: totals[t]["time_ms"] for t in (a, b)},
                                "cost": {t: costs.get(t) for t in (a, b)}, "coin": coin}

    @staticmethod
    def _fmt(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    def _more_games(self, played: int) -> bool:
        if self.play_all:
            return played < self.best_of
        diff = abs(self.score[self.a.team] - self.score[self.b.team])
        if played < self.best_of:
            return diff <= self.best_of - played
        return diff == 0 and played < self.best_of + self.max_sd

    # -------------------------------------------------------------- one game
    def _play_game(self, index: int) -> None:
        cls, pick = self.picker(index)
        seats = [self.a.team, self.b.team] if index % 2 == 1 else [self.b.team, self.a.team]
        g: dict = {"index": index, "game_id": cls.id, "game_name": cls.name, "category": cls.category,
                   "variant": pick.variant, "variant_index": pick.variant_index, "seed": pick.game_seed,
                   "seats": seats, "rules": "", "status": "running", "sudden_death": index > self.best_of,
                   "study": {}, "timeline": [], "result": None}
        fields = getattr(self.picker, "game_fields", None)
        if callable(fields):
            g.update(fields(index))
        self.doc["games"].append(g)
        try:
            game = cls(dict(pick.variant), pick.game_seed)
            g["rules"] = game.rules()
        except Exception:
            self._engine_error(g, seats, None)
            return
        self.echo(f"game {index}: {cls.name} [{pick.variant.get('label', '')}] "
                  f"seat 0 = {seats[0]}, seat 1 = {seats[1]}")
        self.write()

        if self.pool is None:
            for team in seats:  # a bot that crashed in an earlier game gets a fresh process
                self.study_of[team] = self._study_clock(team, self.study)
                if not self.bots[team].alive():
                    self.bots[team].start()
        else:
            g["containers"] = {str(s): self._route(seats[s], cls.id, index) for s in (0, 1)}
        from .warm import llm_block

        # ---- start / ready (study clock) ----
        def start_msg(seat: int) -> dict:
            me, opp = seats[seat], seats[1 - seat]
            return {"type": "start", "match_id": self.match_id, "game_index": index,
                    "best_of": self.best_of, "game_id": cls.id, "game_name": cls.name,
                    "variant": pick.variant, "rules": g["rules"], "seat": seat, "you": me,
                    "opponent": opp, "match_score": self._match_score(me),
                    "study_seconds": self.study_of[me], "move_seconds": self.move_of[me], "chat": self.chat.view(me),
                    "llm": llm_block(self.side[me], self.keyof.get(me, ""), self.model)}

        replies = _parallel({s: (lambda s=s: self.bots[seats[s]].request(start_msg(s), self.study_of[seats[s]], "ready"))
                             for s in (0, 1)})
        failed: dict[int, str] = {}
        said: dict[int, str] = {}  # pre-game chat from accepted `ready` replies
        for s in (0, 1):
            r = replies[s]
            entry: dict = {"ms": r.ms}
            if r.ok:
                c = chat_text(r.msg)  # the chat move sent with `ready`
                if c:
                    said[s] = c
            else:
                entry["error"] = r.kind
                if r.kind == TIMEOUT:
                    entry["timeout"] = True
                failed[s] = f"{seats[s]} {_ERROR_WORDS.get(r.kind, r.kind)} during study ({r.describe()})"
            g["study"][str(s)] = entry
        self._log_chat(g, 0, seats, said)
        try:
            if not failed:
                self._hear(game, said)  # pre-game talk counts as said (games may restrict it)
            g["timeline"].append({"step": 0, "frame": _snap(game)})
        except Exception:
            self._engine_error(g, seats, game)
            return
        self.write()
        if failed:
            self._forfeit(g, seats, game, failed)
            return

        # ---- turns (move clock) ----
        step = 0
        bad: dict[int, dict] = {}  # seat -> first rejected answer this game (the warning)
        g["warnings"] = {"0": 0, "1": 0}
        while True:
            try:
                if game.is_over():
                    break
                movers = list(game.to_move())
                if not movers:
                    break
                turn_msgs = {s: turn_message(game, s, game_index=index, turn=step + 1,
                                             seconds=self.move_of[seats[s]], chat=self.chat.view(seats[s]))
                             for s in movers}
            except Exception:
                self._engine_error(g, seats, game)
                return
            step += 1
            if step > config.MAX_STEPS:
                self._finish(g, seats, game, {"winner": None, "scores": [0, 0],
                                              "reason": f"engine step cap ({config.MAX_STEPS}) reached"})
                return
            actions, record, failed, said = self._collect_turn(game, g, seats, movers, turn_msgs, bad)
            if failed:
                self._log_chat(g, step, seats, said)  # visible to the opponent from its next message
                try:
                    frame = _snap(game)
                except Exception:
                    frame = {}
                g["timeline"].append({"step": step, "actions": record, "frame": frame})
                self._forfeit(g, seats, game, failed)
                return
            try:
                if self._hear(game, said) and game.is_over():  # the chat ended the game: no move
                    self._log_chat(g, step, seats, said)
                    g["timeline"].append({"step": step, "actions": record, "frame": _snap(game),
                                          "applied": False})
                    self.write()
                    break
                spoken = self._spoken(game, actions)  # talk games: the words of each move
                game.apply(actions)
                frame = _snap(game)
            except Exception:
                self._log_chat(g, step, seats, said)
                g["timeline"].append({"step": step, "actions": record})
                self._engine_error(g, seats, game)
                return
            self._log_chat(g, step, seats, said, spoken)  # visible to the opponent from its next message
            g["timeline"].append({"step": step, "actions": record, "frame": frame})
            self.write()
        try:
            res = game.result()
        except Exception:
            self._engine_error(g, seats, game)
            return
        self._finish(g, seats, game, res)

    def _judge(self, game, seat: int, r: Reply) -> tuple[dict, str | None, str | None, str, str]:
        """The game move of one answer to a `turn` -> (entry, canonical action | None, error kind | None,
        why, raw). The chat move is read separately (chat_text), and only from accepted answers."""
        entry: dict = {"action": None, "ms": r.ms}
        if not r.ok:
            raw = r.raw[:200] if r.kind in (INVALID, WRONG_TYPE) else ""
            if r.kind == TIMEOUT:
                why = f"timed out after {r.ms / 1000:g} s"
            elif r.kind == INVALID:
                why = f"invalid JSON: {raw[:60]!r}"
            elif r.kind == WRONG_TYPE:
                got = (r.msg or {}).get("type")
                why = f"wrong message type {got!r} (expected 'action')"
            else:
                why = f"{_ERROR_WORDS.get(r.kind, r.kind)} ({r.describe()})"
            return entry, None, r.kind, why, raw
        raw = r.msg.get("action")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            raw = str(raw)
        if not isinstance(raw, str) or not raw.strip():
            return entry, None, "missing", "missing or empty action", ""
        try:
            canon = game.normalize(seat, raw)
        except Exception:  # a game bug on odd input counts as illegal
            canon = None
        if canon is None:
            return entry, None, "illegal", f"illegal move: {raw[:60]!r}", raw[:200]
        return entry, canon, None, "", raw

    def _collect_turn(self, game, g: dict, seats: list[str], movers: list[int], turn_msgs: dict,
                      bad: dict[int, dict]) -> tuple[dict[int, str], dict[str, dict], dict[int, str], dict[int, str]]:
        """Ask every mover for its action. A seat's first bad answer in a game (illegal, invalid
        JSON, wrong type, missing action) is a warning: the same turn is re-sent with a `warning`
        field and a fresh clock while the other seat's accepted action is held. The second bad
        answer, a timeout or a crash ends the game. Returns (actions, record, failed, said): `said` holds
        the chat moves of the accepted answers (a rejected answer's chat is dropped)."""
        actions: dict[int, str] = {}
        said: dict[int, str] = {}
        record: dict[str, dict] = {}
        failed: dict[int, str] = {}
        pending = list(movers)
        msgs = dict(turn_msgs)
        warned_here: dict[int, dict] = {}  # warnings issued during this step
        while pending:
            replies = _parallel({s: (lambda s=s: self.bots[seats[s]].request(
                msgs[s], self._move_timeout(seats[s]), "action")) for s in pending})
            retry = []
            for s in pending:
                entry, canon, kind, why, raw = self._judge(game, s, replies[s])
                # what this seat saw (published after the match; helps teams build parsers from replays)
                entry["observation"] = str(turn_msgs[s].get("observation", ""))[:4000]
                if s in warned_here:
                    entry["warning"] = warned_here[s]
                if canon is not None:
                    entry["action"] = canon
                    actions[s] = canon
                    c = chat_text(replies[s].msg)
                    if c:
                        said[s] = c
                elif kind in WARNABLE and s not in bad:
                    bad[s] = warned_here[s] = {"count": 1, "reason": why, "rejected": raw}
                    g["warnings"][str(s)] = 1
                    entry["warning"] = warned_here[s]
                    msgs[s] = dict(turn_msgs[s], seconds=self.move_of[seats[s]],
                                   warning={"count": 1, "max": config.BAD_ANSWERS_TO_LOSE, "reason": why,
                                            "rejected": raw})
                    retry.append(s)
                    self.echo(f"  {seats[s]}: WARNING {why} - turn re-sent")
                else:
                    entry["error"] = kind
                    if kind == TIMEOUT:
                        entry["timeout"] = True
                    if kind in (INVALID, WRONG_TYPE, "illegal") and raw:
                        entry["raw" if kind != "illegal" else "action"] = raw
                    if kind in WARNABLE:  # second bad answer in this game
                        failed[s] = f"{seats[s]}: second {why} (warned before: {bad[s]['reason']})"
                    else:
                        failed[s] = f"{seats[s]} {why}"
                record[str(s)] = entry
                if s not in retry:
                    self._echo_action(seats[s], entry)
            if failed:
                break  # pending retries are moot: the game is decided
            pending = retry
        return actions, record, failed, said

    def _echo_action(self, team: str, entry: dict) -> None:
        if entry.get("error"):
            self.echo(f"  {team}: {entry.get('error').upper()} {entry.get('action') or entry.get('raw') or ''}")
        else:
            self.echo(f"  {team}: {entry['action']}  ({entry['ms'] / 1000:.1f}s)")

    # ------------------------------------------------------------------ chat
    def _chat_view(self, team: str) -> list[dict]:
        """The whole match chat as `team` reads it (old name, kept for callers)."""
        return self.chat.view(team)

    def _log_chat(self, g: dict, step: int, seats: list[str], said: dict[int, str],
                  spoken: dict[int, str] | None = None) -> None:
        """Add this step's lines to the match chat, in seat order, tagged with the phase: for each seat
        first the words of its game move (talk games, kind "move"), then its chat move (kind "chat")."""
        spoken = spoken or {}
        for s in sorted(set(said) | set(spoken)):
            for kind, text in (("move", spoken.get(s)), ("chat", said.get(s))):
                if text:
                    self.chat.say(game=g["index"], game_id=g["game_id"], game_name=g["game_name"], step=step,
                                  seat=s, team=seats[s], text=text, kind=kind)

    @staticmethod
    def _spoken(game, actions: dict[int, str]) -> dict[int, str]:
        """Talk games: what each accepted move says out loud (Game.said); a game bug here says nothing."""
        out: dict[int, str] = {}
        for s in sorted(actions):
            try:
                t = game.said(s, actions[s])
            except Exception:
                t = None
            if isinstance(t, str) and t.strip():
                out[s] = " ".join(t.split())
        return out

    @staticmethod
    def _hear(game, said: dict[int, str]) -> bool:
        """Pass accepted chats to the game's optional on_chat(seat, text) hook, in seat order."""
        hook = getattr(game, "on_chat", None)
        if not callable(hook) or not said:
            return False
        for s in sorted(said):
            hook(s, said[s])
        return True

    def _match_score(self, team: str) -> dict:
        opp = self.b.team if team == self.a.team else self.a.team
        f = lambda x: int(x) if float(x).is_integer() else x  # noqa: E731
        return {"you": f(self.score[team]), "opponent": f(self.score[opp])}

    def _forfeit(self, g: dict, seats: list[str], game, failed: dict[int, str]) -> None:
        if len(failed) == 2:
            res = {"winner": None, "scores": [0, 0], "reason": "; ".join(failed.values())}
        else:
            (loser, why), = failed.items()
            winner = 1 - loser
            scores = [0, 0]
            scores[winner] = 1
            res = {"winner": winner, "scores": scores, "reason": why}
        g["forfeit"] = True
        self._finish(g, seats, game, res)

    def _engine_error(self, g: dict, seats: list[str], game) -> None:
        tb = traceback.format_exc()
        g["error"] = tb[-2000:]
        self.echo(f"  ENGINE ERROR in game {g['game_id']}: {tb.strip().splitlines()[-1]}")
        self._finish(g, seats, game, {"winner": None, "scores": [0, 0],
                                      "reason": "game engine error (counted as a draw)"})

    def _finish(self, g: dict, seats: list[str], game, res: dict) -> None:
        w = res.get("winner")
        w = w if w in (0, 1) else None
        scores = list(res.get("scores") or [0, 0])
        reason = str(res.get("reason", ""))
        g["result"] = {"winner_seat": w, "winner": seats[w] if w is not None else None,
                       "scores": scores, "reason": reason}
        g["status"] = "done"
        if w is None:
            self.score[seats[0]] += 0.5
            self.score[seats[1]] += 0.5
        else:
            self.score[seats[w]] += 1
        played = g["index"]
        match_over = not self._more_games(played)
        self.echo(f"  result: {g['result']['winner'] or 'draw'} - {reason}  "
                  f"(match {self._fmt(self.score[self.a.team])}-{self._fmt(self.score[self.b.team])})")
        self.write()
        for s in (0, 1):
            team = seats[s]
            outcome = "draw" if w is None else ("win" if w == s else "loss")
            try:
                final_obs = game.observation(s) if game is not None else ""
            except Exception:
                final_obs = ""
            msg = {"type": "end", "game_index": g["index"], "result": outcome, "reason": reason,
                   "scores": {"you": scores[s] if len(scores) > s else 0,
                              "opponent": scores[1 - s] if len(scores) > 1 - s else 0},
                   "final_observation": final_obs, "match_score": self._match_score(team),
                   "match_over": match_over, "chat": self.chat.view(team)}
            self.bots[team].send(msg)


def run_match(a: Entrant, b: Entrant, **kwargs) -> dict:
    """Convenience wrapper: MatchRunner(a, b, **kwargs).run()."""
    return MatchRunner(a, b, **kwargs).run()
