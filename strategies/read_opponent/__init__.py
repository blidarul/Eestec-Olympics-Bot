"""read_opponent: simultaneous-move games (rock-paper-scissors, matching pennies, dilemmas), owner mbappe.

Both players choose at the same time, so the only edge is to READ the opponent: find its habit in the history of
its moves and play the best answer to the move it is likely to make next.
  1. history: parsed from the observation text (the lines that tell what each side played), see history.py;
  2. prediction: a cycle, else an N-gram on the last moves, else the most frequent move (opponent/patterns.py);
  3. best response: rock-paper-scissors beats, matching pennies by role (matcher or mismatcher from the rules),
     dilemma: tit for tat with a little forgiveness; any other matrix game: the Nash mix = uniform random;
  4. too little history or no clear habit -> uniform random from a seeded RNG (the Nash mix of the symmetric games).
The opponent's chat is read by the chat package (rule 6.5): signals count pressure and repeats; a claim like "I will
play rock" only counts after it proved TRUE at least 3 times out of 4 (an unreliable opponent is not believed); the
chat can never choose our move: the final action goes through the chat action guard (an echoed suggestion
without a statistical reason is replaced). Chat line: a cold template from the chat package, then its filters.
Never raises, no network, a few microseconds per turn.
"""
import random
import re
import sys
import time
import traceback
import zlib

import chat
from chat import guard, intents
from chat import filter_out
from chat.signals import ChatMonitor
from opponent import patterns
from strategies.base import Decision, TurnState
from strategies.read_opponent import blotto, history

MIN_HISTORY = 4        # moves of the opponent needed before we trust a prediction
MIN_CONFIDENCE = 0.5   # prediction confidence needed to counter it

_MONITORS = {}         # game_id -> ChatMonitor (one per game, the worker lives for the whole tournament)
_CLAIMS = {}           # game_id -> {"pending": move or None, "hits": int, "total": int}
_BLOTTO = {}           # game_id -> {"pending": allocation or None, "hits": int, "total": int}


