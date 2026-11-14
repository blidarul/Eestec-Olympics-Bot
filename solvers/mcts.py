"""Generic MCTS (UCB1, c = 1.4, random playouts) with a hard deadline. No game-specific code (10.7).

Same `game` interface as solvers/search.py (legal, apply, is_terminal, score, optional to_move).
Chance: `apply` may return a SAMPLED next state. The tree is "open loop": nodes are identified by the action
path from the root and every simulation re-applies the actions from the root state, so each visit samples fresh
chance outcomes.
Two-player zero-sum: the player to move maximises its own score; scores are normalised with running bounds.
Returns the most visited root move. Calibration (manifest simulator_calibration.transitions_per_sec) only
bounds the simulation count, the deadline always wins.
"""
import math
import random
import time
from dataclasses import dataclass

C_UCB = 1.4


@dataclass
class MCTSResult:
    action: object
    sims: int
    value: float       # mean score from `seat`'s point of view of the chosen move (raw score scale)
    visits: dict       # action -> visit count at the root


class _Node:
    __slots__ = ("n", "w", "children", "mover")

    def __init__(self, mover):
        self.n = 0
        self.w = 0.0                 # sum of raw scores from `seat`'s point of view
        self.children = {}           # action -> _Node
        self.mover = mover           # who chooses among the children (True = `seat`)


def sims_from_calibration(calibration, seconds, avg_rollout_len=20, floor=200, ceil=2_000_000):
    """Upper bound of simulations for `seconds` from manifest["simulator_calibration"]; None if unusable."""
    try:
        if not calibration or calibration.get("usable") is False:
            return None
        tps = float(calibration.get("transitions_per_sec") or 0)
        if tps <= 0:
            return None
        tps = min(max(tps, 1e3), 5e5)
        return int(min(ceil, max(floor, 2.0 * tps * seconds / max(1, avg_rollout_len))))
    except Exception:
        return None


def search(game, state, seat, deadline, c=C_UCB, max_playout=500, rng=None, max_sims=None):
    rng = rng or random.Random()
    moves = list(game.legal(state))
    if not moves:
        return MCTSResult(None, 0, game.score(state, seat), {})
    if len(moves) == 1:
        return MCTSResult(moves[0], 0, game.score(state, seat), {moves[0]: 0})
    has_to_move = callable(getattr(game, "to_move", None))

    def mover_is_me(s, default):
        return (game.to_move(s) == seat) if has_to_move else default

    root = _Node(mover_is_me(state, True))
    lo, hi = [float("inf")], [float("-inf")]
    sims = 0

    def rollout(s):
        for _ in range(max_playout):
            if game.is_terminal(s):
                break
            ms = game.legal(s)
            if not ms:
                break
            s = game.apply(s, rng.choice(ms))
        return game.score(s, seat)

    def select(node, legal_now):
        """UCB1 over legal children; None if an untried move exists (returned separately)."""
        untried = [m for m in legal_now if m not in node.children]
        if untried:
            return rng.choice(untried), True
        logn = math.log(max(1, node.n))
        span = (hi[0] - lo[0]) or 1.0
        best, best_u = None, -1.0
        for m in legal_now:
            ch = node.children[m]
            q = ((ch.w / ch.n) - lo[0]) / span if ch.n else 0.5
            if not node.mover:
                q = 1.0 - q          # opponent picks what is worst for us
            u = q + c * math.sqrt(logn / ch.n) if ch.n else float("inf")
            if u > best_u:
                best, best_u = m, u
        return best, False

    while True:
        if (sims & 7) == 0 and time.monotonic() >= deadline:
            break
        if max_sims is not None and sims >= max_sims:
            break
        node, s, path = root, state, [root]
        while True:
            if game.is_terminal(s):
                break
            legal_now = list(game.legal(s))
            if not legal_now:
                break
            m, expand = select(node, legal_now)
            nxt = game.apply(s, m)
            if expand:
                child = _Node(mover_is_me(nxt, not node.mover))
                node.children[m] = child
                path.append(child)
                s = nxt
                break
            node = node.children[m]
            path.append(node)
            s = nxt
        r = rollout(s)
        lo[0], hi[0] = min(lo[0], r), max(hi[0], r)
        for nd in path:
            nd.n += 1
            nd.w += r
        sims += 1

    if not root.children:
        return MCTSResult(moves[0], sims, 0.0, {})
    visits = {m: ch.n for m, ch in root.children.items()}
    best = max(root.children, key=lambda m: (root.children[m].n, root.children[m].w / max(1, root.children[m].n)))
    ch = root.children[best]
    return MCTSResult(best, sims, ch.w / max(1, ch.n), visits)
