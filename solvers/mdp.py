"""Value iteration over an enumerable MDP (harness-only, layer 3 M6). No game-specific code (10.7).

    states: iterable of hashable states; actions(s) -> list; transitions(s, a) -> [(p, s2, reward)]
solve(...) -> MDPResult(values, policy, iterations, converged, states). Terminal states: no actions (value 0).
Hard caps: max_states (BFS from `start` when `states` is None), a deadline checked every sweep. Never raises on a
deadline: returns the values of the last finished sweep with converged=False.
"""
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class MDPResult:
    values: dict
    policy: dict
    iterations: int
    converged: bool
    states: int


def enumerate_states(start, actions, transitions, max_states=50000, deadline=None):
    """Breadth-first closure of the reachable states from `start`; None when it exceeds max_states or the deadline."""
    seen, todo = {start}, deque([start])
    while todo:
        if deadline is not None and time.monotonic() >= deadline:
            return None
        s = todo.popleft()
        for a in actions(s) or []:
            for _p, s2, _r in transitions(s, a) or []:
                if s2 not in seen:
                    if len(seen) >= max_states:
                        return None
                    seen.add(s2)
                    todo.append(s2)
    return list(seen)


def value_iteration(states, actions, transitions, discount=1.0, tol=1e-9, max_iter=10000, deadline=None):
    states = list(states)
    table = {}
    for s in states:
        table[s] = [(a, [(float(p), s2, float(r)) for p, s2, r in (transitions(s, a) or [])]) for a in (actions(s) or [])]
    v = {s: 0.0 for s in states}
    it, converged = 0, False
    while it < max_iter:
        if deadline is not None and time.monotonic() >= deadline:
            break
        delta = 0.0
        for s in states:                    # in-place (Gauss-Seidel) sweep
            opts = table[s]
            if not opts:
                continue
            best = max(sum(p * (r + discount * v.get(s2, 0.0)) for p, s2, r in outs) for _a, outs in opts)
            delta = max(delta, abs(best - v[s]))
            v[s] = best
        it += 1
        if delta <= tol:
            converged = True
            break
    policy = {}
    for s in states:
        opts = table[s]
        if opts:
            policy[s] = max(opts, key=lambda ao: sum(p * (r + discount * v.get(s2, 0.0)) for p, s2, r in ao[1]))[0]
    return MDPResult(v, policy, it, converged, len(states))


def solve(start, actions, transitions, discount=1.0, deadline=None, max_states=50000, states=None, tol=1e-9):
    """Enumerate (unless `states` is given) and run value iteration; returns MDPResult or None if too large."""
    st = list(states) if states is not None else enumerate_states(start, actions, transitions, max_states, deadline)
    if st is None:
        return None
    return value_iteration(st, actions, transitions, discount, tol, deadline=deadline)
