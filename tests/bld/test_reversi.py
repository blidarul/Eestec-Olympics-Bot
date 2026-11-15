"""Tests for Reversi positional solver in optimization/reversi.py."""
import unittest

from optimization.reversi import (
    parse_reversi_board,
    parse_reversi_move,
    solve_reversi,
)


class TestReversi(unittest.TestCase):
    def test_parse_move(self):
        self.assertEqual(parse_reversi_move("place a1"), (0, 0))
        self.assertEqual(parse_reversi_move("place f6"), (5, 5))
        self.assertEqual(parse_reversi_move("c4"), (3, 2))

    def test_corner_preference(self):
        # Corner a1 (+100) must beat X-square b2 (-40) and C-square b1 (-20)
        legal = ["place b2", "place a1", "place b1"]
        obs = "REVERSI (6x6 standard). You are Player 0 ('X')."
        best = solve_reversi(legal, obs)
        self.assertEqual(best, "place a1")

    def test_c_square_penalty_without_corner(self):
        # When corner a1 is NOT owned, b1 (-20) should lose to safe edge c1 (+15)
        legal = ["place b1", "place c1"]
        obs = "REVERSI (6x6 standard). You are Player 0 ('X')."
        best = solve_reversi(legal, obs)
        self.assertEqual(best, "place c1")

    def test_c_square_boost_with_owned_corner(self):
        # When corner a1 is already owned by X, b1 becomes safe
        legal = ["place b1", "place c3"]
        obs = (
            "REVERSI (6x6 standard). You are Player 0 ('X').\n"
            "   a b c d e f\n"
            " 1 X . . . . . 1\n"
            " 2 . . . . . . 2\n"
            " 3 . . O X . . 3\n"
            " 4 . . X O . . 4\n"
            " 5 . . . . . . 5\n"
            " 6 . . . . . . 6\n"
        )
        best = solve_reversi(legal, obs)
        self.assertEqual(best, "place b1")


if __name__ == "__main__":
    unittest.main()
