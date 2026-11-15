import unittest
from optimization.blind_mans_bluff import parse_bmb_obs, solve_blind_mans_bluff


class TestBlindMansBluff(unittest.TestCase):
    def test_value_bet_on_weak_opp_card(self):
        # Opponent has 3 on forehead (7/9 win prob = 78%)
        obs = "BLIND MAN'S BLUFF (10-card deck, 5 hands). OPPONENT'S CARD: 3 (your own card is hidden!).\n"
        legal = ["check", "bet 1"]
        act = solve_blind_mans_bluff(legal, observation=obs)
        self.assertEqual(act, "bet 1")

    def test_check_on_strong_opp_card(self):
        # Opponent has 8 on forehead (2/9 win prob = 22%)
        obs = "BLIND MAN'S BLUFF (10-card deck, 5 hands). OPPONENT'S CARD: 8 (your own card is hidden!).\n"
        legal = ["check", "bet 1"]
        act = solve_blind_mans_bluff(legal, observation=obs)
        self.assertEqual(act, "check")

    def test_call_on_playable_pot_odds(self):
        # Opponent has 6 (4/9 win prob = 44% > 25% pot odds)
        obs = "BLIND MAN'S BLUFF (10-card deck, 5 hands). OPPONENT'S CARD: 6 (your own card is hidden!).\n"
        legal = ["call 1", "fold"]
        act = solve_blind_mans_bluff(legal, observation=obs)
        self.assertEqual(act, "call 1")

    def test_fold_on_unfavorable_pot_odds(self):
        # Opponent has 9 (1/9 win prob = 11% < 25% pot odds)
        obs = "BLIND MAN'S BLUFF (10-card deck, 5 hands). OPPONENT'S CARD: 9 (your own card is hidden!).\n"
        legal = ["call 1", "fold"]
        act = solve_blind_mans_bluff(legal, observation=obs)
        self.assertEqual(act, "fold")


if __name__ == "__main__":
    unittest.main()
