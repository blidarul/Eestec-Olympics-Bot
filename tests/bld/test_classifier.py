"""Unit tests for prep/classifier.py.
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

from arena.practice.guess_number import GuessNumber
from arena.practice.pig import Pig
from arena.practice.tic_tac_toe import TicTacToe
from arena.practice.bargaining import Bargaining
from arena.practice.nim import Nim
from prep.classifier import classify_rules


class TestClassifier(unittest.TestCase):
    def test_classify_tic_tac_toe(self):
        game = TicTacToe(TicTacToe.variants()[0], seed=42)
        rules = game.rules()
        cls_result = classify_rules(rules)

        self.assertEqual(cls_result.family, "grid_board")
        self.assertTrue(cls_result.is_deterministic)
        self.assertFalse(cls_result.has_hidden_information)
        self.assertEqual(cls_result.turn_structure, "alternating")
        self.assertGreater(cls_result.confidence, 0.4)

    def test_classify_guess_number(self):
        game = GuessNumber(GuessNumber.variants()[0], seed=42)
        rules = game.rules()
        cls_result = classify_rules(rules)

        self.assertEqual(cls_result.family, "deduction")
        self.assertTrue(cls_result.has_hidden_information)
        self.assertEqual(cls_result.turn_structure, "alternating")
        self.assertGreater(cls_result.confidence, 0.4)

    def test_classify_pig(self):
        game = Pig(Pig.variants()[0], seed=42)
        rules = game.rules()
        cls_result = classify_rules(rules)

        self.assertEqual(cls_result.family, "dice_push")
        self.assertFalse(cls_result.is_deterministic)
        self.assertEqual(cls_result.turn_structure, "push_your_luck")
        self.assertGreater(cls_result.confidence, 0.4)

    def test_classify_bargaining(self):
        game = Bargaining(Bargaining.variants()[0], seed=42)
        rules = game.rules()
        cls_result = classify_rules(rules)

        self.assertEqual(cls_result.family, "negotiation")
        self.assertTrue(cls_result.is_deterministic)

    def test_classify_nim(self):
        game = Nim(Nim.variants()[0], seed=42)
        rules = game.rules()
        cls_result = classify_rules(rules)

        self.assertEqual(cls_result.family, "grid_board")
        self.assertTrue(cls_result.is_deterministic)
        self.assertFalse(cls_result.features.get("has_dice", False))


if __name__ == "__main__":
    unittest.main()
