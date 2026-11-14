"""kuhn_nash: equilibrium table for the 3-card, one-bet poker structure (cards 1<2<3, ante 1, one bet of 1).

Equilibrium family with alpha = 1/3: first player: low card bets 1/3 (else checks), middle checks (calls a bet with 2/3),
high bets (else checks, then calls). Second player: high always bets/calls, middle checks / calls 1/3, low bluffs 1/3 /
folds. Mixed actions are sampled with a seed from the observation; only dominant actions are proven.
"""
import hashlib
import random
import re

from solvers.classic import ClassicSolver, register

ALPHA = 1.0 / 3.0
_RANK = {"j": 1, "jack": 1, "q": 2, "queen": 2, "k": 3, "king": 3, "1": 1, "2": 2, "3": 3}
_CARD = re.compile(r"\b(?:your|my|you(?: are|'re)? (?:hold|holding|have|dealt|got))\b[^.\n]{0,25}?\b(jack|queen|king|[jqk]|[123])\b", re.I)
_ROUND = re.compile(r"\b(?:new (?:hand|round|game)|hand \d+|round \d+|dealt|deal)\b", re.I)
_ACT = re.compile(r"\b(check|pass|bet|call|fold|raise)\b", re.I)


def detect(rules, variant):
    low = (rules or "").lower()
    if re.search(r"community|board card|flop|two rounds|second round of betting|\braise", low):
        return None
    three = re.search(r"\b(?:three|3)[- ]cards?\b|\b(?:jack|j)\W+(?:queen|q)\W+(?:and\W+)?(?:king|k)\b|cards? (?:1, 2,? (?:and )?3|j, q,? (?:and )?k)", low)
    if not (three and re.search(r"\bante[sd]?\b|each player (?:puts|pays|posts)|one chip", low)):
        return None
    if not (re.search(r"\b(?:check|pass)\b", low) and re.search(r"\bbet\b", low) and re.search(r"\bfold\b", low)):
        return None
    return {"alpha": ALPHA}


def _kind(a):
    t = str(a).lower()
    for k in ("fold", "call", "bet", "check", "pass", "raise"):
        if k in t:
            return {"pass": "check", "raise": "bet"}.get(k, k)
    return None


def verify(params, sample):
    legal = sample.get("legal_actions")
    if not legal:
        return False
    kinds = {_kind(a) for a in legal}
    return None not in kinds and (kinds <= {"check", "bet"} or kinds <= {"fold", "call"})


def _seq(observation):
    text = observation or ""
    last = None
    for m in _ROUND.finditer(text):
        last = m.end()
    tail = text[last:] if last is not None else text
    return [{"pass": "check", "raise": "bet"}.get(m.group(1).lower(), m.group(1).lower()) for m in _ACT.finditer(tail)]


def _probs(card, legal_kinds, seq, a):
    """-> dict kind -> prob of the equilibrium action mix, and the set of dominant (proven) kinds."""
    if "fold" in legal_kinds:                                         # facing a bet
        if card == 3:
            return {"call": 1.0}, True
        if card == 1:
            return {"fold": 1.0}, True
        after_own_check = "check" in seq[:-1]
        c = a + 1.0 / 3.0 if after_own_check else 1.0 / 3.0
        return {"call": c, "fold": 1 - c}, False
    if seq and seq[-1] == "check":                                    # second player after a check
        if card == 3:
            return {"bet": 1.0}, True
        return ({"check": 1.0}, False) if card == 2 else ({"bet": 1.0 / 3.0, "check": 2.0 / 3.0}, False)
    if card == 3:                                                     # first player
        return {"bet": 3 * a, "check": 1 - 3 * a}, False
    if card == 2:
        return {"check": 1.0}, False
    return {"bet": a, "check": 1 - a}, False


def solve(observation, legal, params, deadline):
    ms = list(_CARD.finditer(observation or ""))
    card = _RANK.get(ms[-1].group(1).lower()) if ms else None
    if card is None:
        return {"move": None, "value": None, "why": "own card not found", "proven": False}
    kinds = {_kind(a) for a in legal or []}
    seq = _seq(observation)
    probs, dominant = _probs(card, kinds, seq, params.get("alpha", ALPHA))
    probs = {k: p for k, p in probs.items() if p > 1e-9 and k in kinds}
    if not probs:
        return {"move": None, "value": None, "why": "no matching action", "proven": False}
    rng = random.Random(int(hashlib.sha1((observation or "").encode("utf-8", "replace")).hexdigest()[:12], 16))
    tot = sum(probs.values())
    x, acc, pick = rng.random() * tot, 0.0, None
    for k, p in sorted(probs.items()):
        acc += p
        pick = k
        if x <= acc:
            break
    move = next(a for a in legal if _kind(a) == pick)
    mix = ", ".join("%s %.0f%%" % (k, 100 * p / tot) for k, p in sorted(probs.items()))
    return {"move": move, "value": None, "proven": bool(dominant and len(probs) == 1),
            "why": "equilibrium mix with card %d: %s -> %s" % (card, mix, pick)}


register(ClassicSolver("kuhn", detect, verify, solve))
