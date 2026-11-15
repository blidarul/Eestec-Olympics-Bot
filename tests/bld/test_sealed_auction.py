import unittest
from optimization.sealed_auction import parse_auction_obs, solve_sealed_auction


class TestSealedAuction(unittest.TestCase):
    def test_vickrey_bids_truthful_valuation(self):
        obs = (
            "SEALED-BID AUCTION (Second-Price (Vickrey), 5 rounds). You are Player 0.\n"
            "Round 1 of 5. Total profits: you 0.0, opponent 0.0.\n"
            "YOUR PRIVATE VALUATION for this lot: 75.0.\n"
            "Valuation range: [10, 100]. Pricing rule: second_price.\n"
        )
        legal = ["bid 10", "bid 28", "bid 46", "bid 64", "bid 75", "bid 82", "bid 100"]
        act = solve_sealed_auction(legal, observation=obs, rules="SECOND-PRICE (Vickrey)")
        self.assertEqual(act, "bid 75")

    def test_first_price_bid_shading(self):
        # Val = 80, min = 10. Target = (80 + 10) / 2 = 45.
        obs = (
            "SEALED-BID AUCTION (First-Price, 5 rounds). You are Player 0.\n"
            "Round 1 of 5. Total profits: you 0.0, opponent 0.0.\n"
            "YOUR PRIVATE VALUATION for this lot: 80.0.\n"
            "Valuation range: [10, 100]. Pricing rule: first_price.\n"
        )
        legal = ["bid 10", "bid 28", "bid 46", "bid 64", "bid 80", "bid 100"]
        act = solve_sealed_auction(legal, observation=obs, rules="FIRST-PRICE")
        # Closest to 45 is "bid 46"
        self.assertEqual(act, "bid 46")

    def test_first_price_strictly_avoids_overbidding(self):
        # Val = 20. Target = (20 + 10) / 2 = 15. Legal options: 10, 30, 50.
        # Should pick 10 (not 30, because 30 > 20 would cause negative profit!).
        obs = (
            "SEALED-BID AUCTION (First-Price, 5 rounds). You are Player 0.\n"
            "Round 1 of 5. Total profits: you 0.0, opponent 0.0.\n"
            "YOUR PRIVATE VALUATION for this lot: 20.0.\n"
            "Valuation range: [10, 100]. Pricing rule: first_price.\n"
        )
        legal = ["bid 10", "bid 30", "bid 50"]
        act = solve_sealed_auction(legal, observation=obs, rules="FIRST-PRICE")
        self.assertEqual(act, "bid 10")


if __name__ == "__main__":
    unittest.main()
