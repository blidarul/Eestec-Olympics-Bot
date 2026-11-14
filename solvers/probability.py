"""Stochastic MDP value iteration and expected-utility choice. Pure python, no I/O."""
from typing import Any


def value_iteration(states, actions, transitions, rewards, gamma=0.95, max_iters=100, tol=1e-4):
    """Return (V, policy). transitions: (s, a) -> [(prob, s')]; rewards: (s, a) -> r.
    Only actions present in `transitions` for a state are available; states with none
    (terminal/empty) get V=0 and policy None. Probabilities are normalised if they do not sum to 1."""
    avail = {s: [a for a in actions if (s, a) in transitions] for s in states}
    norm = {}
    for key, outs in transitions.items():
        tot = sum(p for p, _ in outs if p > 0)
        norm[key] = [(p / tot, n) for p, n in outs if p > 0] if tot > 0 else []
    V = {s: 0.0 for s in states}

    def q(s, a, V):
        return rewards.get((s, a), 0.0) + gamma * sum(p * V.get(n, 0.0) for p, n in norm[(s, a)])

    for _ in range(max(1, max_iters)):
        delta = 0.0
        for s in states:
            if not avail[s]:
                continue
            best = max(q(s, a, V) for a in avail[s])
            delta = max(delta, abs(best - V[s]))
            V[s] = best
        if delta < tol:
            break
    policy = {}
    for s in states:
        if not avail[s]:
            policy[s] = None
            continue
        policy[s] = max(avail[s], key=lambda a: q(s, a, V))  # first best on ties
    return V, policy


def calculate_expected_utility(candidate_actions, outcome_distribution):
    """Return (best_action, max_expected_utility); actions without a distribution are skipped.
    Ties go to the earliest candidate. Empty input -> (None, 0.0)."""
    best, best_u = None, float("-inf")
    for a in candidate_actions:
        outs = outcome_distribution.get(a)
        if not outs:
            continue
        u = sum(p * x for p, x in outs)
        if u > best_u:
            best, best_u = a, u
    if best is None:
        return None, 0.0
    return best, best_u
