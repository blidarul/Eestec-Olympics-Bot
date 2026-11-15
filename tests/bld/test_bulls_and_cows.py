import unittest
from optimization.bulls_and_cows import solve_bulls_and_cows, score, parse_bulls_and_cows_obs


class TestBullsAndCows(unittest.TestCase):
    def test_score_no_repeats(self):
        # Code 4721, guess 1724 -> 2 bulls (7, 2), 2 cows (4, 1)
        b, c = score("4721", "1724", "0123456789")
        self.assertEqual((b, c), (2, 2))

    def test_score_with_repeats(self):
        b, c = score("AABB", "BBAA", "ABCDEF")
        self.assertEqual((b, c), (0, 4))
        b, c = score("AABB", "AAAB", "ABCDEF")
        self.assertEqual((b, c), (3, 0))

    def test_round1_opening(self):
        obs = """BULLS AND COWS (4 digits, no repeats). You are Player 0.
Your secret code (the opponent is trying to crack it): 4721
Round 1 of 10.

Your previous guesses at opponent's code:
  (none yet)

Opponent's previous guesses at your code:
  (none yet)
"""
        act = solve_bulls_and_cows(obs)
        self.assertEqual(act, "guess 0123")

    def test_deduction_filter(self):
        # Suppose opponent secret is 0145.
        # Guess 0123 got 2 bulls, 0 cows.
        # Candidate 0145 should be consistent and can be picked.
        obs = """BULLS AND COWS (4 digits, no repeats). You are Player 0.
Your secret code: 4721
Round 2 of 10.

Your previous guesses at opponent's code:
  Round 1: guess 0123 -> 2 bulls, 0 cows

Opponent's previous guesses at your code:
  Round 1: guess 9876 -> 0 bulls, 1 cows
"""
        act = solve_bulls_and_cows(obs)
        self.assertTrue(act.startswith("guess "))
        code = act.split()[1]
        self.assertEqual(len(code), 4)
        # Must have exactly 2 bulls and 0 cows against 0123
        b, c = score(code, "0123", "0123456789")
        self.assertEqual((b, c), (2, 0))


if __name__ == "__main__":
    unittest.main()
