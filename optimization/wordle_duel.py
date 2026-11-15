"""High-Performance Wordle Duel Specialist and Solver.
Implements exact repeated-letter feedback, entropy-based candidate elimination,
opponent color urgency detection, and zero-candidate relaxation.
Owned by agent `bld`.
"""
from __future__ import annotations

import math
import re
import sys
import time
from collections import Counter
from typing import Any, Iterable

from optimization.words import get_words

OPENINGS = {
    3: "air",
    4: "care",
    5: "slate",
    6: "planet",
    7: "balance",
    8: "strength",
}


def evaluate_guess(secret: str, guess: str) -> str:
    """Evaluate guess against secret with exact repeated-letter rules:
    Pass 1: Greens first (exact match at index).
    Pass 2: Yellows left to right for remaining letters in guess matching unused secret letters.
    Everything else is Grey ('X').
    Returns string of length N with chars 'G', 'Y', 'X'.
    """
    secret = secret.upper()
    guess = guess.upper()
    n = len(secret)
    res = ["X"] * n
    unused_secret_counts: dict[str, int] = {}

    for i in range(n):
        if guess[i] == secret[i]:
            res[i] = "G"
        else:
            unused_secret_counts[secret[i]] = unused_secret_counts.get(secret[i], 0) + 1

    for i in range(n):
        if res[i] == "G":
            continue
        c = guess[i]
        if unused_secret_counts.get(c, 0) > 0:
            res[i] = "Y"
            unused_secret_counts[c] -= 1

    return "".join(res)


def parse_feedback_pattern(fb: str | Iterable[Any], length: int) -> str:
    """Normalize raw observation feedback into a canonical 'G'/'Y'/'X' string."""
    if isinstance(fb, (list, tuple)):
        # numeric tuples like (2, 1, 0, 1, 1) or characters
        res = []
        for x in fb:
            if x in (2, "G", "g", "+", "green"):
                res.append("G")
            elif x in (1, "Y", "y", "?", "yellow"):
                res.append("Y")
            else:
                res.append("X")
        if len(res) == length:
            return "".join(res)

    s = str(fb).strip().upper()
    # Normalize words
    s = re.sub(r"\bGREEN\b", "G", s)
    s = re.sub(r"\bYELLOW\b", "Y", s)
    s = re.sub(r"\b(?:GREY|GRAY|BLACK|MISS|RED)\b", "X", s)

    chars = [c for c in s if c in ("G", "Y", "X")]
    if len(chars) == length:
        return "".join(chars)

    # Emoji square handling
    s_raw = str(fb)
    emojis = []
    for ch in s_raw:
        if ch == "\U0001f7e9":  # green square
            emojis.append("G")
        elif ch == "\U0001f7e8":  # yellow square
            emojis.append("Y")
        elif ch in ("\u2b1b", "\u2b1c", "\u25fc"):  # black / white square
            emojis.append("X")
    if len(emojis) == length:
        return "".join(emojis)

    # Map numbers 2, 1, 0
    digits = [c for c in s if c in ("2", "1", "0")]
    if len(digits) == length:
        d_map = {"2": "G", "1": "Y", "0": "X"}
        return "".join(d_map[d] for d in digits)

    # Fallback to length 'X's if malformed
    return "X" * length


def filter_candidates(candidates: list[str], guess: str, feedback: str) -> list[str]:
    """Filter candidate words to only those consistent with (guess, feedback)."""
    target_fb = feedback.upper()
    g = guess.lower()
    return [c for c in candidates if evaluate_guess(c, g) == target_fb]


def calculate_entropy(guess: str, candidates: list[str], sample_limit: int = 150) -> float:
    """Calculate expected information gain (Shannon entropy in bits) for a guess."""
    total = len(candidates)
    if total <= 1:
        return 0.0

    sample = candidates if total <= sample_limit else candidates[:sample_limit]
    total_sample = len(sample)

    counts = Counter(evaluate_guess(c, guess) for c in sample)
    ent = 0.0
    for cnt in counts.values():
        p = cnt / total_sample
        ent -= p * math.log2(p)
    return ent


def opponent_is_close(opponent_feedbacks: list[str], length: int) -> bool:
    """Check if the opponent is one letter away from solving the word (has N-1 greens)."""
    if not opponent_feedbacks:
        return False
    for fb in opponent_feedbacks:
        pat = parse_feedback_pattern(fb, length)
        if pat.count("G") >= length - 1:
            return True
    return False


