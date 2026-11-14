"""Warm per-game containers: prep runs and the pool that routes a drawn game to its prepared container.

See docs/ARCHITECTURE.md section 4.1. Prep is fully automatic: after the freeze the arena starts each
team's image once per needed game (the whole pool in T1/T2, the drawn games in T3) and sends that copy
`prep` (the rules of every variant of that one game, `seconds` to use). The container assembles itself into a standalone specialist for the game
(simulator, solver, chat plan), answers `ready` and then stays alive, idle, owned by the arena.

When a match draws the game, the arena routes that game's start/turn/end to the team's container for
it (WarmPool.checkout / checkin); `end` with `match_over` does not end a warm container's life, it
waits for the next match that draws its game. A team without a ready container for the drawn game
gets a cold one (the old flow: `start` with the normal study clock), which is then kept as the team's
container for that game. `{"type": "shutdown"}` + closed stdin ends a container's life.

The per-match LLM key travels in `start["llm"]` (containers outlive matches); the environment holds
the key the container was started with (its prep key, or the first match's key for a cold container).
"""
from __future__ import annotations

import functools
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import config, randomizer
from .protocol import EOF, INVALID, OK, TIMEOUT, WRONG_TYPE, Bot, container_memory

_log = logging.getLogger(__name__)

# outcomes of a prep run (prep.json "status")
READY = "ready"  # answered ready: warm, alive, waiting for its game
PREP_TIMEOUT = "timeout"  # no ready within `seconds`: stopped, the game is played by a cold container
PREP_ERROR = "error"  # crashed / failed to start during prep: same fallback
STOPPED = "stopped"  # the run was cut short (session released while preparing)


def bot_env(entrant, key: str, model: str) -> dict[str, str]:
    """Environment of a bot process: gateway URL for its mode, key, model, team id (+ entrant extras)."""
    env = {"LLM_BASE_URL": llm_base_url(entrant), "LLM_API_KEY": key, "LLM_MODEL": model, "TEAM_ID": entrant.team}
    env.update(entrant.env)
    return env


def llm_base_url(entrant) -> str:
    if entrant.llm_base_url:
        return entrant.llm_base_url
    return config.CONTAINER_LLM_BASE_URL if entrant.image is not None else config.HOST_LLM_BASE_URL


def llm_block(entrant, key: str, model: str) -> dict[str, str]:
    """The `llm` field of `prep` / `start`: what the harness must use for this prep or match."""
    env = bot_env(entrant, key, model)
    return {"base_url": env["LLM_BASE_URL"], "api_key": key, "model": env["LLM_MODEL"]}


def entrant_ref(entrant) -> str:
    """What a container runs: a warm container only serves the same image (digest ref) or command."""
    if entrant.image is not None:
        return str(entrant.image)
    cmd = entrant.cmd
    return cmd if isinstance(cmd, str) else " ".join(map(str, cmd or []))


def _num(x):
    return int(x) if float(x).is_integer() else x


SAMPLE_MIN_MOVES = 2  # before the sample turn each seat has moved at least this often (history lines show)
SAMPLE_FRACTION = 3  # ... and about 1/SAMPLE_FRACTION of the sample game has been played
SAMPLE_TRIES = 8  # seeded random playouts tried when random play ends the game before any history


def _random_action(game, seat: int, rng: random.Random) -> str:
    """Like arena/tests/make_fixtures.py: the game's own random_action(seat, rng) when it has one, else a
    uniform pick from legal_actions()."""
    gen = getattr(game, "random_action", None)
    if callable(gen):
        return gen(seat, rng)
    legal = game.legal_actions(seat)
    if legal:
        return rng.choice(legal)
    raise ValueError(f"seat {seat}: legal_actions is None and the game has no random_action(seat, rng)")


