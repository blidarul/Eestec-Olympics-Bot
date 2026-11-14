"""pegs: code-breaking with (exact, partial) feedback, solved through M1's `deduce` (entropy guess, candidate filter).

Same keyword detection as precompute's `_deduce` (which runs first and makes the runner skip this one when it fired);
this entry gives the classic contract plus a direct `pegs_solve` tool. Certain only with one candidate left.
"""
import re

from solvers import catalog
from solvers.classic import ClassicSolver, register


def detect(rules, variant):
    from solvers.precompute import _LEN_RX, _LEN_W, _NOREP, _PEG_KW, _deduce_alphabet
    low = (rules or "").lower()
    if not re.search(r"secret|hidden|code|guess", low):
        return None
    if not (_PEG_KW.search(rules or "") or ("exact" in low and re.search(r"partial|misplaced|wrong (?:place|position)", low))):
        return None
    ml = _LEN_RX.search(rules or "")
    if not ml:
        return None
    n = ml.group(1).lower()
    length = int(n) if n.isdigit() else _LEN_W.get(n)
    alpha = _deduce_alphabet(low)
    if not length or alpha is None:
        return None
    return {"length": length, "alphabet": alpha, "repeat": not _NOREP.search(rules or "")}


def verify(params, sample):
    legal = sample.get("legal_actions")
    if not legal:
        return True                                  # free-text guesses: nothing to compare
    return all(len(re.sub(r"[^0-9A-Za-z]", "", str(a))) == params["length"] for a in legal[:20])


def solve(observation, legal, params, deadline):
    h = catalog.call("extract_history", {"text": observation}, deadline)
    hist = []
    if h.get("ok"):
        for e in h["result"].get("history") or []:
            if e.get("actor") in (None, "you") and e.get("value") is not None and e.get("feedback"):
                g = str(e["value"])
                if g.isdigit() and len(g) < params["length"]:
                    g = g.zfill(params["length"])
                hist.append({"guess": g, "feedback": str(e["feedback"])})
    r = catalog.call("deduce_next", {"model": "pegs", "params": params, "history": hist[-60:], "mode": "entropy"}, deadline)
    if not r.get("ok"):
        return {"move": None, "value": None, "why": "deduce failed: %s" % (r.get("error"),), "proven": False}
    res = r["result"]
    if res.get("contradictory_history") or not res.get("candidates"):
        return {"move": None, "value": None, "why": "history unreadable", "proven": False}
    text = res.get("next_guess_text")
    move = None
    if legal:
        n = re.sub(r"[^0-9a-z]", "", str(text).lower())
        for a in legal:
            if n and n in re.sub(r"[^0-9a-z]", "", str(a).lower()):
                move = a
                break
    else:
        move = text
    return {"move": move, "value": None, "proven": bool(res.get("certain") and move is not None),
            "why": "%d candidates left; best guess %s" % (res["candidates"], text)}


register(ClassicSolver("pegs", detect, verify, solve))
