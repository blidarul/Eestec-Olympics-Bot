"""kinrow: k-in-a-row on any board, optional gravity (drop into a column).

Exact alpha-beta with memo when empty cells <= 12 (value is then proven); otherwise priority rules:
win > block win > make double threat > block double threat > best line score. Parameters, not game names.
"""
import re
import time

from solvers import catalog
from solvers.classic import ClassicSolver, register

EXACT_EMPTY = 12
_GRAV = re.compile(r"\b(?:drop|dropp\w*|gravity|falls?|fall to|lowest (?:empty|free|available)|slides? down|"
                   r"column to (?:drop|play)|choose a column|pick a column)\b", re.I)
_DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))


def detect(rules, variant):
    from solvers.precompute import _find_k
    k = _find_k(rules or "", variant or {})
    if k is None:
        return None
    low = (rules or "").lower()
    if not re.search(r"\b(?:board|grid|cell|square|column|row)s?\b", low):
        return None
    gravity = bool(variant.get("gravity")) if isinstance(variant, dict) and "gravity" in variant else bool(_GRAV.search(low))
    return {"k": k, "gravity": gravity}


def _parse(observation, params, deadline):
    """-> (grid_dict, cells, rows, cols, players, empty, me) or None."""
    g = catalog.call("extract_grid", {"text": observation}, deadline)
    if not (g.get("ok") and g["result"].get("found") and g["result"].get("grids")):
        return None
    grid = dict(g["result"]["grids"][0])
    rows_s = list(grid["rows"])
    while len(rows_s) > 2 and _label_row(rows_s[-1]):
        rows_s.pop()
    while len(rows_s) > 2 and _label_row(rows_s[0]):
        rows_s.pop(0)
    grid["rows"] = rows_s
    syms = {}
    for row in rows_s:
        for ch in row:
            syms[ch] = syms.get(ch, 0) + 1
    empty = next((e for e in (".", "-", "_", " ", "0", "·") if e in syms), None)
    if empty is None:
        return None
    players = [s for s in syms if s != empty]
    if len(players) == 1:
        return grid, [list(r) for r in rows_s], players, empty
    if len(players) != 2:
        return None
    return grid, [list(r) for r in rows_s], players, empty


def _label_row(row):
    return len(row) >= 4 and len(set(row)) == len(row) and (row.isdigit() or row.isalpha())


def _me(observation, variant, players):
    from solvers.precompute import _my_symbol
    return _my_symbol(observation, variant or {}, players)


def _bottom(cells, empty):
    """'last' if stones rest on the last row (usual), 'first' if on the first, None if not gravity-consistent."""
    rows, cols = len(cells), len(cells[0])
    for side in ("last", "first"):
        ok = True
        for c in range(cols):
            col = [cells[r][c] for r in (range(rows - 1, -1, -1) if side == "last" else range(rows))]
            seen_empty = False
            for ch in col:
                if ch == empty:
                    seen_empty = True
                elif seen_empty:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return side
    return None


def _wins(cells, r, c, p, k):
    rows, cols = len(cells), len(cells[0])
    for dr, dc in _DIRS:
        n = 1
        for s in (1, -1):
            rr, cc = r + dr * s, c + dc * s
            while 0 <= rr < rows and 0 <= cc < cols and cells[rr][cc] == p:
                n += 1
                rr += dr * s
                cc += dc * s
        if n >= k:
            return True
    return False


def _moves(cells, empty, gravity, bottom):
    rows, cols = len(cells), len(cells[0])
    if not gravity:
        return [(r, c) for r in range(rows) for c in range(cols) if cells[r][c] == empty]
    out = []
    for c in range(cols):
        rng = range(rows - 1, -1, -1) if bottom == "last" else range(rows)
        for r in rng:
            if cells[r][c] == empty:
                out.append((r, c))
                break
    return out


class _Timeout(Exception):
    pass