class WordleDuelSolver:
    """Specialist solver for Wordle Duel games."""

    def __init__(self, length: int = 5, words: list[str] | None = None):
        self.length = length
        self.vocabulary: list[str] = [w.lower() for w in (words or get_words(length)) if len(w) == length]
        if not self.vocabulary:
            self.vocabulary = get_words(length) or ["word"[:length]]
        self.candidates: list[str] = list(self.vocabulary)
        self.history: list[tuple[str, str]] = []

    def update_history(self, guess: str, feedback: str) -> None:
        """Add a round of (guess, feedback) and update remaining candidates."""
        clean_guess = guess.lower().strip()
        clean_fb = parse_feedback_pattern(feedback, self.length)
        self.history.append((clean_guess, clean_fb))

        filtered = filter_candidates(self.candidates, clean_guess, clean_fb)
        if filtered:
            self.candidates = filtered
        else:
            # Safe relaxation: never allow zero candidates
            # Try filtering from full vocabulary excluding tested guess
            relaxed = [c for c in self.vocabulary if c != clean_guess]
            for past_g, past_fb in self.history[-2:]:
                sub = filter_candidates(relaxed, past_g, past_fb)
                if sub:
                    relaxed = sub
            self.candidates = relaxed if relaxed else [w for w in self.vocabulary if w != clean_guess]

    def choose_best_guess(
        self,
        avoid: set[str] | None = None,
        opponent_colors: list[str] | None = None,
        deadline: float | None = None,
    ) -> str:
        """Choose the optimal next word guess."""
        avoid_set = {a.lower().strip() for a in (avoid or set())}
        avoid_set.update(g for g, _ in self.history)

        # 1. Turn 1 opening move
        if not self.history:
            op = OPENINGS.get(self.length)
            if op and op not in avoid_set and len(op) == self.length:
                return op
            for w in self.vocabulary:
                if w not in avoid_set:
                    return w

        # 2. Check remaining candidates
        cands = [c for c in self.candidates if c not in avoid_set]
        if not cands:
            cands = [c for c in self.vocabulary if c not in avoid_set]
            if not cands:
                return OPENINGS.get(self.length, "words"[:self.length])

        # If very few candidates remain (<= 2), guess a candidate directly (first to find wins)
        if len(cands) <= 2:
            return cands[0]

        # 3. Urgency check: if opponent is one letter away (N-1 greens), prioritize candidate directly
        if opponent_is_close(opponent_colors or [], self.length) and cands:
            return cands[0]

        # 4. Entropy-based guess selection
        # Test up to 100 candidate words + up to 50 frequent vocabulary words
        cand_set = set(cands)
        eval_pool = list(cands[:100])
        extra_pool = [w for w in self.vocabulary[:150] if w not in cand_set and w not in avoid_set]
        eval_pool.extend(extra_pool[:50])

        best_word = cands[0]
        best_score = -1.0

        for w in eval_pool:
            if deadline and time.monotonic() >= deadline:
                break
            ent = calculate_entropy(w, cands)
            # Small tie-breaker bonus if the word is itself a candidate (can win this turn)
            bonus = 0.15 if w in cand_set else 0.0
            score = ent + bonus
            if score > best_score:
                best_score = score
                best_word = w

        return best_word


def solve_wordle_duel(
    history: list[tuple[str, str]],
    length: int = 5,
    prefix: str = "",
    opponent_colors: list[str] | None = None,
    words: list[str] | None = None,
    deadline: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """Standalone entry point for Wordle Duel decision turn."""
    t0 = time.monotonic()
    solver = WordleDuelSolver(length=length, words=words)
    for g, fb in history:
        solver.update_history(g, fb)

    avoid = {g.lower() for g, _ in history}
    best_w = solver.choose_best_guess(avoid=avoid, opponent_colors=opponent_colors, deadline=deadline)

    action = f"{prefix}{best_w}".strip() if prefix else best_w
    info = {
        "tool": "wordle_duel_entropy",
        "candidates_left": len(solver.candidates),
        "ms": int((time.monotonic() - t0) * 1000),
    }
    return action, info


def solve_wordle_from_obs(
    obs_text: str,
    my_actions: Iterable[str] = (),
    length: int = 5,
    prefix: str = "",
    deadline: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """Solve Wordle directly from observation and action history using entropy elimination."""
    t0 = time.monotonic()
    solver = WordleDuelSolver(length=length)

    history: list[tuple[str, str]] = []
    lines = obs_text.splitlines()
    for act in my_actions:
        w_act = str(act).strip()
        if prefix and w_act.lower().startswith(prefix.lower()):
            w_act = w_act[len(prefix):].strip()
        if len(w_act) == length and w_act.isalpha():
            for idx, l in enumerate(lines):
                if w_act.lower() in l.lower():
                    tail = l[l.lower().find(w_act.lower()) + len(w_act):]
                    fb = parse_feedback_pattern(tail, length)
                    if (not fb or fb == "X" * length) and idx + 1 < len(lines):
                        next_fb = parse_feedback_pattern(lines[idx + 1], length)
                        if next_fb and next_fb != "X" * length:
                            fb = next_fb
                    if fb:
                        history.append((w_act.lower(), fb))
                        solver.update_history(w_act.lower(), fb)
                        break

    # Extract opponent feedback patterns to activate urgency detection
    opp_colors: list[str] = []
    in_opp = False
    for l in lines:
        if "opponent" in l.lower():
            in_opp = True
        elif in_opp and ("your guess" in l.lower() or "round" in l.lower() or not l.strip()):
            in_opp = False
        if in_opp:
            pat = parse_feedback_pattern(l, length)
            if pat and pat != "X" * length:
                opp_colors.append(pat)

    avoid = {str(a).lower() for a in my_actions}
    avoid.update(g.lower() for g, _ in history)
    best_w = solver.choose_best_guess(avoid=avoid, opponent_colors=opp_colors, deadline=deadline)

    action = f"{prefix}{best_w}".strip() if prefix else best_w
    info = {
        "tool": "wordle_duel_entropy",
        "candidates_left": len(solver.candidates),
        "ms": int((time.monotonic() - t0) * 1000),
    }
    return action, info