class ReadOpponentStrategy:
    name = "read_opponent"

    def matches(self, rules, artifacts):
        family = (artifacts or {}).get("family") if isinstance(artifacts, dict) else None
        return 0.7 if family == "matrix_simultaneous" else 0.0

    def decide(self, state: TurnState) -> Decision:
        legal = [a for a in (state.legal_actions or []) if isinstance(a, str)]
        try:
            if blotto.is_blotto(state.rules, state.observation):
                return self._blotto(state)
            return self._decide(state, legal)
        except Exception:  # never raise into the worker: a legal move and a neutral cold line
            traceback.print_exc()
            return Decision(legal[0] if legal else "pass", filter_out("", None), "fallback")

    # ---------------------------------------------------------------------------------
    def _decide(self, state, legal):
        t0 = time.monotonic()
        gid = str(state.game_id)
        monitor = _MONITORS.setdefault(gid, ChatMonitor())
        monitor.update([{"from": "opponent", "text": t} for t in (state.opponent_chat or [])])
        ours, theirs = history.parse_history(state.observation, legal)
        claims = _CLAIMS.setdefault(gid, {"pending": None, "hits": 0, "total": 0})
        self._score_claim(claims, theirs)
        claims["pending"] = history.claimed_move(state.opponent_chat, legal)

        prediction, conf, method = patterns.predict_next(theirs, legal, MIN_HISTORY)
        if claims["total"] >= 3 and claims["hits"] / claims["total"] >= 0.75 and claims["pending"]:
            prediction, conf, method = claims["pending"], 0.7, "reliable-claim"   # a claim that has proven true
        action, reason = self._choose(state, legal, ours, theirs, prediction, conf)
        backup = random.Random(f"{gid}|{state.turn}|b").choice([a for a in legal if a != action] or legal or ["pass"])
        # the chat can never choose our move: an echoed suggestion needs a statistical reason (EV)
        res = guard.guard_action(action, backup, legal or None, monitor, reason, None, (), action)
        intent, family = self._tone(monitor, state)
        chat = filter_out(intents.compose(intent, family, f"{gid}|{state.turn}"), None)
        monitor.consume()
        print(f"read_opponent: {res.action!r} pred={prediction} conf={conf:.2f} via={method} guard={res.why} "
              f"{time.monotonic() - t0:.3f}s", file=sys.stderr, flush=True)
        return Decision(res.action, chat, "strategy" if not res.changed else "fallback")

    def _blotto(self, state):
        """Colonel Blotto: predictor + best response (blotto.py). The opponent's chat feeds the signals; a claimed allocation is
        believed only after it proved true at least 3 times out of 4. The chat can never choose our allocation."""
        gid = str(state.game_id)
        monitor = _MONITORS.setdefault(gid, ChatMonitor())
        monitor.update([{"from": "opponent", "text": t} for t in (state.opponent_chat or [])])
        n = blotto.parse_setup(state.rules, state.observation)["fields"]
        _ours, theirs = blotto.parse_history(state.observation, n)
        claim = _BLOTTO.setdefault(gid, {"pending": None, "hits": 0, "total": 0})
        if claim["pending"] and theirs:
            claim["total"] += 1
            claim["hits"] += 1 if sum(abs(a - b) for a, b in zip(claim["pending"], theirs[-1])) <= 0.1 * max(1, sum(theirs[-1])) else 0
        claim["pending"] = blotto.claimed_allocation(state.opponent_chat, n)
        reliable = claim["pending"] if claim["total"] >= 3 and claim["hits"] / claim["total"] >= 0.75 else None
        rng = random.Random(f"{gid}|{state.turn}|{zlib.crc32(str(state.observation).encode('utf-8', 'replace'))}")
        action, how = blotto.decide(state.rules, state.observation, rng, reliable)
        line = chat.reply_line(state.opponent_chat or [], state.turn, state.rules, (state.artifacts or {}).get("forbidden_terms"), "bluff")
        monitor.consume()
        print(f"read_opponent: blotto {action!r} via={how}", file=sys.stderr, flush=True)
        return Decision(action, line or filter_out("", None), "strategy")

    @staticmethod
    def _score_claim(claims, theirs):
        """Did the opponent's last claim ("I will play rock") match what it then played?"""
        if claims["pending"] and theirs:
            claims["total"] += 1
            claims["hits"] += 1 if theirs[-1] == claims["pending"] else 0
        claims["pending"] = None

    @staticmethod
    def _choose(state, legal, ours, theirs, prediction, conf):
        """(action, reason). A counter-move when the prediction is clear, else the uniform Nash mix."""
        rng = random.Random(f"{state.game_id}|{state.turn}|{len(theirs)}")
        if not legal:
            return "pass", "OTHER"
        kind = history.game_kind(legal, state.rules)
        if kind == "dilemma":
            return history.dilemma_move(legal, ours, theirs, rng), "OTHER"
        if prediction and conf >= MIN_CONFIDENCE:
            counter = history.best_response(prediction, legal, kind, state.rules, state.seat)
            if counter in legal:
                return counter, "EV"
        return rng.choice(legal), "OTHER"

    @staticmethod
    def _tone(monitor, state):
        """Cold chat, chosen from public signals only (never from our move or the prediction)."""
        if monitor.new_probe or monitor.new_hostile:
            return "STONEWALL", ("probe" if monitor.new_probe else "pressure")
        if monitor.repeated_now and monitor.opponent_repeats:
            return "UNSETTLE", "repeat"
        rng = random.Random(f"{state.game_id}|{state.turn}|tone")
        return rng.choice(["MINIMAL", "MINIMAL", "MINIMAL", "UNSETTLE"]), "general"


STRATEGY = ReadOpponentStrategy()
