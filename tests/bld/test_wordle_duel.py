"""Tests for Wordle Duel specialist solver and benchmark (Issue #39).
Tests repeated-letter rules, entropy maximization, candidate filtering,
zero-candidate relaxation, opponent urgency detection, and 2000-word benchmark.
Owned by agent `bld`.
"""
from __future__ import annotations

import random
import time
import pytest

from optimization.words import get_words
from optimization.wordle_duel import (
    WordleDuelSolver,
    evaluate_guess,
    parse_feedback_pattern,
    calculate_entropy,
    opponent_is_close,
    solve_wordle_duel,
)

WORDLE_4_OBS = """WORDLE DUEL (4 letters, 5 guesses max). Both players guess simultaneously.
Round 2/5. Enter guess <word>.
Your guesses:
1. CARE -> Y X X X
Opponent guesses:
1. TIME -> X X X G
"""

WORDLE_6_OBS = """WORDLE DUEL (6 letters, 7 guesses max). Both players guess simultaneously.
Round 2/7. Enter guess <word>.
Your guesses:
1. PLANET -> G X Y X X G
Opponent guesses:
1. FOREST -> X G X Y X X
"""


def test_repeated_letter_rules_exact_contract():
    # Exact test case required by Issue #39: secret CRANE, guess CATER -> G Y X Y Y
    # C -> G (exact match at 0)
    # A -> Y (in secret at 2, not 1)
    # T -> X (not in secret)
    # E -> Y (in secret at 4, not 3)
    # R -> Y (in secret at 1, not 4)
    res = evaluate_guess("CRANE", "CATER")
    assert res == "GYXYY"


def test_repeated_letters_duplicate_in_guess():
    # Secret has one 'E', guess has two 'E's
    # Secret: SPOKE, Guess: SPEED -> S(G) P(G) E(Y) E(X) D(X)
    res = evaluate_guess("SPOKE", "SPEED")
    assert res == "GGYXX"

    # Secret: ALLOY, Guess: LLAMA -> L(Y) L(G) A(Y) M(X) A(X)
    res = evaluate_guess("ALLOY", "LLAMA")
    assert res == "YGYXX"


def test_parse_feedback_pattern():
    assert parse_feedback_pattern("G Y X Y Y", 5) == "GYXYY"
    assert parse_feedback_pattern([2, 1, 0, 1, 1], 5) == "GYXYY"
    assert parse_feedback_pattern("🟩🟨⬛🟨🟨", 5) == "GYXYY"
    assert parse_feedback_pattern("GREEN YELLOW GREY YELLOW YELLOW", 5) == "GYXYY"


def test_opponent_urgency_detection():
    # Opponent is 1 letter away if they have N-1 greens (e.g. 4 greens in 5-letter game)
    assert opponent_is_close(["GGGGX"], 5) is True
    assert opponent_is_close(["GGGYX"], 5) is False
    assert opponent_is_close(["GGGX"], 4) is True
    assert opponent_is_close(["GGGGGG"], 6) is True


def test_zero_candidate_safe_relaxation():
    # If contradictory or unexpected feedback occurs, solver must never return empty candidates
    solver = WordleDuelSolver(length=5)
    solver.update_history("slate", "GGGGG")
    # Add an impossible feedback that eliminates all
    solver.update_history("cater", "GGGGG")
    guess = solver.choose_best_guess()
    assert len(guess) == 5
    assert len(solver.candidates) > 0


def test_wordle_duel_replays_fixtures():
    # 4-letter fixture
    solver4 = WordleDuelSolver(length=4)
    solver4.update_history("care", "YXXX")
    g4 = solver4.choose_best_guess()
    assert len(g4) == 4
    assert g4 != "care"

    # 6-letter fixture
    solver6 = WordleDuelSolver(length=6)
    solver6.update_history("planet", "GXYXXG")
    g6 = solver6.choose_best_guess()
    assert len(g6) == 6
    assert g6 != "planet"

    # Test candidate preference when <= 2 candidates remain
    solver6.candidates = ["packet", "pocket"]
    g_cand = solver6.choose_best_guess()
    assert g_cand in ["packet", "pocket"]

    # Test urgency preference when opponent is 1 letter away
    solver6.candidates = ["packet", "pocket", "parrot", "priest"]
    g_urgent = solver6.choose_best_guess(opponent_colors=["GGGGGX"])
    assert g_urgent in solver6.candidates


def run_benchmark_simulation(length: int, num_words: int = 2000):
    words = get_words(length)
    vocab = [w.lower() for w in words if len(w) == length]
    assert vocab, f"Vocabulary for length {length} must not be empty"

    random.seed(length * 1000 + 42)
    sample_secrets = [random.choice(vocab) for _ in range(num_words)]

    total_guesses = 0
    worst_guesses = 0
    max_move_time_ms = 0.0

    t_start = time.monotonic()
    for s in sample_secrets:
        solver = WordleDuelSolver(length=length, words=vocab)
        g_cnt = 0
        while g_cnt < 12:
            t0 = time.monotonic()
            g = solver.choose_best_guess()
            dt_ms = (time.monotonic() - t0) * 1000.0
            if dt_ms > max_move_time_ms:
                max_move_time_ms = dt_ms

            g_cnt += 1
            if g.lower() == s:
                break
            solver.update_history(g, evaluate_guess(s, g))

        total_guesses += g_cnt
        if g_cnt > worst_guesses:
            worst_guesses = g_cnt

    mean_guesses = total_guesses / num_words
    total_sec = time.monotonic() - t_start

    print(
        f"\n[BENCHMARK] Wordle {length}-letter ({num_words} simulated words): "
        f"mean={mean_guesses:.2f}, worst={worst_guesses}, "
        f"max_move_time={max_move_time_ms:.2f}ms, total_time={total_sec:.2f}s"
    )
    assert mean_guesses <= 4.5, f"Mean guesses {mean_guesses} exceeded 4.5"
    assert worst_guesses <= 9, f"Worst guesses {worst_guesses} exceeded 9"
    assert max_move_time_ms < 100.0, f"Max move time {max_move_time_ms}ms exceeded 100ms"
    return mean_guesses, worst_guesses, max_move_time_ms


def test_wordle_duel_4_letter_2000_words():
    run_benchmark_simulation(4, 2000)


def test_wordle_duel_5_letter_2000_words():
    run_benchmark_simulation(5, 2000)


def test_wordle_duel_6_letter_2000_words():
    run_benchmark_simulation(6, 2000)
