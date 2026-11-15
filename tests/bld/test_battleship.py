import unittest
from optimization.battleship import solve_battleship, parse_battleship_obs

OBS_EMPTY = """BATTLESHIP (6x6, 3 ships). You are Player 0.
Round 1 of 30. It is your turn.
Fleet status: you have 3 ships afloat; opponent has 3 ships afloat.

YOUR SHOTS (targeting opponent's fleet):
   a b c d e f
 1 . . . . . .
 2 . . . . . .
 3 . . . . . .
 4 . . . . . .
 5 . . . . . .
 6 . . . . . .

YOUR WATERS (your fleet and opponent's shots):
   a b c d e f
 1 C C C . . .
 2 . . . . . .
 3 . . D D . .
 4 . . . . . .
 5 P P . . . .
 6 . . . . . .
"""

OBS_HIT = """BATTLESHIP (6x6, 3 ships). You are Player 0.
Round 3 of 30. It is your turn.
Fleet status: you have 3 ships afloat; opponent has 3 ships afloat.

YOUR SHOTS (targeting opponent's fleet):
   a b c d e f
 1 . . . . . .
 2 . . o . . .
 3 . . X . . .
 4 . . . . . .
 5 . . . . . .
 6 . . . . . .
"""

OBS_ALIGNED_HITS = """BATTLESHIP (6x6, 3 ships). You are Player 0.
Round 4 of 30. It is your turn.
Fleet status: you have 3 ships afloat; opponent has 3 ships afloat.

YOUR SHOTS (targeting opponent's fleet):
   a b c d e f
 1 . . . . . .
 2 . . o . . .
 3 . . X X . .
 4 . . . . . .
 5 . . . . . .
 6 . . . . . .
"""


class TestBattleship(unittest.TestCase):
    def test_parse(self):
        res = parse_battleship_obs(OBS_EMPTY)
        self.assertIsNotNone(res)
        size, cells = res
        self.assertEqual(size, 6)
        self.assertEqual(len(cells), 36)

    def test_hunt_parity(self):
        act = solve_battleship(OBS_EMPTY)
        self.assertTrue(act.startswith("fire "))
        parts = act.split()
        coord = parts[1]
        col = ord(coord[0]) - ord("a")
        row = int(coord[1:]) - 1
        # Should obey parity
        self.assertEqual((row + col) % 2, 0)

    def test_target_neighbor(self):
        act = solve_battleship(OBS_HIT)
        # Hit was at c3 (row 2, col 2). Neighbor must be b3, d3, c2, c4.
        # But c2 is 'o' (miss)! So candidate must be b3, d3, or c4!
        self.assertIn(act, ["fire b3", "fire d3", "fire c4"])

    def test_line_continuation(self):
        act = solve_battleship(OBS_ALIGNED_HITS)
        # Hits are at c3, d3 (horizontal line on row 3).
        # Continuation must be b3 or e3!
        self.assertIn(act, ["fire b3", "fire e3"])


if __name__ == "__main__":
    unittest.main()
