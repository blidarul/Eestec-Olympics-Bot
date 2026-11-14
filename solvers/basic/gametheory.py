"""Game-theory primitives (TOOLS_PLAN.md phase P4).

General tools (no game names, rule 10.7): plain data in, plain data out, stdlib only, no eval.
matrix_nash / sample_action / best_response / nim_analysis take JSON and are model-callable.
minimax_small and csp_backtrack take Python callables, so they are harness-only (not exported
to the model and never fed strings from the model or the opponent).
"""
import random
import time
from fractions import Fraction

from solvers.catalog import ToolError, ToolSpec, register

MAX_MATRIX = 30
LIST_CAP = 40


def _check_time(deadline):
    if time.monotonic() > deadline:
        raise ToolError("deadline exceeded")


def _fs(f):
    return str(Fraction(f))


def _dec(f):
    return float("%.6g" % float(f))


def _frac(x, label):
    if isinstance(x, bool):
        raise ToolError("%s must be a number" % label)
    try:
        return Fraction(str(x).strip())
    except (ValueError, ZeroDivisionError):
        raise ToolError("%s must be a number or fraction string, got %r" % (label, x))


_NUM = {"type": ["number", "string"]}
_MATRIX = {"type": "array", "minItems": 1, "maxItems": MAX_MATRIX,
           "items": {"type": "array", "minItems": 1, "maxItems": MAX_MATRIX, "items": _NUM},
           "description": "payoff matrix: rows = our actions, columns = opponent actions, entries = what WE get"}


def _matrix(raw):
    n = len(raw[0])
    if any(len(r) != n for r in raw):
        raise ToolError("all matrix rows must have the same length")
    return [[_frac(v, "payoff") for v in row] for row in raw]


# ---------------------------------------------------------------- matrix_nash

def _remove_dominated(A, rows, cols, deadline):
    """Iteratively drop weakly dominated rows (maximiser) and columns (minimiser); keeps one of equal lines."""
    changed = True
    while changed:
        changed = False
        _check_time(deadline)
        for i in list(range(len(rows))):
            if len(rows) == 1:
                break
            for k in range(len(rows)):
                if k != i and all(A[rows[k]][c] >= A[rows[i]][c] for c in cols) and (
                        any(A[rows[k]][c] > A[rows[i]][c] for c in cols) or k < i):
                    del rows[i]
                    changed = True
                    break
            if changed:
                break
        if changed:
            continue
        for j in list(range(len(cols))):
            if len(cols) == 1:
                break
            for l in range(len(cols)):
                if l != j and all(A[r][cols[l]] <= A[r][cols[j]] for r in rows) and (
                        any(A[r][cols[l]] < A[r][cols[j]] for r in rows) or l < j):
                    del cols[j]
                    changed = True
                    break
            if changed:
                break


def _solve_lp(B, deadline):
    """Zero-sum game with all entries of B > 0 (row player maximises).
    Returns (value, x over rows, y over cols) by exact simplex with Bland's rule."""
    m, n = len(B), len(B[0])
    # variables: y_0..y_{n-1}, slacks s_0..s_{m-1}; rows: B y + s = 1; objective: maximise sum y
    tab = [list(B[i]) + [Fraction(int(i == k)) for k in range(m)] + [Fraction(1)] for i in range(m)]
    obj = [Fraction(-1)] * n + [Fraction(0)] * m + [Fraction(0)]
    basis = [n + i for i in range(m)]
    while True:
        _check_time(deadline)
        col = next((j for j in range(n + m) if obj[j] < 0), None)      # Bland: lowest index
        if col is None:
            break
        best = None
        for i in range(m):
            if tab[i][col] > 0:
                ratio = tab[i][-1] / tab[i][col]
                if best is None or ratio < best[0] or (ratio == best[0] and basis[i] < basis[best[1]]):
                    best = (ratio, i)
        if best is None:
            raise ToolError("internal error: unbounded LP")
        r = best[1]
        piv = tab[r][col]
        tab[r] = [v / piv for v in tab[r]]
        for i in range(m):
            if i != r and tab[i][col] != 0:
                f = tab[i][col]
                tab[i] = [a - f * b for a, b in zip(tab[i], tab[r])]
        f = obj[col]
        obj = [a - f * b for a, b in zip(obj, tab[r])]
        basis[r] = col
    z = obj[-1]
    y = [Fraction(0)] * n
    for i, b in enumerate(basis):
        if b < n:
            y[b] = tab[i][-1]
    x = [obj[n + i] for i in range(m)]
    return 1 / z, [v / z for v in x], [v / z for v in y]


