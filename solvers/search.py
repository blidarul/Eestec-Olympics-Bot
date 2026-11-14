"""Generic alpha-beta with iterative deepening, a transposition table and a hard deadline (no game-specific code, 10.7).

The caller supplies a `game` object (any object with these methods) and a parsed `state`:
    game.legal(state)          -> list of actions (may be empty)
    game.apply(state, action)  -> new state (must not mutate `state`)
    game.is_terminal(state)    -> bool
    game.score(state, seat)    -> float, from `seat`'s point of view (exact at terminals, heuristic elsewhere)
    game.to_move(state)        -> optional: seat to move; if missing, seats alternate starting with `seat`
    game.key(state)            -> optional: 64-bit int state hash (Zobrist); else hash(state); unhashable -> no table
`parse(obs) -> state` lives in the caller (the game adapter).

Transposition table (issue #14): integer keys only, bounded (optimization.structures.TranspositionTable when it
imports, a local equivalent otherwise), with exact / lower / upper bound flags, so no string is built per node.
Subtrees searched to a terminal state are stored as proven (valid at any depth).

`search()` returns a SearchResult; `exact` is True when the last completed iteration never met the depth horizon,
i.e. the value is the true game value. `best_move()` keeps the old 3-tuple interface.
Never raises on deadline: returns the best move of the last COMPLETED depth (or the first legal move).
"""
import random
import time
from dataclasses import dataclass

_EXACT, _LOWER, _UPPER = 0, 1, 2
_PROVEN = 10 ** 9
_TURN_KEY = random.Random(0x5EA4C).getrandbits(64)
INF = float("inf")


class _Timeout(Exception):
    pass


class _LocalTT:
    """Same contract as optimization.structures.TranspositionTable (used if that module does not import)."""

    def __init__(self, capacity=200_000):
        self.capacity, self.table = capacity, {}

    def store(self, key, depth, value, flag, best_action=None):
        if len(self.table) >= self.capacity and key not in self.table:
            self.table.pop(next(iter(self.table)))
        self.table[key] = (depth, value, flag, best_action)

    def lookup(self, key, depth, alpha, beta):
        e = self.table.get(key)
        if e is None:
            return None, None
        d, v, f, a = e
        if d >= depth and (f == _EXACT or (f == _LOWER and v >= beta) or (f == _UPPER and v <= alpha)):
            return v, a
        return None, a


def make_table(capacity=200_000):
    try:
        from optimization.structures import TranspositionTable
        return TranspositionTable(capacity)
    except Exception:
        return _LocalTT(capacity)


@dataclass
class SearchResult:
    action: object
    value: float
    depth: int
    exact: bool      # value is the true game value (search never hit the depth horizon)
    nodes: int
    timed_out: bool


def _pause_gc():
    try:
        from optimization.budget import pause_gc
        return pause_gc()
    except Exception:
        import contextlib
        return contextlib.nullcontext()


def search(game, state, seat, deadline, max_depth=64, table=None, node_cap=None):
    """Alpha-beta, iterative deepening. `deadline` is a time.monotonic() value."""
    moves = list(game.legal(state))
    if not moves:
        return SearchResult(None, game.score(state, seat), 0, True, 0, False)
    if len(moves) == 1:
        return SearchResult(moves[0], game.score(state, seat), 0, False, 0, False)
    has_to_move = callable(getattr(game, "to_move", None))
    key_fn = getattr(game, "key", None)
    tt = table if table is not None else make_table()
    nodes = [0]
    horizon = [0]

    def check():
        nodes[0] += 1
        if nodes[0] & 255 == 0 and (time.monotonic() >= deadline or (node_cap and nodes[0] >= node_cap)):
            raise _Timeout

    def skey(s, maxing):
        try:
            k = key_fn(s) if key_fn is not None else hash(s)
        except Exception:
            return None
        return k if maxing else k ^ _TURN_KEY

    def ab(s, depth, alpha, beta, maxing):
        check()
        if game.is_terminal(s):
            return game.score(s, seat)
        if depth <= 0:
            horizon[0] += 1
            return game.score(s, seat)
        k = skey(s, maxing)
        hint = None
        if k is not None:
            v, hint = tt.lookup(k, depth, alpha, beta)
            if v is not None:
                if tt.table[k][0] < _PROVEN:
                    horizon[0] += 1  # reused a depth-limited value: not provably exact
                return v
        ms = list(game.legal(s))
        if not ms:
            return game.score(s, seat)
        if has_to_move:
            maxing = game.to_move(s) == seat
        if hint is not None and hint in ms:
            ms.remove(hint)
            ms.insert(0, hint)
        a0, b0, h0 = alpha, beta, horizon[0]
        val, best = (-INF if maxing else INF), None
        for m in ms:
            v = ab(game.apply(s, m), depth - 1, alpha, beta, not maxing)
            if (v > val) if maxing else (v < val):
                val, best = v, m
            if maxing:
                alpha = max(alpha, val)
            else:
                beta = min(beta, val)
            if alpha >= beta:
                break
        if k is not None:
            flag = _UPPER if val <= a0 else _LOWER if val >= b0 else _EXACT
            tt.store(k, _PROVEN if horizon[0] == h0 else depth, val, flag, best)
        return val

    best, best_val, reached, exact, timed_out = moves[0], -INF, 0, False, False
    order = list(moves)
    with _pause_gc():
        try:
            for depth in range(1, max_depth + 1):
                horizon[0] = 0
                d_best, d_val, alpha = None, -INF, -INF
                for m in order:
                    v = ab(game.apply(state, m), depth - 1, alpha, INF, False)
                    if v > d_val:
                        d_best, d_val = m, v
                    alpha = max(alpha, d_val)
                best, best_val, reached = d_best, d_val, depth
                order.remove(d_best)
                order.insert(0, d_best)  # principal move first at the next depth
                if horizon[0] == 0:  # whole tree searched to terminal states
                    exact = True
                    break
                if abs(d_val) == INF:
                    break
        except _Timeout:
            timed_out = True
    return SearchResult(best, best_val, reached, exact, nodes[0], timed_out)


def best_move(game, state, seat, deadline, max_depth=64):
    """Return (action, value, depth_reached); action is None only if there is no legal move."""
    r = search(game, state, seat, deadline, max_depth)
    return r.action, r.value, r.depth
