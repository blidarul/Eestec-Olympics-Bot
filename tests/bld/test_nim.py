import unittest
from optimization.nim import parse_piles_from_obs, solve_nim


class TestNimSolver(unittest.TestCase):
    def test_parse_piles(self):
        obs = "Piles now: pile 1 = 5, pile 2 = 0, pile 3 = 7, pile 4 = 2   (total 14)"
        piles = parse_piles_from_obs(obs)
        self.assertEqual(piles, [5, 0, 7, 2])

    def test_normal_play_winning_move(self):
        # Piles [3, 4, 5]: nim-sum is 3 ^ 4 ^ 5 = 2.
        # Changing pile 1 (size 3) to 1 gives 1 ^ 4 ^ 5 = 0 (take 2 from pile 1)
        obs = "Piles now: pile 1 = 3, pile 2 = 4, pile 3 = 5   (total 12)"
        legal = [
            "take 1 from pile 1", "take 2 from pile 1", "take 3 from pile 1",
            "take 1 from pile 2", "take 2 from pile 2", "take 3 from pile 2", "take 4 from pile 2",
            "take 1 from pile 3", "take 2 from pile 3", "take 3 from pile 3", "take 4 from pile 3", "take 5 from pile 3",
        ]
        act = solve_nim(legal, observation=obs, rules="NORMAL PLAY: the player who takes the LAST token WINS.")
        self.assertEqual(act, "take 2 from pile 1")

    def test_misere_play_endgame(self):
        # Piles [1, 1, 3]: in misère, taking all 3 from pile 3 leaves [1, 1], which is an EVEN number of 1s (losing!).
        # Taking 2 from pile 3 leaves [1, 1, 1], which is an ODD number of 1s (winning!).
        obs = "Piles now: pile 1 = 1, pile 2 = 1, pile 3 = 3   (total 5)"
        legal = [
            "take 1 from pile 1", "take 1 from pile 2",
            "take 1 from pile 3", "take 2 from pile 3", "take 3 from pile 3",
        ]
        act = solve_nim(legal, observation=obs, rules="MISERE PLAY: the player who takes the LAST token LOSES.")
        self.assertEqual(act, "take 2 from pile 3")

    def test_take_1_3_limited_play(self):
        # Single pile of 4 with take 1-3:
        # Taking 1 leaves 3 (which can be taken, but modulo 4: 4 % 4 = 0, taking 1 leaves 3 = 3 % 4 != 0).
        # What if pile is 5? 5 % 4 = 1. Taking 1 leaves 4 (4 % 4 = 0), winning move!
        obs = "Piles now: pile 1 = 5   (total 5)"
        legal = ["take 1 from pile 1", "take 2 from pile 1", "take 3 from pile 1"]
        act = solve_nim(legal, observation=obs, rules="Remove between 1 and 3 from exactly ONE pile. NORMAL PLAY.")
        self.assertEqual(act, "take 1 from pile 1")


if __name__ == "__main__":
    unittest.main()