def matrix_nash(args, deadline):
    A = _matrix(args["matrix"])
    m, n = len(A), len(A[0])
    rows, cols = list(range(m)), list(range(n))
    _remove_dominated(A, rows, cols, deadline)
    lo = min(A[r][c] for r in rows for c in cols)
    shift = 1 - lo
    B = [[A[r][c] + shift for c in cols] for r in rows]
    v_shift, x_red, y_red = _solve_lp(B, deadline)
    value = v_shift - shift
    x = [Fraction(0)] * m
    y = [Fraction(0)] * n
    for r, p in zip(rows, x_red):
        x[r] = p
    for c, p in zip(cols, y_red):
        y[c] = p
    # exact self-check: each strategy guarantees the value against every pure reply
    if sum(x) != 1 or sum(y) != 1 or any(p < 0 for p in x + y):
        raise ToolError("internal error: invalid strategy")
    for j in range(n):
        if sum(x[i] * A[i][j] for i in range(m)) < value:
            raise ToolError("internal error: row strategy does not guarantee the value")
    for i in range(m):
        if sum(y[j] * A[i][j] for j in range(n)) > value:
            raise ToolError("internal error: column strategy does not hold the value")
    rl = args.get("row_labels") or ["row %d" % i for i in range(m)]
    cl = args.get("col_labels") or ["col %d" % j for j in range(n)]
    if len(rl) != m or len(cl) != n:
        raise ToolError("labels must match the matrix size (%d rows, %d columns)" % (m, n))

    def table(labels, probs):
        return [{"index": i, "label": labels[i], "p": _fs(p), "p_decimal": _dec(p)} for i, p in enumerate(probs) if p > 0]

    mine = table(rl, x)
    best = max(mine, key=lambda e: (Fraction(e["p"]), -e["index"]))
    return {"value": _fs(value), "value_decimal": _dec(value),
            "row_strategy": mine, "col_strategy": table(cl, y),
            "row_probs": [_dec(p) for p in x], "pure": len(mine) == 1,
            "kept_rows_after_dominance": len(rows), "kept_cols_after_dominance": len(cols),
            "explain": "Game value %s for us. Our optimal mix: %s." % (
                _fs(value), ", ".join("%s %.3g" % (e["label"], float(Fraction(e["p"]))) for e in mine[:8]))
            + (" (pure action)" if len(mine) == 1 else " Randomise with sample_action.") if best else ""}


register(ToolSpec(
    name="matrix_nash",
    summary="Zero-sum matrix game (rows = our actions, entries = our payoff): the optimal mixed strategies for both sides and the game value, exact. Use for simultaneous-move games (rock-paper-scissors style, bluff/call tables).",
    params={"type": "object",
            "properties": {"matrix": _MATRIX,
                           "row_labels": {"type": "array", "maxItems": MAX_MATRIX, "items": {"type": "string", "maxLength": 40}},
                           "col_labels": {"type": "array", "maxItems": MAX_MATRIX, "items": {"type": "string", "maxLength": 40}}},
            "required": ["matrix"]},
    fn=matrix_nash, families=("any",), model_callable=True, max_ms=3000))


# ---------------------------------------------------------------- sample_action

