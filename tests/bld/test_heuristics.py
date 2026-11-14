"""Unit tests for prep/heuristics.py.
Verifies generic, adaptive heuristic and policy learners.
Owned by agent `bld`.
"""
import sys
import unittest
from pathlib import Path

# Add arena-lite to path for importing practice games
repo_root = Path(__file__).resolve().parents[2]
arena_dir = repo_root / "arena-lite"
if str(arena_dir) not in sys.path:
    sys.path.insert(0, str(arena_dir))

from arena.practice.pig import Pig
from arena.practice.tic_tac_toe import TicTacToe
from prep.action_parser import parse_action_grammar
from prep.classifier import classify_rules
from prep.heuristics import (
    compute_centrality_order,
    compute_grid_symmetries,
    compute_heuristics,
    compute_stopping_thresholds,
)


class TestHeuristics(unittest.TestCase):
    def test_generic_stopping_thresholds(self):
        # Test generic stopping MDP policy on arbitrary parameters
        policy = compute_stopping_thresholds(
            target_score=60,
            p_bust=0.167,
            avg_gain=4.0,
            continue_action="spin",
            stop_action="bank",
        )
        self.assertEqual(policy["target_score"], 60)
        self.assertEqual(policy["continue_action"], "spin")
        self.assertEqual(policy["stop_action"], "bank")
        self.assertGreater(policy["base_threshold"], 10)

        # Check that when my_score is 55, remaining is 5, so threshold is 5
        self.assertEqual(policy["thresholds_by_score"]["55"], 5)

    def test_grid_symmetries_square_and_rectangular(self):
        # Square 3x3 board (D4 dihedral group)
        syms_3x3 = compute_grid_symmetries(cols=3, rows=3)
        self.assertIn("A1", syms_3x3)
        corners = syms_3x3["A1"]
        self.assertIn("A1", corners)
        self.assertIn("C1", corners)
        self.assertIn("A3", corners)
        self.assertIn("C3", corners)
        self.assertEqual(syms_3x3["B2"], ["B2"])

        # Rectangular 4x3 board (D2 Klein group)
        syms_rect = compute_grid_symmetries(cols=4, rows=3)
        self.assertIn("A1", syms_rect)
        self.assertEqual(len(syms_rect["A1"]), 4)

    def test_centrality_order(self):
        order_3x3 = compute_centrality_order(cols=3, rows=3)
        self.assertEqual(order_3x3[0], "B2")  # Center move is top priority

        order_5x5 = compute_centrality_order(cols=5, rows=5)
        self.assertEqual(order_5x5[0], "C3")  # Center of 5x5

    def test_compute_heuristics_integration(self):
        game = TicTacToe(TicTacToe.variants()[0], seed=42)
        rules = game.rules()
        cls_res = classify_rules(rules)
        grammar = parse_action_grammar(rules)

        heur = compute_heuristics(cls_res, grammar, rules)
        self.assertEqual(heur["family"], "grid_board")
        self.assertEqual(heur["opening_moves"][0], "B2")
        self.assertIn("symmetries", heur)


if __name__ == "__main__":
    unittest.main()
