"""Candidate elimination (no game-specific code, 10.7).

    cands = eliminate(cands, guess, feedback, compatible)   # keep c where compatible(c, guess) == feedback
    g = best_split(cands, guesses, compatible)               # guess whose feedback classes are smallest in the worst case
`compatible(candidate, guess)` returns the feedback `guess` would get if `candidate` were the secret
(any hashable value). `best_split` is deadline-aware and falls back to the first guess.
"""
import time
from collections import Counter


def eliminate(cands, guess, feedback, compatible):
    kept = [c for c in cands if compatible(c, guess) == feedback]
    return kept if kept else list(cands)  # inconsistent feedback (noisy/lying source): do not empty the set


def best_split(cands, guesses=None, compatible=None, deadline=None, sample=400):
    """Guess minimising the largest feedback class (ties: prefer a guess that is itself a candidate)."""
    cands = list(cands)
    pool = list(guesses) if guesses is not None else cands
    if not pool:
        return None
    if len(cands) <= 2 or compatible is None:
        return cands[0] if cands and (guesses is None or cands[0] in pool) else pool[0]
    probe = cands if len(cands) <= sample else cands[:: max(1, len(cands) // sample)]
    cset = set(cands) if all(_hashable(c) for c in cands) else set()
    best, best_key = pool[0], None
    for g in pool:
        if deadline is not None and time.monotonic() >= deadline:
            break
        worst = max(Counter(compatible(c, g) for c in probe).values())
        k = (worst, 0 if g in cset else 1)
        if best_key is None or k < best_key:
            best, best_key = g, k
    return best


def _hashable(x):
    try:
        hash(x)
        return True
    except TypeError:
        return False