def sample_action(args, deadline):
    probs = [_frac(p, "prob") for p in args["probs"]]
    if any(p < 0 for p in probs):
        raise ToolError("probabilities must be >= 0")
    total = sum(probs, Fraction(0))
    if total <= 0:
        raise ToolError("probabilities sum to 0")
    labels = args.get("labels")
    if labels is not None and len(labels) != len(probs):
        raise ToolError("labels and probs must have the same length")
    rng = random.Random(args.get("seed", 0))
    u = Fraction(rng.random()) * total
    acc = Fraction(0)
    pick = max(i for i, p in enumerate(probs) if p > 0)
    for i, p in enumerate(probs):
        acc += p
        if u < acc and p > 0:
            pick = i
            break
    label = labels[pick] if labels else None
    return {"index": pick, "label": label, "p": _dec(probs[pick] / total),
            "explain": "Sampled action %s (probability %.3g, seed %s)." % (label if labels else pick, float(probs[pick] / total), args.get("seed", 0))}


register(ToolSpec(
    name="sample_action",
    summary="Pick one action at random from a mixed strategy (list of probabilities) with a seeded RNG, so the result is reproducible.",
    params={"type": "object",
            "properties": {"probs": {"type": "array", "minItems": 1, "maxItems": 200, "items": _NUM,
                                     "description": "probabilities (or weights) per action, in order"},
                           "labels": {"type": "array", "maxItems": 200, "items": {"type": "string", "maxLength": 60}},
                           "seed": {"type": "integer", "description": "RNG seed (default 0); use a different seed each turn"}},
            "required": ["probs"]},
    fn=sample_action, families=("any",), model_callable=True, max_ms=300))


# ---------------------------------------------------------------- best_response

def best_response(args, deadline):
    A = _matrix(args["matrix"])
    m, n = len(A), len(A[0])
    freq = [_frac(f, "frequency") for f in args["opponent_freq"]]
    if len(freq) != n:
        raise ToolError("opponent_freq needs %d entries (one per column), got %d" % (n, len(freq)))
    if any(f < 0 for f in freq):
        raise ToolError("frequencies must be >= 0")
    total = sum(freq, Fraction(0))
    if total <= 0:
        raise ToolError("opponent_freq sums to 0")
    freq = [f / total for f in freq]
    evs = [sum(A[i][j] * freq[j] for j in range(n)) for i in range(m)]
    best = max(range(m), key=lambda i: (evs[i], -i))
    rl = args.get("row_labels") or ["row %d" % i for i in range(m)]
    if len(rl) != m:
        raise ToolError("row_labels must have %d entries" % m)
    ties = [i for i in range(m) if evs[i] == evs[best]]
    return {"best_action": best, "label": rl[best], "ev": _fs(evs[best]), "ev_decimal": _dec(evs[best]),
            "ties": ties, "all_evs": [{"index": i, "label": rl[i], "ev_decimal": _dec(evs[i])} for i in range(m)][:LIST_CAP],
            "explain": "Best reply to the observed mix: %s (EV %.4g)." % (rl[best], float(evs[best]))}


register(ToolSpec(
    name="best_response",
    summary="Exploit an opponent: given our payoff matrix and how often the opponent played each column (counts or probabilities), return our best action and its expected value.",
    params={"type": "object",
            "properties": {"matrix": _MATRIX,
                           "opponent_freq": {"type": "array", "minItems": 1, "maxItems": MAX_MATRIX, "items": _NUM,
                                             "description": "opponent's frequency (counts or probabilities) for each column"},
                           "row_labels": {"type": "array", "maxItems": MAX_MATRIX, "items": {"type": "string", "maxLength": 40}}},
            "required": ["matrix", "opponent_freq"]},
    fn=best_response, families=("any",), model_callable=True, max_ms=500))


# ---------------------------------------------------------------- nim_analysis

MAX_HEAPS = 12
MAX_HEAP = 1000


