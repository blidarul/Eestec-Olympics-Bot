"""Tests for game-theory and dynamic programming precomputations in prep (Issue #46).
Tests Pig exact DP policy, Connect Four opening book precomputation,
and Colonel Blotto game-theoretic allocation portfolios.
Owned by agent `bld`.
"""
from __future__ import annotations

import os
import tempfile
import pytest

from optimization.pig_dp import compute_pig_thresholds, query_pig_action
from optimization.connect_four_book import precompute_connect_four_book, query_connect_four_book
from optimization.blotto_solver import generate_blotto_allocations, select_blotto_action
from prep.engine import PrepEngine


def test_pig_dp_1die_thresholds():
    thresh = compute_pig_thresholds(target_score=50, num_dice=1, max_iterations=20)
    assert len(thresh) == 50
    assert len(thresh[0]) == 50
    # At (0, 0), the classic optimal threshold for Pig-50 is 20-22
    assert 19 <= thresh[0][0] <= 23

    # When we are at 45 (5 away from target), threshold must be 5
    assert thresh[45][0] == 5

    # When opponent is at 48 (2 away from winning), threshold increases significantly
    assert thresh[20][48] >= thresh[20][0]


def test_pig_dp_2dice_thresholds():
    thresh2 = compute_pig_thresholds(target_score=60, num_dice=2, snake_eyes_reset=True, max_iterations=20)
    assert len(thresh2) == 60
    assert len(thresh2[0]) == 60
    # With 2 dice, threshold exists and is bounded
    assert 15 <= thresh2[0][0] <= 30


def test_query_pig_action():
    thresh = [[20] * 50 for _ in range(50)]
    # Below threshold -> roll
    assert query_pig_action(thresh, my_score=10, opp_score=10, turn_points=15, target_score=50) == "roll"
    # At or above threshold -> bank
    assert query_pig_action(thresh, my_score=10, opp_score=10, turn_points=20, target_score=50) == "bank"
    # Immediate win -> bank even if below threshold
    assert query_pig_action(thresh, my_score=45, opp_score=10, turn_points=5, target_score=50) == "bank"


def test_connect_four_opening_book():
    book = precompute_connect_four_book(rows=6, cols=7, connect_k=4, time_limit_sec=1.5)
    assert "" in book
    # Opening move on 7-column board should be center column (4)
    assert book[""] == 4
    # Query opening book
    assert query_connect_four_book(book, []) == 4
    if "4" in book:
        assert query_connect_four_book(book, [4]) == book["4"]


def test_blotto_strategic_portfolio():
    port = generate_blotto_allocations(soldiers=100, fields=5, values=[1, 1, 1, 1, 1], count=25)
    assert len(port) >= 15
    for alloc in port:
        assert len(alloc) == 5
        assert sum(alloc) == 100
        assert all(x >= 0 for x in alloc)

    # Test selection
    action_str = select_blotto_action(port, available_soldiers=100, fields=5, round_no=1)
    tokens = [int(x) for x in action_str.split()]
    assert len(tokens) == 5
    assert sum(tokens) == 100

    # Test reserve scaling (e.g. 30 soldiers, 3 fields)
    port3 = generate_blotto_allocations(soldiers=30, fields=3, values=[1, 1, 1], count=10)
    act3 = select_blotto_action(port3, available_soldiers=30, fields=3, round_no=1)
    tokens3 = [int(x) for x in act3.split()]
    assert len(tokens3) == 3
    assert sum(tokens3) == 30


def test_prep_engine_precomputes_game_theory_books():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PrepEngine(memory_dir=tmpdir)
        prep_msg = {
            "game_id": "test_prep_gt",
            "game_name": "Test GT Games",
            "seconds": 30.0,
            "variants": [
                {
                    "label": "pig_var",
                    "rules": "PIG - One die, first to 50. Roll or hold.",
                    "sample_turn": {"observation": "Banked: you 0, opponent 0. Turn total: 0", "legal_actions": ["roll", "hold"]},
                },
                {
                    "label": "c4_var",
                    "rules": "CONNECT FOUR - 6x7 board, connect 4 to win. Gravity drops pieces to bottom.",
                    "sample_turn": {"observation": "Drop 1-7", "legal_actions": ["drop 1", "drop 2", "drop 3", "drop 4", "drop 5", "drop 6", "drop 7"]},
                },
                {
                    "label": "blotto_var",
                    "rules": "COLONEL BLOTTO - 100 soldiers across 5 battlefields. Values: F1=1, F2=1, F3=1, F4=1, F5=1.",
                    "sample_turn": {"observation": "allocation of 100 soldiers", "legal_actions": None},
                },
            ],
        }

        res = engine.run_prep(prep_msg)
        assert res.get("type") == "ready"
        game_dir = os.path.join(tmpdir, "test_prep_gt")
        # Check files were written
        assert os.path.exists(os.path.join(game_dir, "pig_dp.json"))
        assert os.path.exists(os.path.join(game_dir, "opening_book.json"))
        assert os.path.exists(os.path.join(game_dir, "blotto_book.json"))
