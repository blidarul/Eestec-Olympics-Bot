"""dice_race: roll/hold games to a target (a bust face loses the turn total).

Exact table (solvers/data/dice_race_t<T>_d<F>_b<B>.json, made by solvers/classic/dice_table.py) when the parameters
match a shipped file: hold when the turn total reaches hold_at[my][opp]. Otherwise a near-optimal rule
(hold at 20 or when the target is reached; keep rolling when the opponent is close). Certain only from the table.
"""
import glob
import json
import os
import re

from solvers.classic import ClassicSolver, register

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_TABLES = {}
_NUM = {"one": 1, "two": 2, "three": 3}


def _table(target, faces, bust):
    key = (target, faces, bust)
    if key not in _TABLES:
        t = None
        try:
            p = os.path.join(_DATA, "dice_race_t%d_d%d_b%d.json" % key)
            if os.path.exists(p):
                with open(p) as fh:
                    t = json.load(fh)
        except Exception:  # noqa: BLE001
            t = None
        _TABLES[key] = t
    return _TABLES[key]


def detect(rules, variant):
    low = (rules or "").lower()
    if not re.search(r"\broll", low) or not re.search(r"\b(?:hold|bank|stop|keep your)\b", low):
        return None
    tm = re.search(r"(?:reach|first to|target of|race to|score of|total of|at least|or more|to)\s*(\d{2,4})\s*(?:points?|or more|\b)", low)
    if not tm:
        return None
    target = int(tm.group(1))
    if not 10 <= target <= 1000:
        return None
    if not re.search(r"\b(?:lose|loses|lost|forfeit|zero|nothing|0)\b", low):
        return None
    multi = bool(re.search(r"\b(?:two|2|three|3|\d+)\s+(?:six-sided\s+|fair\s+)?dice\b|\bdoubles?\b|\b[2-9]d\d+\b", low))
    fm = re.search(r"\bd(\d{1,3})\b|(\d{1,3})[- ]sided", low)
    faces = int(next(g for g in fm.groups() if g)) if fm else 6
    bm = re.search(r"(?:rolls?|roll of|rolling|shows?|is)\s+(?:a\s+)?(\d{1,3})\b[^.]{0,60}(?:lose|loses|forfeit|nothing|bust)", low)
    bust = int(bm.group(1)) if bm else 1
    if not 1 <= bust <= faces:
        return None
    return {"target": target, "faces": faces, "bust": bust, "multi": multi}


def _read(observation):
    o = observation or ""
    me = re.search(r"\byour\s+(?:total\s+|current\s+|banked\s+|game\s+)?(?:score|points|total)\s*(?:is|:|=)?\s*(\d+)", o, re.I)
    op = re.search(r"\b(?:opponent(?:'s)?|their)\s+(?:total\s+|current\s+|banked\s+|game\s+)?(?:score|points|total)\s*(?:is|:|=)?\s*(\d+)",
                   o, re.I)
    tt = re.search(r"\b(?:turn\s+total|this\s+turn|current\s+turn|turn\s+points|unbanked|pending|at\s+risk|turn\s+score)\D{0,15}?(\d+)",
                   o, re.I)
    if not (me and op):
        return None
    return int(me.group(1)), int(op.group(1)), int(tt.group(1)) if tt else 0


def _actions(legal):
    roll = [a for a in legal if re.search(r"roll", str(a), re.I)]
    hold = [a for a in legal if re.search(r"hold|bank|stop|pass|keep", str(a), re.I)]
    return (roll[0] if len(roll) == 1 else None), (hold[0] if len(hold) == 1 else None)


def verify(params, sample):
    obs, legal = sample.get("observation"), sample.get("legal_actions")
    if not isinstance(obs, str) or _read(obs) is None:
        return False
    if not legal:
        return True
    roll, hold = _actions(legal)
    return roll is not None and (hold is not None or _read(obs)[2] == 0 and len(legal) == 1)


def _rule(i, j, k, target):
    if i + k >= target:
        return "hold", 1.0
    thr = 20
    if j >= target - 20:                       # opponent can win next turn: keep rolling
        thr = max(thr, min(target - i, 40))
    return ("hold" if k >= thr else "roll"), 0.0


def solve(observation, legal, params, deadline):
    st = _read(observation)
    if not st:
        return {"move": None, "value": None, "why": "scores not recognised", "proven": False}
    i, j, k = st
    target = params["target"]
    t = None if params.get("multi") else _table(target, params["faces"], params["bust"])
    if t is not None and i < target and j < target and k < target - i + 1:
        want = "hold" if (k > 0 and k >= t["hold_at"][i][j]) or i + k >= target else "roll"
        src = "exact table"
        proven = True
    else:
        want, _ = _rule(i, j, k, target)
        src = "rule of thumb (hold at 20 or the target)"
        proven = False
    if k == 0 and want == "hold":
        want = "roll"                           # holding 0 changes nothing
    roll, hold = _actions(legal or [])
    move = (roll if want == "roll" else hold) if legal else None
    why = "%s: %s with %d banked, opponent %d, turn total %d" % (src, want, i, j, k)
    if legal and move is None:
        proven = False
    return {"move": move, "value": None, "why": why, "proven": proven and move is not None}


register(ClassicSolver("dice_race", detect, verify, solve))