def _grundy_table(limit, removals, deadline):
    g = [0] * (limit + 1)
    if removals is None:
        return list(range(limit + 1))
    for h in range(1, limit + 1):
        if h % 256 == 0:
            _check_time(deadline)
        seen = {g[h - s] for s in removals if s <= h}
        k = 0
        while k in seen:
            k += 1
        g[h] = k
    return g


def _misere_solver(removals, deadline, limit_states=300000):
    memo = {}

    def win(state):                       # True if the player to move wins (takes the last item = loses)
        if state in memo:
            return memo[state]
        if len(memo) > limit_states:
            raise ToolError("misere search too large for this removal set")
        if len(memo) % 512 == 0:
            _check_time(deadline)
        if not state:
            memo[state] = True            # previous player took the last item: mover wins
            return True
        res = False
        for idx, h in enumerate(state):
            if idx and state[idx - 1] == h:
                continue
            for s in removals:
                if s <= h:
                    new = list(state)
                    new[idx] = h - s
                    nxt = tuple(sorted(x for x in new if x))
                    if not win(nxt):
                        res = True
                        break
            if res:
                break
        memo[state] = res
        return res
    return win


def nim_analysis(args, deadline):
    heaps = args["heaps"]
    misere = args.get("misere", False)
    rem = args.get("removals", "any")
    if rem == "any":
        removals = None
    elif isinstance(rem, list) and rem and all(isinstance(s, int) and not isinstance(s, bool) and s >= 1 for s in rem):
        removals = sorted(set(rem))
    else:
        raise ToolError("removals must be \"any\" or a non-empty list of positive integers, e.g. [1,2,3]")
    if len(heaps) > MAX_HEAPS:
        raise ToolError("at most %d heaps" % MAX_HEAPS)
    if misere and removals is not None and sum(heaps) > 60:
        raise ToolError("misere with a removal set is solved by search: total size must be <= 60")
    top = max(heaps) if heaps else 0
    gt = _grundy_table(top, removals, deadline)
    grundy = [gt[h] for h in heaps]
    nim_sum = 0
    for g in grundy:
        nim_sum ^= g

    def moves():
        for i, h in enumerate(heaps):
            rs = range(1, h + 1) if removals is None else [s for s in removals if s <= h]
            for s in rs:
                yield i, s

    def mover_wins_after(i, s):
        """True if the position after the move is lost for the player who must move next."""
        new = list(heaps)
        new[i] -= s
        if not misere:
            x = 0
            for h in new:
                x ^= gt[h]
            return x == 0
        if removals is None:
            if max(new, default=0) >= 2:
                x = 0
                for h in new:
                    x ^= h
                return x == 0
            return sum(new) % 2 == 1
        return not solver(tuple(sorted(h for h in new if h)))

    solver = _misere_solver(removals, deadline) if misere and removals is not None else None
    good = []
    count = 0
    for i, s in moves():
        count += 1
        if count % 2048 == 0:
            _check_time(deadline)
        if mover_wins_after(i, s):
            good.append({"heap": i, "remove": s, "new_size": heaps[i] - s})
    # a player to move with no moves: normal play loses, misere play wins (the opponent took the last item)
    if not any(heaps):
        first_wins = misere
    else:
        first_wins = bool(good)
    res = {"grundy": grundy, "nim_sum": nim_sum, "misere": bool(misere), "first_player_wins": first_wins,
           "winning_moves": good[:LIST_CAP], "winning_move_count": len(good),
           "winning_move": good[0] if good else None}
    if first_wins and good:
        w = good[0]
        res["explain"] = "Winning: take %d from heap %d (heaps are 0-indexed), leaving %d." % (w["remove"], w["heap"], w["new_size"])
    elif first_wins:
        res["explain"] = "No items left: the player to move wins (misere)."
    else:
        res["explain"] = "Losing position for the player to move (nim-sum %d): any move loses against perfect play; make the smallest move and hope for a mistake." % nim_sum
    return res


