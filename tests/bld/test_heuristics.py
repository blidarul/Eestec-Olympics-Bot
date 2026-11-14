"""Unit tests for prep/heuristics.py.
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
    compute_grid_symmetries,
    compute_heuristics,
    compute_pig_thresholds,
)


class TestHeuristics(unittest.TestCase):
    def test_pig_thresholds(self):
        tables = compute_pig_thresholds(target=50, dice=1)
        self.assertEqual(tables["target"], 50)
        self.assertEqual(tables["base_threshold"], 20)
        # Check that when my_score is 45, threshold is 5 (since 50 - 45 = 5)
        self.assertEqual(tables["thresholds_by_score"]["45"], 5)
        # Check that when my_score is 0, threshold is 20
        self.assertEqual(tables["thresholds_by_score"]["0"], 20)

    def test_grid_symmetries(self):
        syms_3x3 = compute_grid_symmetries(size=3)
        self.assertIn("A1", syms_3x3)
        # A1 is a corner: under rotations and flips, corners map to A1, C1, A3, C3
        corners = syms_3x3["A1"]
        self.assertIn("A1", corners)
        self.assertIn("C1", corners)
        self.assertIn("A3", corners)
        self.assertIn("C3", corners)

        # Center B2 maps only to itself
        center = syms_3x3["B2"]
        self.assertEqual(center, ["B2"])

    def test_compute_heuristics_integration(self):
        game = TicTacToe(TicTacToe.variants()[0], seed=42)
        rules = game.rules()
        cls_res = classify_rules(rules)
        grammar = parse_action_grammar(rules)

        heur = compute_heuristics(cls_res, grammar, rules)
        self.assertEqual(heur["family"], "grid_board")
        self.assertIn("B2", heur["opening_moves"])
        self.assertIn("symmetries", heur)


if __name__ == "__main__":
    unittest.main()
