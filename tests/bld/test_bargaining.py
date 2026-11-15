import unittest
from optimization.bargaining import parse_bargaining_obs, solve_bargaining


class TestBargaining(unittest.TestCase):
    def test_rejects_losing_offer(self):
        # Opponent offers 40, keeps 60
        obs = (
            "BARGAINING (100 coins, 10% decay). Round 1 of 5. Current pot size: 100 coins.\n"
            "PENDING OFFER from Player 0: offers you 40 coins (keeps 60 coins).\n"
            "You may 'accept' or reply with a counter 'offer <me> <opp>'.\n"
        )
        legal = ["accept", "offer 50 50", "offer 60 40", "offer 70 30"]
        act = solve_bargaining(legal, observation=obs)
        self.assertNotEqual(act, "accept")
        self.assertIn("offer", act)

    def test_accepts_winning_offer(self):
        # Opponent offers 60, keeps 40
        obs = (
            "BARGAINING (100 coins, 10% decay). Round 2 of 5. Current pot size: 90 coins.\n"
            "PENDING OFFER from Player 0: offers you 60 coins (keeps 30 coins).\n"
        )
        legal = ["accept", "offer 45 45", "offer 54 36"]
        act = solve_bargaining(legal, observation=obs)
        self.assertEqual(act, "accept")

    def test_accepts_equal_offer(self):
        # Opponent offers 50, keeps 50
        obs = (
            "BARGAINING (100 coins, 10% decay). Round 1 of 5. Current pot size: 100 coins.\n"
            "PENDING OFFER from Player 0: offers you 50 coins (keeps 50 coins).\n"
        )
        legal = ["accept", "offer 50 50", "offer 60 40"]
        act = solve_bargaining(legal, observation=obs)
        self.assertEqual(act, "accept")

    def test_proposes_advantage_split(self):
        # Proposing in round 1 with pot 100
        obs = (
            "BARGAINING (100 coins, 10% decay). Round 1 of 5. Current pot size: 100 coins.\n"
            "Open the negotiation with 'offer <my_share> <their_share>'.\n"
        )
        legal = ["offer 50 50", "offer 60 40", "offer 70 30"]
        act = solve_bargaining(legal, observation=obs)
        self.assertEqual(act, "offer 60 40")


if __name__ == "__main__":
    unittest.main()