register(ToolSpec(
    name="nim_analysis",
    summary="Nim and subtraction games: Grundy values, nim-sum and a winning move (or 'losing position') for heap sizes, with any removal size or a fixed set like [1,2,3], normal play (last item wins) or misere (last item loses).",
    params={"type": "object",
            "properties": {"heaps": {"type": "array", "minItems": 0, "maxItems": MAX_HEAPS,
                                     "items": {"type": "integer", "minimum": 0, "maximum": MAX_HEAP}},
                           "removals": {"type": ["string", "array"], "description": "\"any\" (default: take any positive number from one heap) or a list of allowed amounts such as [1,2,3]"},
                           "misere": {"type": "boolean", "description": "true if taking the last item LOSES; default false"}},
            "required": ["heaps"]},
    fn=nim_analysis, families=("any",), model_callable=True, max_ms=3000))


# ---------------------------------------------------------------- minimax_small (harness only)

class _Timeout(Exception):
    pass


def minimax_small(args, deadline):
    moves_fn, apply_fn, term_fn, val_fn = args["moves"], args["apply"], args["terminal"], args["value"]
    state = args["state"]
    max_depth = args.get("max_depth", 200)
    max_nodes = args.get("max_nodes", 2000000)
    for name, f in (("moves", moves_fn), ("apply", apply_fn), ("terminal", term_fn), ("value", val_fn)):
        if not callable(f):
            raise ToolError("%s must be a callable" % name)
    memo = {}
    nodes = [0]

    def negamax(s, depth):
        """Value for the player to move in s (value() is read from that player's side at terminal states)."""
        nodes[0] += 1
        if nodes[0] % 256 == 0 and time.monotonic() > deadline - 0.03:
            raise _Timeout
        if nodes[0] > max_nodes:
            raise _Timeout
        try:
            key = (s, depth)
            if key in memo:
                return memo[key]
        except TypeError:
            key = None
        if term_fn(s) or depth <= 0:
            v = val_fn(s)
        else:
            ms = list(moves_fn(s))
            if not ms:
                v = val_fn(s)
            else:
                v = max(-negamax(apply_fn(s, m), depth - 1) for m in ms)
        if key is not None:
            memo[key] = v
        return v

    if term_fn(state):
        return {"value": val_fn(state), "best_move": None, "complete": True, "nodes": 1,
                "explain": "State is terminal."}
    ms = list(moves_fn(state))
    if not ms:
        return {"value": val_fn(state), "best_move": None, "complete": True, "nodes": 1,
                "explain": "No moves available."}
    scored = []
    complete = True
    try:
        for m in ms:
            scored.append((-negamax(apply_fn(state, m), max_depth - 1), m))
    except _Timeout:
        complete = False
    except RecursionError:
        raise ToolError("game tree too deep for the Python stack: lower max_depth")
    if not scored:
        raise ToolError("no move was fully evaluated before the deadline")
    best_v, best_m = scored[0]
    for v, m in scored[1:]:
        if v > best_v:
            best_v, best_m = v, m
    return {"value": best_v, "best_move": best_m, "complete": complete, "nodes": nodes[0],
            "moves_evaluated": len(scored), "moves_total": len(ms),
            "move_values": [[str(m), v] for v, m in scored[:LIST_CAP]],
            "explain": "Best move %s with value %s for the player to move (%s, %d nodes)." % (
                best_m, best_v, "exact" if complete else "partial: %d of %d moves searched" % (len(scored), len(ms)), nodes[0])}