def sample_turn(game_cls, variant: dict, seed: int, move: float = config.MOVE_SECONDS) -> dict:
    """One complete, real `turn` message for seat 0, exactly as the arena sends it (match.turn_message:
    `type`, `game_index` 1, `turn`, `observation`, `legal_actions`, `seconds`, `chat` []), taken mid-game
    from a sample game of `variant` dealt with `seed` (the prep seed of the rules text, never a real
    match's deal) and played with seeded random legal moves.

    The turn is seat 0's first decision at or after about a third of that sample game in which each seat
    has already moved at least SAMPLE_MIN_MOVES times (so round history and feedback lines appear). When
    random play ends the game before that, other seeded random playouts of the same deal are tried (up to
    SAMPLE_TRIES); if none gets there, seat 0's last decision of the longest one. Never past the end.
    Deterministic: a pure function of (game, variant, seed, move). Raises on an engine error (the caller
    leaves the sample out)."""
    from .match import turn_message

    def replay(attempt: int, stop_at: int | None):
        """Play the sample game; returns (game, steps played, [(step, min moves so far) where seat 0 moves])."""
        game = game_cls(dict(variant), seed)
        rng = random.Random(randomizer.derive_seed("sample-turn", game_cls.id, seed, attempt))
        moved, seat0, step = [0, 0], [], 0
        while not game.is_over() and step < config.MAX_STEPS:
            movers = list(game.to_move())
            if not movers:
                break
            if step + 1 == stop_at:
                return game, step, seat0
            step += 1
            if 0 in movers:
                seat0.append((step, min(moved)))
            actions = {}
            for s in movers:
                raw = _random_action(game, s, rng)
                canon = game.normalize(s, raw)
                if canon is None:
                    raise ValueError(f"random action {raw!r} of seat {s} was rejected at step {step}")
                actions[s] = canon
            game.apply(actions)
            for s in movers:
                moved[s] += 1
        return game, step, seat0

    choice = None  # (attempt, step)
    fallback = None  # (seat-0 decisions, attempt, step): the longest playout too short for history
    for attempt in range(SAMPLE_TRIES):
        _, total, seat0 = replay(attempt, None)
        rich = [st for st, m in seat0 if m >= SAMPLE_MIN_MOVES]
        if rich:
            target = -(-total // SAMPLE_FRACTION)  # ceil(total / 3)
            choice = (attempt, next((st for st in rich if st >= target), rich[-1]))
            break
        if seat0 and (fallback is None or len(seat0) > fallback[0]):
            fallback = (len(seat0), attempt, seat0[-1][0])
    if choice is None:
        if fallback is None:
            raise ValueError("seat 0 never moves in the sample game")
        choice = fallback[1:]
    attempt, at = choice
    game, step, _ = replay(attempt, at)
    if step + 1 != at or game.is_over() or 0 not in game.to_move():
        raise ValueError(f"the sample game did not replay to step {at}")
    msg = turn_message(game, 0, game_index=1, turn=at, seconds=_num(move), chat=[])
    return json.loads(json.dumps(msg))  # detached, JSON-safe (exactly what goes over the wire)


@functools.lru_cache(maxsize=512)
def _sample_cached(game_cls, variant_index: int, seed: int, move) -> tuple[str | None, str | None]:
    """(sample turn as JSON text, None) or (None, why). Cached: every team's prep gets the same sample and
    a failing game is logged once."""
    try:
        v = game_cls.variants()[variant_index]
        return json.dumps(sample_turn(game_cls, v, seed, move)), None
    except Exception as exc:  # noqa: BLE001 - an engine error only costs the sample, never the prep
        why = f"{type(exc).__name__}: {exc}"
        _log.warning("prep %s variant %d: no sample_turn (%s)", getattr(game_cls, "id", "?"), variant_index, why)
        return None, why


def prep_variants(game_cls, seed: int = 0, move: float = config.MOVE_SECONDS,
                  log: Callable[[str], None] | None = None) -> list[dict]:
    """[{"label", "rules", "sample_turn"}] for every variant. Rules may hold a sample deal (the seeded parts of
    a game); the same seed gives every team the same text. `sample_turn` is a real
    `turn` message from a sample game of that deal (sample_turn()); it is left out, and `log` told why, when
    the engine fails to produce one."""
    out = []
    for i, v in enumerate(game_cls.variants()):
        gseed = randomizer.derive_seed("prep", seed, game_cls.id, i) % 2_147_483_647
        entry = {"label": v.get("label", ""), "rules": game_cls(dict(v), gseed).rules()}
        sample, why = _sample_cached(game_cls, i, gseed, _num(move))
        if sample is not None:
            entry["sample_turn"] = json.loads(sample)
        elif log is not None:
            log(f"prep {game_cls.id} variant {v.get('label', i)!r}: no sample_turn ({why})")
        out.append(entry)
    return out


def prep_message(game_cls, team: str, *, seconds: float, llm: dict, seed: int = 0,
                 study: float = config.WARM_STUDY_SECONDS, move: float = config.MOVE_SECONDS,
                 log: Callable[[str], None] | None = None) -> dict:
    return {"type": "prep", "game_id": game_cls.id, "game_name": game_cls.name,
            "variants": prep_variants(game_cls, seed, move, log), "seconds": _num(seconds), "you": team,
            "study_seconds": _num(study), "move_seconds": _num(move), "llm": llm}


# ------------------------------------------------------------------------- pool
@dataclass
class WarmBot:
    team: str
    game_id: str
    ref: str
    bot: Bot
    origin: str  # "prep" (prepared for the game) | "cold" (started by a match, kept afterwards)
    state: str = "starting"  # starting | prepping | ready | busy | dead | released
    since: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    matches: list[str] = field(default_factory=list)
    mem_mb: float | None = None
    temporary: bool = False  # over the cap: not kept after its game

    def alive(self) -> bool:
        return self.bot.alive()

    def info(self) -> dict:
        return {"team": self.team, "game": self.game_id, "origin": self.origin, "state": self.state,
                "container": self.bot.container, "since": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.since)),
                "matches": len(self.matches), "mem_mb": self.mem_mb}


