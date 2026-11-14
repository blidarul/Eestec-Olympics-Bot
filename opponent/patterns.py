"""Small pure helpers to find patterns in a sequence of opponent moves (no I/O, no randomness).

Used by opponent/tracker.py (profile: cycle period) and strategies/read_opponent (prediction).
A sequence is a list of strings, oldest first, for example ["rock", "paper", "rock", "paper"].
"""
from collections import Counter

MAX_PERIOD = 6   # longest cycle we look for
MIN_REPEATS = 2  # a cycle must repeat at least this many times to count
MIN_CYCLE_TAIL = 6  # and cover at least this many moves


def detect_cycle(seq):
    """The shortest period p (2..MAX_PERIOD) such that the end of `seq` repeats the pattern of length p at least
    MIN_REPEATS times; None if there is no such cycle. A constant sequence is period 1."""
    n = len(seq)
    if n >= 3 and len(set(seq[-3:])) == 1:
        return 1
    for p in range(2, MAX_PERIOD + 1):
        need = max(p * MIN_REPEATS, MIN_CYCLE_TAIL)  # long enough that chance rarely makes a cycle
        if n < need:
            break
        tail = seq[-need:]
        if all(tail[i] == tail[i + p] for i in range(need - p)):
            return p
    return None


def ngram_predict(seq, n_max=3, min_support=3):
    """(prediction, confidence) from the longest context (n_max..1) that was seen at least `min_support` times,
    or (None, 0.0). Confidence = share of the most common follower, damped when the support is small."""
    for n in range(min(n_max, len(seq) - 1), 0, -1):
        ctx = tuple(seq[-n:])
        followers = Counter()
        for i in range(len(seq) - n):
            if tuple(seq[i:i + n]) == ctx:
                followers[seq[i + n]] += 1
        total = sum(followers.values())
        if total >= min_support:
            move, cnt = followers.most_common(1)[0]
            return move, (cnt / total) * min(1.0, total / 6.0)
    return None, 0.0


def frequency_predict(seq, actions):
    """(most frequent move, its share) over the whole history, or (None, 0.0) when no move stands out
    (a share at most 1/k + 0.1 for k actions is treated as noise)."""
    if not seq:
        return None, 0.0
    move, cnt = Counter(seq).most_common(1)[0]
    share = cnt / len(seq)
    k = max(2, len(actions))
    return (move, share) if share > 1.0 / k + 0.1 else (None, 0.0)


def predict_next(seq, actions, min_history=4):
    """Predict the opponent's next move. Returns (move, confidence, method) with method in
    "cycle", "ngram", "frequency" or "none". Never raises, deterministic."""
    seq = [s for s in seq if s]
    if len(seq) < min_history:
        return None, 0.0, "none"
    p = detect_cycle(seq)
    if p:
        return seq[-p], 0.9, "cycle"
    move, conf = ngram_predict(seq)
    freq_move, share = frequency_predict(seq, actions)
    if freq_move is not None and share >= 0.6 and conf < 0.9:
        return freq_move, share, "frequency"      # a strong overall habit beats a weak local context (noise)
    if move is not None and conf >= 0.7:
        return move, conf, "ngram"
    if freq_move is not None:
        return freq_move, share, "frequency"
    return None, 0.0, "none"
