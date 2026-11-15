"""Tests for Mini Chess tactical evaluator in optimization/mini_chess.py."""
import unittest

from optimization.mini_chess import (
    evaluate_chess_move,
    is_square_attacked,
    parse_chess_grid,
    solve_mini_chess,
)


class TestMiniChess(unittest.TestCase):
    def test_parse_grid(self):
        obs = (
            "MINI CHESS (Gardner 5x5). You are WHITE (Player 0).\n"
            "Turn: WHITE to move (ply 1 of 80).\n"
            "   a b c d e\n"
            " 5 r n b q k 5\n"
            " 4 p p p p p 4\n"
            " 3 . . . . . 3\n"
            " 2 P P P P P 2\n"
            " 1 R N B Q K 1\n"
            "   a b c d e\n"
        )
        grid, side, size = parse_chess_grid(obs)
        self.assertEqual(side, 0)
        self.assertEqual(size, 5)
        self.assertEqual(grid[0][0], "r")
        self.assertEqual(grid[4][4], "K")
        self.assertEqual(grid[2][2], ".")

    def test_capture_preference(self):
        # White Pawn at c3 (row 2) can capture Black Queen at d4 (row 1) or advance to c4
        grid = [
            [".", ".", ".", ".", "k"],
            [".", ".", ".", "q", "."],
            [".", ".", "P", ".", "."],
            [".", ".", ".", ".", "."],
            [".", ".", ".", ".", "K"],
        ]
        score_cap = evaluate_chess_move("c3d4", grid, side=0, size=5)
        score_quiet = evaluate_chess_move("c3c4", grid, side=0, size=5)
        self.assertGreater(score_cap, score_quiet)

    def test_hanging_piece_avoidance(self):
        # White Queen at d1 moving to d4 where black pawn at e5 attacks it undefended
        grid = [
            [".", ".", ".", "k", "."],
            [".", ".", ".", ".", "p"],
            [".", ".", ".", ".", "."],
            [".", ".", ".", ".", "."],
            [".", ".", ".", "Q", "K"],
        ]
        score_blunder = evaluate_chess_move("d1d4", grid, side=0, size=5)
        score_safe = evaluate_chess_move("d1d2", grid, side=0, size=5)
        self.assertLess(score_blunder, score_safe)


if __name__ == "__main__":
    unittest.main()
