import unittest
from optimization.stag_hunt import parse_stag_hunt_obs, solve_stag_hunt


class TestStagHunt(unittest.TestCase):
    def test_round_1_probe_stag(self):
        obs = "STAG HUNT (10 rounds). Round 1/10. Scores: you 0, opponent 0.\nRound history:\n  (none yet)"
        act = solve_stag_hunt(["stag", "hare"], observation=obs, rules="Both hunt STAG: +5 points each")
        self.assertEqual(act, "stag")

    def test_switches_to_hare_against_unreliable_opponent(self):
        # Opponent played hare 3 times, stag 1 time (p = 0.25 < 0.60)
        obs = (
            "STAG HUNT (10 rounds). Round 5 of 10. Scores: you 9, opponent 12.\n"
            "Past expeditions history:\n"
            "  Round 1: you stag (+0), opp hare (+3) -> player 1 deserted\n"
            "  Round 2: you hare (+3), opp hare (+3) -> mutual hare\n"
            "  Round 3: you stag (+5), opp stag (+5) -> mutual stag\n"
            "  Round 4: you stag (+0), opp hare (+3) -> player 1 deserted\n"
        )
        act = solve_stag_hunt(["stag", "hare"], observation=obs, rules="Both hunt STAG: +5 points each")
        self.assertEqual(act, "hare")

    def test_lead_protection_plays_hare(self):
        # Round 9 of 10, leading 26 to 20
        obs = (
            "STAG HUNT (10 rounds). Round 9/10. Scores: you 26, opponent 20.\n"
            "Round history:\n"
            "  Round 8: you stag (+5), opponent stag (+5)\n"
        )
        act = solve_stag_hunt(["stag", "hare"], observation=obs, rules="Both hunt STAG: +5 points each")
        self.assertEqual(act, "hare")


if __name__ == "__main__":
    unittest.main()