class WarmPool:
    """The warm containers of one session (or one in-process run), keyed by (team, game id)."""

    def __init__(self, home: str, log_dir: str | os.PathLike, *, cap: int = config.WARM_CAP,
                 grace: float = config.SHUTDOWN_GRACE, echo: Callable[[str], None] | None = None):
        self.home = home
        self.log_dir = Path(log_dir)
        self.cap = max(1, int(cap))
        self.grace = grace
        self.echo = echo or (lambda s: None)
        self.entries: dict[tuple[str, str], WarmBot] = {}
        self.retired: list[dict] = []  # what happened to containers that left the pool (for the status files)
        self.lock = threading.RLock()

    # ---------------------------------------------------------------- making
    def make(self, entrant, game_id: str, key: str, model: str, origin: str) -> WarmBot:
        """A new (not started, not registered) container for `entrant` and `game_id`."""
        env = bot_env(entrant, key, model)
        mem = Path(entrant.memory_dir) if entrant.memory_dir else config.MEMORY / config.safe_name(entrant.team)
        log = self.log_dir / "warm" / f"{config.safe_name(entrant.team)}--{config.safe_name(game_id)}.log"
        label = f"{entrant.team}-{game_id}"
        if entrant.image is not None:
            labels = {"eestec-arena.session": self.home, "eestec-arena.team": entrant.team,
                      "eestec-arena.game": game_id, "eestec-arena.warm": "1", **getattr(entrant, "labels", {})}
            bot = Bot(label, image=entrant.image, env=env, log_path=log, memory_dir=mem, network=entrant.network,
                      labels=labels, shutdown_grace=self.grace)
        else:
            bot = Bot(label, cmd=entrant.cmd, env=env, log_path=log, memory_dir=mem, shutdown_grace=self.grace)
        return WarmBot(entrant.team, game_id, entrant_ref(entrant), bot, origin)

    def _alive_count(self) -> int:
        return sum(1 for wb in self.entries.values() if wb.state not in ("dead", "released"))

    def _evict_one(self) -> bool:
        """Shut down the least recently used idle container (cold ones first) to make room."""
        idle = [wb for wb in self.entries.values() if wb.state == "ready"]
        if not idle:
            return False
        wb = min(idle, key=lambda w: (w.origin == "prep", w.last_used))
        self._retire_locked(wb, "evicted: warm cap reached")
        return True

    def register(self, wb: WarmBot, evict: bool = False) -> bool:
        """Add `wb` (replacing an old container for the same team and game). False when the cap is reached
        and nothing may be evicted; with `evict`, idle containers make room (least recently used first)."""
        with self.lock:
            old = self.entries.get((wb.team, wb.game_id))
            if old is not None and old is not wb:
                self._retire_locked(old, "replaced")
            while self._alive_count() >= self.cap:
                if not (evict and self._evict_one()):
                    return False
            self.entries[(wb.team, wb.game_id)] = wb
            return True

    def has_room(self) -> bool:
        with self.lock:
            return self._alive_count() < self.cap

    # ---------------------------------------------------------------- routing
    def get(self, team: str, game_id: str) -> WarmBot | None:
        with self.lock:
            return self.entries.get((team, game_id))

    def ready(self, team: str, game_id: str, ref: str | None = None) -> bool:
        with self.lock:
            wb = self.entries.get((team, game_id))
            return bool(wb and wb.state == "ready" and (ref is None or wb.ref == ref) and wb.alive())

    def checkout(self, entrant, game_id: str) -> WarmBot | None:
        """The team's ready container for the game (now busy), or None (no container, a dead one, or one
        running another image: those are retired)."""
        with self.lock:
            wb = self.entries.get((entrant.team, game_id))
            if wb is None:
                return None
            if wb.state == "busy":
                return None
            if wb.state != "ready" or not wb.alive() or wb.ref != entrant_ref(entrant):
                why = "image changed" if wb.ref != entrant_ref(entrant) else "container exited"
                self._retire_locked(wb, why)
                return None
            wb.state = "busy"
            wb.last_used = time.time()
            return wb

    def checkin(self, wb: WarmBot) -> None:
        """After its game: back to ready (idle) when alive, else gone."""
        with self.lock:
            wb.last_used = time.time()
            if wb.temporary:
                threading.Thread(target=wb.bot.shutdown, args=(self.grace,), daemon=True).start()
                wb.state = "released"
                return
            if self.entries.get((wb.team, wb.game_id)) is not wb:
                return
            if wb.alive():
                wb.state = "ready"
            else:
                self._retire_locked(wb, "container exited")

    def retire(self, wb: WarmBot, reason: str, grace: float | None = None, wait: bool = False) -> None:
        with self.lock:
            self._retire_locked(wb, reason, grace, wait)

    def _retire_locked(self, wb: WarmBot, reason: str, grace: float | None = None, wait: bool = False) -> None:
        if self.entries.get((wb.team, wb.game_id)) is wb:
            del self.entries[(wb.team, wb.game_id)]
        was_alive = wb.state not in ("dead", "released") and wb.alive()
        wb.state = "released" if was_alive else "dead"
        self.retired.append({**wb.info(), "reason": reason, "at": config.now_iso()})
        if len(self.retired) > 500:
            del self.retired[:100]
        g = self.grace if grace is None else grace
        if wait:
            wb.bot.shutdown(g)
        else:
            threading.Thread(target=wb.bot.shutdown, args=(g,), daemon=True).start()

    # ---------------------------------------------------------------- the end
    def release_all(self, grace: float | None = None) -> int:
        """Shutdown message, closed stdin and `grace` seconds for every container (in parallel)."""
        with self.lock:
            wbs = list(self.entries.values())
            self.entries.clear()
        g = self.grace if grace is None else grace
        threads = []
        for wb in wbs:
            alive = wb.alive()
            wb.state = "released" if alive else "dead"
            self.retired.append({**wb.info(), "reason": "released at the end of the session", "at": config.now_iso()})
            t = threading.Thread(target=wb.bot.shutdown, args=(g,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=g + 30)
        return len(wbs)

    # ---------------------------------------------------------------- status
    def containers(self) -> list[WarmBot]:
        with self.lock:
            return list(self.entries.values())

    def sample_memory(self) -> dict[str, float]:
        """Refresh mem_mb of the image containers (docker stats); returns {container: MiB}."""
        wbs = [wb for wb in self.containers() if wb.bot.container and wb.alive()]
        usage = container_memory([wb.bot.container for wb in wbs])
        for wb in wbs:
            if wb.bot.container in usage:
                wb.mem_mb = usage[wb.bot.container]
        return usage

    def snapshot(self) -> dict:
        wbs = self.containers()
        alive = [wb for wb in wbs if wb.state not in ("dead", "released")]
        mems = [wb.mem_mb for wb in alive if wb.mem_mb is not None]
        by_state: dict[str, int] = {}
        for wb in alive:
            by_state[wb.state] = by_state.get(wb.state, 0) + 1
        return {"alive": len(alive), "cap": self.cap, "by_state": by_state,
                "mem_mb_total": round(sum(mems), 1) if mems else None,
                "mem_mb_avg": round(sum(mems) / len(mems), 1) if mems else None,
                "mem_mb_max": max(mems) if mems else None, "measured": len(mems),
                "containers": [wb.info() for wb in sorted(alive, key=lambda w: (w.team, w.game_id))]}


# ------------------------------------------------------------------- one prep
def prep_one(pool: WarmPool, entrant, game_cls, *, keys, seconds: float = config.PREP_SECONDS,
             seed: int = 0, model: str = config.MODEL, study: float = config.WARM_STUDY_SECONDS,
             move: float = config.MOVE_SECONDS, prep_id: str = "", stop: threading.Event | None = None,
             on_update: Callable[[dict], None] | None = None) -> dict:
    """Prepare one container of `entrant` for `game_cls` and keep it in `pool` when it answers `ready`.

    Returns the prep record: {"status": ready|timeout|error|stopped, "seconds", "cost", "note", "started",
    "finished", "container"}. A bot that ignores `prep` (no answer: timeout) or crashes on it is never
    penalized: its games are played by cold containers with the normal study clock.
    """
    on_update = on_update or (lambda rec: None)
    rec: dict[str, Any] = {"status": "running", "started": config.now_iso(), "seconds": None, "cost": None,
                           "note": "", "container": None}
    run_id = prep_id or f"prep-{pool.home}-{game_cls.id}"
    try:
        key, handle = keys.acquire(entrant.team, run_id, model)
    except Exception as exc:  # noqa: BLE001 - a key failure is an error of this run only
        rec.update(status=PREP_ERROR, note=f"no LLM key: {exc}", finished=config.now_iso())
        return rec
    wb = pool.make(entrant, game_cls.id, key, model, origin="prep")
    if not pool.register(wb):
        rec.update(status="skipped", note=f"warm cap ({pool.cap}) reached: this game is played cold",
                   finished=config.now_iso())
        _release_key(keys, handle, rec)
        return rec
    wb.state = "prepping"
    bot = wb.bot
    t0 = time.monotonic()
    bot.start()
    rec["container"] = bot.container
    on_update(dict(rec))
    msg = prep_message(game_cls, entrant.team, seconds=seconds, llm=llm_block(entrant, key, model), seed=seed,
                       study=study, move=move, log=bot.note)
    bot.note(f"prep {game_cls.id}: {len(msg['variants'])} variant(s), {seconds:g} s")
    outcome, note = PREP_TIMEOUT, f"no ready within {seconds:g} s"
    if not bot.send(msg):
        outcome, note = PREP_ERROR, "the container exited before the prep message"
    else:
        deadline = t0 + seconds + config.CLOCK_GRACE
        while True:
            if stop is not None and stop.is_set():
                outcome, note = STOPPED, "session released during prep"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            r = bot.recv(min(1.0, remaining), expect="ready")
            if r.kind == TIMEOUT:
                continue
            if r.kind == OK:
                outcome, note = READY, ""
                break
            if r.kind == EOF:
                outcome, note = PREP_ERROR, f"exited during prep ({r.describe()})"
                break
            if r.kind in (INVALID, WRONG_TYPE):  # tolerated during prep: logged, keep waiting
                bot.note(f"prep: ignored {r.describe()}")
    used = round(time.monotonic() - t0, 1)
    rec.update(status=outcome, seconds=used, note=note)
    if outcome == READY:
        with pool.lock:
            if wb.state == "prepping":
                wb.state = "ready"
                wb.last_used = time.time()
        bot.note(f"prep {game_cls.id}: ready after {used:g} s, waiting for its game")
    else:
        bot.note(f"prep {game_cls.id}: {outcome} ({note}); its games are played by a cold container")
        pool.retire(wb, f"prep {outcome}", grace=min(pool.grace, 5.0))
    rec["finished"] = config.now_iso()
    on_update(dict(rec))
    _release_key(keys, handle, rec)
    return rec


def _release_key(keys, handle, rec: dict) -> None:
    try:
        rec["cost"] = keys.release(handle)
    except Exception as exc:  # noqa: BLE001 - cost is best effort
        rec["note"] = (rec.get("note") + "; " if rec.get("note") else "") + f"cost unknown: {exc}"