register(ToolSpec(
    name="minimax_small",
    summary="Harness-only: exact negamax with memoisation over callables moves(state), apply(state, move), terminal(state), value(state) (score for the player to move at a terminal state); returns best move and value.",
    params={"type": "object",
            "properties": {"state": {"description": "start state (hashable for memoisation)"},
                           "moves": {"description": "callable moves(state) -> list of moves"},
                           "apply": {"description": "callable apply(state, move) -> new state (pure: must not mutate state)"},
                           "terminal": {"description": "callable terminal(state) -> bool"},
                           "value": {"description": "callable value(state) -> number for the player to move in that state"},
                           "max_depth": {"type": "integer", "minimum": 1, "maximum": 500},
                           "max_nodes": {"type": "integer", "minimum": 1, "maximum": 10 ** 8}},
            "required": ["state", "moves", "apply", "terminal", "value"]},
    fn=minimax_small, families=("think_ahead",), model_callable=False, max_ms=2000))


# ---------------------------------------------------------------- csp_backtrack (harness only)

def csp_backtrack(args, deadline):
    domains = args["variables"]
    if not isinstance(domains, dict) or not domains:
        raise ToolError("variables must be a non-empty {name: [values]} dict")
    names = list(domains)
    cons = []
    for c in args.get("constraints") or []:
        scope, fn = c["vars"], c["check"]
        if not callable(fn):
            raise ToolError("constraint 'check' must be a callable")
        unknown = [v for v in scope if v not in domains]
        if unknown:
            raise ToolError("constraint mentions unknown variables: %s" % unknown)
        cons.append((tuple(scope), fn))
    for group in args.get("all_different") or []:
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                cons.append(((group[a], group[b]), lambda x, y: x != y))
    mode = args.get("mode", "solutions")
    cap = args.get("max_solutions", 100)
    # smallest domain first, then variables that appear in more constraints
    degree = {v: sum(v in s for s, _ in cons) for v in names}
    order = sorted(names, key=lambda v: (len(domains[v]), -degree[v]))
    pos = {v: i for i, v in enumerate(order)}
    by_last = {}
    for scope, fn in cons:
        by_last.setdefault(max(scope, key=pos.__getitem__) if scope else order[0], []).append((scope, fn))
    assign, sols = {}, []
    stats = {"count": 0, "nodes": 0, "stopped": None}

    def rec(i):
        if i == len(order):
            stats["count"] += 1
            if mode == "solutions" and len(sols) < cap:
                sols.append(dict(assign))
            if mode == "solutions" and stats["count"] >= cap:
                stats["stopped"] = "cap"
                return True
            return False
        v = order[i]
        for val in domains[v]:
            stats["nodes"] += 1
            if stats["nodes"] % 512 == 0 and time.monotonic() > deadline - 0.03:
                stats["stopped"] = "deadline"
                return True
            assign[v] = val
            if all(fn(*[assign[x] for x in scope]) for scope, fn in by_last.get(v, ())):
                if rec(i + 1):
                    return True
            del assign[v]
        return False

    rec(0)
    complete = stats["stopped"] is None
    res = {"count": stats["count"], "complete": complete, "stopped_by": stats["stopped"], "nodes": stats["nodes"]}
    if mode == "solutions":
        res["solutions"] = sols
    res["explain"] = "%s%d solution(s)%s." % ("" if complete else "At least ", stats["count"],
                                              "" if complete else " (search stopped: %s)" % stats["stopped"])
    return res


register(ToolSpec(
    name="csp_backtrack",
    summary="Harness-only: backtracking constraint solver over variables {name: domain}, constraints [{vars, check(*values)->bool}] and all_different groups; returns solutions up to a cap or just the count (deduction helper).",
    params={"type": "object",
            "properties": {"variables": {"type": "object", "description": "{name: list of possible values}"},
                           "constraints": {"type": "array", "maxItems": 5000,
                                           "items": {"type": "object", "required": ["vars", "check"]}},
                           "all_different": {"type": "array", "maxItems": 100, "items": {"type": "array"}},
                           "mode": {"type": "string", "enum": ["solutions", "count"]},
                           "max_solutions": {"type": "integer", "minimum": 1, "maximum": 100000}},
            "required": ["variables"]},
    fn=csp_backtrack, families=("guessing",), model_callable=False, max_ms=2000))
