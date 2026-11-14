"""range_guess: plain numeric guessing with higher/lower feedback = binary search (M1's numeric model).

precompute's guessing detector already produces these facts; this wrapper makes the same answer available
through the classic contract (and is skipped by the runner when that detector fired).
"""
import re

import time

from solvers import catalog
from solvers.classic import ClassicSolver, register


def detect(rules, variant):
    from solvers.precompute import _find_range
    low = (rules or "").lower()
    if "guess" not in low or not re.search(r"higher|lower|too high|too low|greater|smaller", low):
        return None
    rng = _find_range(rules, variant or {})
    return {"lo": rng[0], "hi": rng[1]} if rng else None


def verify(params, sample):
    legal = sample.get("legal_actions")
    return legal is None or all(re.search(r"\d", str(a)) for a in legal[:5]) or not legal


def solve(observation, legal, params, deadline):
    from solvers.precompute import _fb
    h = catalog.call("extract_history", {"text": observation}, deadline)
    hist = []
    if h.get("ok"):
        for e in h["result"].get("history") or []:
            fb = _fb(e.get("feedback"))
            v = e.get("value")
            if e.get("actor") in (None, "you") and isinstance(v, int) and not isinstance(v, bool) and fb:
                hist.append({"guess": v, "feedback": fb})
    r = catalog.call("binary_search_next", {"lo": params["lo"], "hi": params["hi"], "history": hist[-60:]}, deadline)
    if not r.get("ok") or r["result"].get("found"):
        return {"move": None, "value": None, "why": "no guess", "proven": False}
    res = r["result"]
    g = str(res.get("next_guess"))
    move = None
    if legal:
        for a in legal:
            if re.fullmatch(r"\D*%s\D*" % re.escape(g), str(a)):
                move = a
                break
    else:
        move = g
    return {"move": move, "value": None, "why": "binary search: %s candidates left" % res.get("candidates"),
            "proven": res.get("candidates") == 1 and move is not None}


register(ClassicSolver("range_guess", detect, verify, solve))
