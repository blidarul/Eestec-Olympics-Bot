"""subtraction: heaps with an allowed-removal set (any count, a list, or a range), normal or misere play.

Normal play: Grundy values (xor over heaps). Misere or when the xor shortcut does not apply: exact memo search
on the sorted heap tuple (small positions only). Certain only when the position is a win and the move maps to
exactly one legal action.
"""
import re
import time

from solvers.classic import ClassicSolver, register

MAX_HEAP = 400
_UNIT = r"(?:stones?|sticks?|objects?|items?|coins?|matches|tokens?|counters?|pebbles?|chips?|beans?|cards?)"
_LIST = re.compile(r"(?:remove|take|pick|draw|subtract)s?\s+(?:exactly\s+|either\s+)?((?:\d+\s*(?:,\s*|\s+or\s+|\s+and\s+|\s*/\s*)\s*)+\d+)",
                   re.I)
_RANGE = re.compile(r"(?:remove|take|pick|draw)s?\s+(?:between\s+)?(\d+)\s*(?:to|-|and|through)\s*(\d+)", re.I)
_MAX = re.compile(r"(?:at most|up to|no more than|maximum of|max)\s*(\d+)", re.I)
_MIS = re.compile(r"mis[eè]re|(?:takes?|taking|removes?|picks?|draws?)[^.]{0,30}last[^.]{0,30}\b(?:loses?|loss|wrong)\b|"
                  r"last (?:player|one|stone|object|item|coin|match)[^.]{0,30}\b(?:loses?|loss)\b", re.I)


def detect(rules, variant):
    low = (rules or "").lower()
    if not re.search(r"\b(?:heaps?|piles?|stacks?|%s)\b" % _UNIT, low):
        return None
    if not re.search(r"\b(?:remove|take|pick|draw|subtract)\b", low):
        return None
    if not re.search(r"\blast\b|\bcannot move\b|\bno (?:moves|stones|objects|items)\b|\bempty\b", low):
        return None
    removals = "any"
    m = _LIST.search(rules)
    if m:
        removals = sorted({int(x) for x in re.findall(r"\d+", m.group(1))})
    else:
        m = _RANGE.search(rules)
        if m and int(m.group(1)) <= int(m.group(2)) <= 60:
            removals = list(range(int(m.group(1)), int(m.group(2)) + 1))
        else:
            m = _MAX.search(rules)
            if m and 1 <= int(m.group(1)) <= 60:
                removals = list(range(1, int(m.group(1)) + 1))
    if removals != "any" and (not removals or min(removals) < 1):
        return None
    return {"removals": removals, "misere": bool(_MIS.search(rules))}


def _state(observation):
    """-> (heaps, first_label, single) or None."""
    from solvers.precompute import _heaps
    heaps, first = _heaps(observation)
    if heaps:
        return heaps, first, False
    nums = re.findall(r"(\d{1,3})\s+%s\b|%s\s*(?:left|remaining|remain)\s*[:=]?\s*(\d{1,3})|(?:remaining|left)\s*[:=]\s*(\d{1,3})" %
                      (_UNIT, _UNIT), observation or "", re.I)
    vals = [int(x) for t in nums for x in t if x]
    if len(set(vals)) == 1 or (vals and len(vals) == 1):
        return [vals[0]], None, True
    return None


def _grundy_table(n, removals):
    g = [0] * (n + 1)
    for i in range(1, n + 1):
        seen = {g[i - s] for s in removals if s <= i}
        v = 0
        while v in seen:
            v += 1
        g[i] = v
    return g


def _opts(n, removals):
    return range(1, n + 1) if removals == "any" else [s for s in removals if s <= n]