def _exact(cells, empty, gravity, bottom, k, me, opp, deadline):
    """Negamax from `me` to move. Returns (value, best move) value in {1, 0, -1}; raises _Timeout."""
    memo = {}
    nodes = [0]

    def key(turn):
        return ("".join("".join(r) for r in cells), turn)

    def go(turn, other):
        mv = _moves(cells, empty, gravity, bottom)
        if not mv:
            return 0, None
        kk = key(turn)
        if kk in memo:
            return memo[kk]
        nodes[0] += 1
        if (nodes[0] & 255) == 0 and time.monotonic() > deadline:
            raise _Timeout
        best, bm = -2, None
        # try immediate wins first
        for r, c in mv:
            cells[r][c] = turn
            w = _wins(cells, r, c, turn, k)
            cells[r][c] = empty
            if w:
                memo[kk] = (1, (r, c))
                return memo[kk]
        for r, c in mv:
            cells[r][c] = turn
            v, _ = go(other, turn)
            cells[r][c] = empty
            v = -v
            if v > best:
                best, bm = v, (r, c)
                if best == 1:
                    break
        memo[kk] = (best, bm)
        return memo[kk]

    return go(me, opp)


def _threats(cells, empty, mv, p, k):
    """Cells where p would win next (among the playable moves mv)."""
    out = []
    for r, c in mv:
        cells[r][c] = p
        if _wins(cells, r, c, p, k):
            out.append((r, c))
        cells[r][c] = empty
    return out


def _line_score(cells, r, c, p, q, k, empty):
    """Sum over windows through (r,c) that contain no q: p-stones^2."""
    rows, cols = len(cells), len(cells[0])
    tot = 0
    for dr, dc in _DIRS:
        for off in range(k):
            r0, c0 = r - dr * off, c - dc * off
            r1, c1 = r0 + dr * (k - 1), c0 + dc * (k - 1)
            if not (0 <= r0 < rows and 0 <= c0 < cols and 0 <= r1 < rows and 0 <= c1 < cols):
                continue
            mine = 0
            bad = False
            for i in range(k):
                ch = cells[r0 + dr * i][c0 + dc * i]
                if ch == q:
                    bad = True
                    break
                if ch == p:
                    mine += 1
            if not bad:
                tot += (mine + 1) ** 2
    return tot


def _heuristic(cells, empty, gravity, bottom, k, me, opp):
    mv = _moves(cells, empty, gravity, bottom)
    w = _threats(cells, empty, mv, me, k)
    if w:
        return w[0], "immediate win"
    b = _threats(cells, empty, mv, opp, k)
    if b:
        return b[0], "block the opponent's win"
    # double threat for me: after the move I have >= 2 distinct winning cells next turn
    def future_threats(cells_, p, q, move):
        r, c = move
        cells_[r][c] = p
        mv2 = _moves(cells_, empty, gravity, bottom)
        t = _threats(cells_, empty, mv2, p, k)
        cells_[r][c] = empty
        return t, mv2

    mine2 = [m for m in mv if len(future_threats(cells, me, opp, m)[0]) >= 2]
    if mine2:
        return mine2[0], "creates a double threat"
    theirs2 = [m for m in mv if len(future_threats(cells, opp, me, m)[0]) >= 2]
    if theirs2:
        return theirs2[0], "blocks the opponent's double threat"
    rows, cols = len(cells), len(cells[0])
    cr, cc = (rows - 1) / 2.0, (cols - 1) / 2.0
    best = max(mv, key=lambda m: (_line_score(cells, m[0], m[1], me, opp, k, empty)
                                  + 0.9 * _line_score(cells, m[0], m[1], opp, me, k, empty),
                                  -abs(m[0] - cr) - abs(m[1] - cc)))
    return best, "best line score"


def _strip(t):
    return re.sub(r"^(?:[A-Za-z]+\s+)+", "", str(t))


def _styles(rows, cols, grid):
    rl, cl = grid.get("row_labels"), grid.get("col_labels")
    st = []
    if rl and cl and len(rl) == rows and len(cl) == cols:
        st.append(lambda r, c: "%s%s" % (rl[r], cl[c]))
        st.append(lambda r, c: "%s%s" % (cl[c], rl[r]))
    if cols <= 26:
        st.append(lambda r, c: chr(65 + c) + str(r + 1))
        st.append(lambda r, c: chr(65 + c) + str(rows - r))
    st += [lambda r, c: "%d,%d" % (r, c), lambda r, c: "%d,%d" % (r + 1, c + 1),
           lambda r, c: "%d,%d" % (c, r), lambda r, c: "%d,%d" % (c + 1, r + 1),
           lambda r, c: str(r * cols + c), lambda r, c: str(r * cols + c + 1)]
    return st


