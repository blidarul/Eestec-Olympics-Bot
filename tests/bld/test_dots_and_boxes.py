"""Tests for Dots and Boxes solver in optimization/dots_and_boxes.py."""
import unittest

from optimization.dots_and_boxes import parse_dab_dimensions, solve_dots_and_boxes


class TestDotsAndBoxes(unittest.TestCase):
    def test_dimension_parsing(self):
        rules = "DOTS AND BOXES (3x5 boxes). You are Player 0."
        r, c = parse_dab_dimensions(rules, "")
        self.assertEqual((r, c), (3, 5))

        r2, c2 = parse_dab_dimensions("Dots and Boxes", "Current scores (4x4 boxes)")
        self.assertEqual((r2, c2), (4, 4))

    def test_capture_priority(self):
        # In a 1x1 box, edges are a1-b1, a2-b2, a1-a2, b1-b2
        # Suppose a1-b1, a2-b2, a1-a2 are drawn -> b1-b2 completes the box!
        legal = ["line b1-b2", "line c1-c2"]
        act = solve_dots_and_boxes(legal, rules="1x1 boxes", observation="")
        self.assertEqual(act, "line b1-b2")

    def test_safe_move_over_sacrifice(self):
        # 2x2 board:
        # A box with 2 drawn edges: playing a 3rd edge gives away the box!
        # A box with 0 drawn edges: playing an edge is safe!
        # Suppose line a1-b1 and line a1-a2 are drawn for top-left box (a1-b1-a2-b2).
        # Playing line b1-b2 would be edge #3 (sacrifice).
        # Playing line b2-c2 is in another box with 0 edges (safe).
        # We simulate this by having legal_actions containing both.
        # All edges:
        # box (0,0): a1-b1, a2-b2, a1-a2, b1-b2
        # box (0,1): b1-c1, b2-c2, b1-b2, c1-c2
        # box (1,0): a2-b2, a3-b3, a2-a3, b2-b3
        # box (1,1): b2-c2, b3-c3, b2-b3, c2-c3
        # Suppose a1-b1 and a1-a2 are drawn. (so they are NOT in legal_actions)
        all_other_edges = [
            "line a2-b2", "line b1-b2",
            "line b1-c1", "line b2-c2", "line c1-c2",
            "line a3-b3", "line a2-a3", "line b2-b3",
            "line b3-c3", "line c2-c3",
        ]
        # Playing b1-b2 gives away top-left box.
        # Playing b1-c1 is completely safe!
        chosen = solve_dots_and_boxes(all_other_edges, rules="2x2 boxes")
        self.assertNotEqual(chosen, "line b1-b2")


if __name__ == "__main__":
    unittest.main()
