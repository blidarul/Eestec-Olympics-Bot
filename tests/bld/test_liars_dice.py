import unittest
from optimization.liars_dice import (
    binom_survival,
    parse_liars_dice_state,
    solve_liars_dice,
)


class TestLiarsDice(unittest.TestCase):
    def test_binom_survival(self):
        # 5 dice, p = 1/6 (no wild)
        p = 1.0 / 6.0
        self.assertAlmostEqual(binom_survival(5, 0, p), 1.0)
        self.assertAlmostEqual(binom_survival(5, 6, p), 0.0)
        # P(>= 1) = 1 - (5/6)^5 = 0.5981
        self.assertAlmostEqual(binom_survival(5, 1, p), 1.0 - (5.0 / 6.0) ** 5, places=4)

    def test_parse_state(self):
        obs = """LIAR'S DICE (5 dice each, Ones wild). You are Player 0.
Dice counts: you have 5 dice, opponent has 4 dice (total 9).
YOUR HIDDEN DICE: [1, 2, 4, 4, 6].
Current bid on table: 2 of 4.
Turn: Player 0 to act.
"""
        state = parse_liars_dice_state(obs)
        self.assertEqual(state["my_dice"], [1, 2, 4, 4, 6])
        self.assertEqual(state["my_count"], 5)
        self.assertEqual(state["opp_count"], 4)
        self.assertEqual(state["current_bid"], (2, 4))
        self.assertTrue(state["ones_wild"])

    def test_call_liar_on_impossible_or_low_prob_bid(self):
        # We hold [2, 3, 5]. Total dice = 6 (3 each). Opponent bids 5 of 4.
        # Opponent has 3 dice, needed = 5 - 0 = 5 > 3. P = 0.0.
        obs = """LIAR'S DICE (3 dice each). You are Player 0.
Dice counts: you have 3 dice, opponent has 3 dice (total 6).
YOUR HIDDEN DICE: [2, 3, 5].
Current bid on table: 5 of 4.
Turn: Player 0 to act.
"""
        act = solve_liars_dice(obs, legal_actions=["liar", "bid 5 5"])
        self.assertEqual(act, "liar")

    def test_raise_when_holding_matching_dice(self):
        # We hold [4, 4, 4, 5, 6]. Opponent bids 1 of 4.
        # We hold THREE 4s already! P_true of 1 of 4 is 100%.
        # Calling liar would be disastrous. We should raise.
        obs = """LIAR'S DICE (5 dice each). You are Player 0.
Dice counts: you have 5 dice, opponent has 5 dice (total 10).
YOUR HIDDEN DICE: [4, 4, 4, 5, 6].
Current bid on table: 1 of 4.
Turn: Player 0 to act.
"""
        legal = ["liar", "bid 1 5", "bid 1 6", "bid 2 4", "bid 3 4", "bid 4 4"]
        act = solve_liars_dice(obs, legal_actions=legal)
        self.assertNotEqual(act, "liar")
        self.assertTrue(act.startswith("bid "))


if __name__ == "__main__":
    unittest.main()