def _search_win(heaps, removals, misere, deadline):
    """Exact win test for the player to move; returns (wins, winning moves [(heap_idx, remove)])."""
    memo = {}

    def win(state):
        if state in memo:
            return memo[state]
        if time.monotonic() > deadline:
            raise TimeoutError
        total = sum(state)
        if total == 0:
            memo[state] = bool(misere)           # normal: mover cannot move and loses; misere: previous took last
            return memo[state]
        res = False
        for i, h in enumerate(state):
            if i and state[i] == state[i - 1]:
                continue
            for r in _opts(h, removals):
                ns = tuple(sorted(state[:i] + (h - r,) + state[i + 1:]))
                if not win(ns):
                    res = True
                    break
            if res:
                break
        memo[state] = res
        return res

    start = tuple(sorted(heaps))
    wins = win(start)
    moves = []
    for i, h in enumerate(heaps):
        for r in _opts(h, removals):
            rest = list(heaps)
            rest[i] = h - r
            if not win(tuple(sorted(rest))):
                moves.append((i, r))
    return wins, moves


def analyse(heaps, params, deadline):
    removals, misere = params["removals"], params["misere"]
    if any(h > MAX_HEAP for h in heaps):
        return None
    if not misere:
        n = max(heaps)
        g = _grundy_table(n, list(range(1, n + 1)) if removals == "any" else removals)
        if removals == "any":
            g = list(range(n + 1))                           # Grundy of a plain heap is its size
        x = 0
        for h in heaps:
            x ^= g[h]
        moves = []
        for i, h in enumerate(heaps):
            for r in _opts(h, removals):
                if x ^ g[h] ^ g[h - r] == 0:
                    moves.append((i, r))
        return {"wins": x != 0, "moves": moves, "grundy_xor": x}
    try:
        w, moves = _search_win(heaps, removals, True, deadline)
    except (TimeoutError, RecursionError):
        return None
    return {"wins": w, "moves": moves}


def _action_for(move, heaps, first, single, legal):
    hi, rem = move
    label = hi + (first if first is not None else 1)
    hits = []
    for a in legal:
        t = str(a)
        nums = [int(x) for x in re.findall(r"\d+", t)]
        if single:
            if nums == [rem]:
                hits.append(a)
        elif len(nums) == 2:
            m1 = re.search(r"(\d+)\D+?(?:from|of|in|off)\D{0,8}?(\d+)", t, re.I)
            pair = (int(m1.group(2)), int(m1.group(1))) if m1 else (nums[0], nums[1])
            offs = [first] if first is not None else [1, 0]
            if any(pair == (hi + o, rem) for o in offs):
                hits.append(a)
    return hits[0] if len(hits) == 1 else None


def verify(params, sample):
    obs, legal = sample.get("observation"), sample.get("legal_actions")
    if not isinstance(obs, str):
        return False
    st = _state(obs)
    if not st:
        return False
    heaps, first, single = st
    if not legal:
        return True
    # every legal action must be a move of this model
    removals = params["removals"]
    ok = 0
    for a in legal:
        nums = [int(x) for x in re.findall(r"\d+", str(a))]
        if not nums or len(nums) > 2:
            return False
        rem = nums[0] if single or len(nums) == 1 else None
        if rem is not None and removals != "any" and rem not in removals:
            return False
        ok += 1
    return ok > 0


def solve(observation, legal, params, deadline):
    st = _state(observation)
    if not st:
        return {"move": None, "value": None, "why": "heaps not recognised", "proven": False}
    heaps, first, single = st
    a = analyse(heaps, params, deadline)
    if a is None:
        return {"move": None, "value": None, "why": "position too large", "proven": False}
    if not a["wins"]:
        return {"move": None, "value": -1, "why": "losing position: any move loses against perfect play "
                "(take the smallest amount and hope)", "proven": False}
    move, why = None, "winning move: heap %d, remove %d" % (a["moves"][0][0] + (first if first is not None else 1),
                                                          a["moves"][0][1])
    if legal:
        hits = {_action_for(m, heaps, first, single, legal) for m in a["moves"]} - {None}
        if len(hits) >= 1:
            move = sorted(hits)[0] if len(hits) > 1 else next(iter(hits))
    return {"move": move, "value": 1, "why": why, "proven": move is not None}


register(ClassicSolver("subtraction", detect, verify, solve))
