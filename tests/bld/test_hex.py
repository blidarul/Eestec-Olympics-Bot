"""Tests for Hex solver in optimization/hex.py."""
import unittest

from optimization.hex import (
    parse_hex_move,
    parse_hex_observation,
    shortest_path_dist,
    solve_hex,
)


class TestHex(unittest.TestCase):
    def test_parse_move(self):
        self.assertEqual(parse_hex_move("place a1"), (0, 0))
        self.assertEqual(parse_hex_move("place d4"), (3, 3))
        self.assertEqual(parse_hex_move("g7"), (6, 6))

    def test_parse_observation(self):
        obs = (
            "HEX (7x7). You are Player 0 ('X').\n"
            "Board:\n"
            "  1  . . . . . . .  1\n"
            "   2  . . . . . . .  2\n"
            "    3  . . . . . . .  3\n"
            "     4  . . . X . . .  4\n"
            "      5  . . . . . . .  5\n"
            "       6  . . . . . . .  6\n"
            "        7  . . . . . . .  7\n"
        )
        board, seat, size = parse_hex_observation(obs)
        self.assertEqual(seat, 0)
        self.assertEqual(size, 7)
        self.assertEqual(board[3][3], 0)
        self.assertIsNone(board[0][0])

    def test_winning_move_selected(self):
        # In a 3x3 board for seat 0 (connect row 0 to row 2)
        # If (0, 1) and (1, 1) are owned by 0, both a3 and b3 connect to row 2 and win!
        legal = ["place a3", "place b3", "place c3"]
        obs = (
            "HEX (3x3). You are Player 0 ('X').\n"
            "  1  . X .  1\n"
            "   2  . X .  2\n"
            "    3  . . .  3\n"
        )
        best = solve_hex(legal, obs)
        self.assertIn(best, ["place a3", "place b3"])

    def test_block_opponent_win(self):
        # Seat 0 plays X. Opponent seat 1 (O) connects col 0 to col 2.
        # If (1, 0) and (1, 1) are owned by O, O needs (1, 2) to win.
        # Seat 0 must block by playing (1, 2) -> 'c2'!
        legal = ["place a1", "place c2", "place a3"]
        obs = (
            "HEX (3x3). You are Player 0 ('X').\n"
            "  1  . . .  1\n"
            "   2  O O .  2\n"
            "    3  . . .  3\n"
        )
        best = solve_hex(legal, obs)
        self.assertEqual(best, "place c2")


if __name__ == "__main__":
    unittest.main()