def _action_map(cells, empty, params, grid, legal, bottom):
    """(r, c) -> legal action for every playable move, or None when no naming style fits the legal set exactly."""
    from solvers.precompute import _norm
    mv = _moves(cells, empty, params["gravity"], bottom)
    rows, cols = len(cells), len(cells[0])
    if params["gravity"]:
        pp = dict(params)
        pp["_open_cols"] = sorted(c for _, c in mv)
        out = {m: _column_action(m[1], cols, grid, legal, pp) for m in mv}
        return out if None not in out.values() and set(out.values()) == set(legal) else None
    lnorm = {}
    for a in legal:
        for t in (_norm(a), _norm(_strip(a))):
            lnorm.setdefault(t, a)
    for st in _styles(rows, cols, grid):
        out = {m: lnorm.get(_norm(st(*m))) for m in mv}
        if None not in out.values() and set(out.values()) == set(legal) and len(set(out.values())) == len(mv):
            return out
    return None


def _column_action(c, cols, grid, legal, params):
    """Legal actions of a gravity game name a column (number or letter). Offset is inferred from the legal set."""
    keyed = []
    for a in legal:
        t = str(a)
        nums = re.findall(r"\d+", t)
        if len(nums) == 1:
            keyed.append((int(nums[0]), a))
        elif not nums:
            m = re.fullmatch(r"\W*(?:\w+\s+)?([A-Za-z])\W*", t)
            if m:
                keyed.append((ord(m.group(1).upper()) - 65, a))
    params_cols = params.get("_open_cols")
    if not keyed or len(keyed) != len(legal) or not params_cols:
        return None
    keyed.sort()
    if len(keyed) != len(params_cols):
        return None
    off = keyed[0][0] - params_cols[0]
    if any(keyed[i][0] - params_cols[i] != off for i in range(len(keyed))):
        return None
    for n, a in keyed:
        if n - off == c:
            return a
    return None


def _setup(observation, legal, params, variant, deadline):
    p = _parse(observation, params, deadline)
    if not p:
        return None
    grid, cells, players, empty = p
    if len(players) != 2:
        return None
    me = _me(observation, variant, players)
    if me is None:
        return None
    opp = players[0] if players[1] == me else players[1]
    bottom = _bottom(cells, empty) if params["gravity"] else None
    if params["gravity"] and bottom is None:
        return None
    return grid, cells, me, opp, empty, bottom


def verify(params, sample):
    obs, legal = sample.get("observation"), sample.get("legal_actions")
    if not isinstance(obs, str) or not isinstance(legal, list) or not legal:
        return False
    s = _setup(obs, legal, dict(params), {}, time.monotonic() + 1)
    if s is None:
        # symbol unknown: still verify the move mapping with a guessed player
        p = _parse(obs, params, time.monotonic() + 1)
        if not p or len(p[2]) != 2:
            return False
        grid, cells, players, empty = p
        bottom = _bottom(cells, empty) if params["gravity"] else None
        if params["gravity"] and bottom is None:
            return False
    else:
        grid, cells, me, opp, empty, bottom = s
    mv = _moves(cells, empty, params["gravity"], bottom)
    if not mv:
        return False
    return _action_map(cells, empty, params, grid, legal, bottom) is not None


def solve(observation, legal, params, deadline, variant=None):
    s = _setup(observation, legal, params, variant or {}, deadline)
    if s is None:
        return {"move": None, "value": None, "why": "board or player symbol not recognised", "proven": False}
    grid, cells, me, opp, empty, bottom = s
    mv = _moves(cells, empty, params["gravity"], bottom)
    if not mv:
        return {"move": None, "value": None, "why": "no moves", "proven": False}
    nempty = sum(row.count(empty) for row in cells)
    k = params["k"]
    move, value, why, proven = None, None, "", False
    if nempty <= EXACT_EMPTY:
        try:
            value, move = _exact([row[:] for row in cells], empty, params["gravity"], bottom, k, me, opp, deadline)
            proven = True
            why = {1: "proven win", 0: "proven draw", -1: "proven loss (best resistance)"}[value]
        except _Timeout:
            move = None
    if move is None:
        move, why = _heuristic(cells, empty, params["gravity"], bottom, k, me, opp)
        proven = why in ("immediate win",)
        value = 1 if proven else None
    amap = _action_map(cells, empty, params, grid, legal, bottom) if legal else None
    act = amap.get(move) if amap else None
    if legal and act is None:
        return {"move": None, "value": value, "why": why + " (move not mappable to a legal action)", "proven": False}
    # a forced block counts as certain: the opponent wins next turn otherwise
    return {"move": act, "value": value, "why": why, "proven": proven or why == "block the opponent's win"}


register(ClassicSolver("kinrow", detect, verify, solve))
