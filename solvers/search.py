"""Generic alpha-beta with iterative deepening and a hard deadline (no game-specific code, 10.7).

The caller supplies a `game` object (any object with these methods) and a parsed `state`:
    game.legal(state)          -> list of actions (may be empty)
    game.apply(state, action)  -> new state (must not mutate `state`)
    game.is_terminal(state)    -> bool
    game.score(state, seat)    -> float, from `seat`'s point of view (exact at terminals, heuristic elsewhere)
    game.to_move(state)        -> optional: seat to move; if missing, seats alternate starting with `seat`
`parse(obs) -> state` lives in the caller (the game adapter). States should be hashable for the
transposition table; unhashable states simply skip it.
Never raises on deadline: returns the best move of the last COMPLETED depth (or the first legal move).
"""
import time


class _Timeout(Exception):
    pass


def best_move(game, state, seat, deadline, max_depth=64):
    """Return (action, value, depth_reached). `deadline` is a time.monotonic() value. action is None
    only if there is no legal move."""
    moves = list(game.legal(state))
    if not moves:
        return None, game.score(state, seat), 0
    best, best_val, reached = moves[0], float("-inf"), 0
    if len(moves) == 1:
        return best, game.score(state, seat), 0
    has_to_move = callable(getattr(game, "to_move", None))
    table = {}
    nodes = [0]

    def check():
        nodes[0] += 1
        if nodes[0] % 256 == 0 and time.monotonic() >= deadline:
            raise _Timeout

    def key(s, depth, maxing):
        try:
            hash(s)
            return (s, depth, maxing)
        except TypeError:
            return None

    def ab(s, depth, alpha, beta, maxing):
        check()
        if depth == 0 or game.is_terminal(s):
            return game.score(s, seat)
        k = key(s, depth, maxing)
        if k is not None and k in table:
            return table[k]
        ms = list(game.legal(s))
        if not ms:
            return game.score(s, seat)
        if has_to_move:
            maxing = game.to_move(s) == seat
        a0, b0 = alpha, beta
        val = float("-inf") if maxing else float("inf")
        for m in ms:
            v = ab(game.apply(s, m), depth - 1, alpha, beta, not maxing)
            if maxing:
                val = max(val, v)
                alpha = max(alpha, val)
            else:
                val = min(val, v)
                beta = min(beta, val)
            if alpha >= beta:
                return val  # cut-off value is a bound, not exact: not cached
        if k is not None and a0 < val < b0:  # exact only inside the window
            table[k] = val
        return val

    order = list(moves)
    try:
        for depth in range(1, max_depth + 1):
            d_best, d_val, alpha = None, float("-inf"), float("-inf")
            for m in order:
                v = ab(game.apply(state, m), depth - 1, alpha, float("inf"), False)
                if v > d_val:
                    d_best, d_val = m, v
                alpha = max(alpha, d_val)
            best, best_val, reached = d_best, d_val, depth
            order.remove(d_best)
            order.insert(0, d_best)  # principal move first at the next depth
            if abs(d_val) == float("inf"):
                break
    except _Timeout:
        pass
    return best, best_val, reached
