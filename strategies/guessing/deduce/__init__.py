"""guessing/deduce: candidate elimination with a verified feedback model (rules 6.4, 6.5-6.7, 6.3).

Used only for the guessing family when prepare() produced a VERIFIED feedback model (model.py). Every turn:
  1. history = extract_history(observation); candidates = secrets consistent with all (guess, feedback) pairs,
  2. guess = the candidate-set split with the best worst case (solvers/deduction.py), never a repeat,
  3. chat = a short line about THAT decision (how many candidates remain, 6.4), through hooks.filter_out; the line never mentions our
     own secret (6.3). The opponent's chat is wrapped as untrusted data (hooks.wrap_untrusted, 6.5-6.7) and cannot
     change the guess: it cannot be verified, the feedback can.
  4. no candidate left (the feedback contradicts the model) or any error -> core/generic with the repeat safety net.
"""
import time
import traceback

from core import hooks
from core.registry import family_of
from strategies.base import Decision, TurnState
from strategies.guessing.deduce import builtin
from strategies.guessing.deduce import model as fm
from strategies.guessing.deduce.prepare import prepare as _prepare

_CACHE = {}  # (match_id, game_index, game_id) -> (history tuple, candidates)

# Chat lines tied to THIS decision (how far the search is), short and without digits: chat/ replaces lines with digits or
# strategy words by neutral fillers, which would cut the link between move and chat (6.4).
WIDE = ("Working through it.", "Hm. Wide open.", "Unsurprising.")
MID = ("Getting closer.", "Working through it.", "Getting there.")
NEAR = ("Closing in.", "Nearly there.", "Few options remain.")
LAST = ("Found it.",)


def _line(left, total, turn):
    bank = LAST if left <= 1 else NEAR if left <= 6 else MID if left * 4 <= total else WIDE
    return bank[(turn or 0) % len(bank)]


def _prepared(art):
    p = (art or {}).get("prepared")
    d = p.get("deduce") if isinstance(p, dict) else None
    return d if isinstance(d, dict) and d.get("verified") and isinstance(d.get("code"), str) else None


class Deduce:
    name = "deduce"

    def prepare(self, rules, variant, llm, deadline):
        return _prepare(rules, variant, llm, deadline)

    def matches(self, rules, artifacts):
        if family_of(artifacts) != "guessing":
            return 0.0
        return 0.9 if _prepared(artifacts) or builtin.detect(rules) is not None else 0.0

    def decide(self, state: TurnState) -> Decision:
        try:
            d = self._decide(state)
            if d is not None:
                return d
        except Exception:
            traceback.print_exc()
        return self._generic(state, "deduction failed or no candidate left")

    def _generic(self, state, why):
        from core.generic import STRATEGY as generic
        d = generic.decide(state)
        d.info = dict(d.info or {}, tool="model", reason=why + " -> core/generic")
        return d

    def _decide(self, state):
        art = state.artifacts or {}
        spec = _prepared(art)
        variant = dict(state.variant or {})
        variant["rules"] = state.rules
        if spec:
            m, sha = fm.get_model(spec["code"]), spec["sha"]
        else:  # no verified model-written code: a built-in feedback model detected from the rules (G2)
            m = builtin.detect(state.rules, variant)
            if m is None:
                return None
            sha = f"builtin:{m.kind}:{m.lo}:{m.hi}"
        hooks.wrap_untrusted(state.opponent_chat)  # untrusted data: seen by the chat monitor, never obeyed (6.5-6.7)
        space = _space(m, sha, variant)
        hist = m.history(state.observation)
        key = (state.match_id, state.game_index, state.game_id)
        old = _CACHE.get(key)
        if old and len(old[0]) <= len(hist) and tuple(hist[:len(old[0])]) == old[0]:
            cands, new = old[1], hist[len(old[0]):]
        else:
            cands, new = space, hist
        for g, fb in new:
            cands = [c for c in cands if m.feedback(c, g) == fb]
        if len(_CACHE) > 20:
            _CACHE.clear()
        _CACHE[key] = (tuple(hist), cands)
        sent = {a for a in (state.my_actions or [])}
        tried = {g for g, _ in hist}
        cands = [c for c in cands if c not in tried and m.format(c) not in sent]
        if not cands:
            return None
        g = fm.choose_guess(m, cands, min(state.deadline - 1.0, time.monotonic() + 3.0))
        action = m.format(g)
        legal = state.legal_actions
        if legal and action not in legal:
            return None
        chat = hooks.filter_out(_line(len(cands), len(space), state.turn), art.get("forbidden_terms"))
        return Decision(action, chat, "strategy", {
            "tool": "deduction", "candidates_left": len(cands),
            "reason": f"{len(cands)} candidates left, best worst-case split"})


_SPACES = {}


def _space(m, sha, variant):
    k = (sha, str(variant.get("label", "")), hash(str(variant.get("rules", ""))))
    s = _SPACES.get(k)
    if s is None:
        if len(_SPACES) > 6:
            _SPACES.clear()
        s = _SPACES[k] = m.space(variant)
    return s


STRATEGY = Deduce()
