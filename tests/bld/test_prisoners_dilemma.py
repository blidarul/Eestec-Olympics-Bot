import unittest
from optimization.prisoners_dilemma import parse_pd_obs, solve_prisoners_dilemma


class TestPrisonersDilemma(unittest.TestCase):
    def test_round_1_opens_with_cooperate(self):
        obs = (
            "PRISONER'S DILEMMA (Qualify at 25, at least 8 rounds). You are Player 0.\n"
            "Round 1 (min 8, max 20).\n"
            "Scores: you 0 (defections: 0), opponent 0 (defections: 0). Quota: 25.\n"
            "Current standing if game ended now: nobody reached 25 and both defected 0 times.\n\n"
            "Round history:\n"
            "  (none yet)\n"
        )
        act = solve_prisoners_dilemma(["cooperate", "defect"], observation=obs)
        self.assertEqual(act, "cooperate")

    def test_retaliates_after_opponent_defect(self):
        obs = (
            "PRISONER'S DILEMMA (Qualify at 25, at least 8 rounds). You are Player 0.\n"
            "Round 2 (min 8, max 20).\n"
            "Scores: you 0 (defections: 0), opponent 5 (defections: 1). Quota: 25.\n"
            "Current standing if game ended now: nobody reached 25; seat 0 has fewer defections (0 vs 1).\n\n"
            "Round history:\n"
            "  Round 1: you cooperate (+0), opponent defect (+5)\n"
        )
        act = solve_prisoners_dilemma(["cooperate", "defect"], observation=obs)
        self.assertEqual(act, "defect")

    def test_continues_cooperation_when_opponent_cooperates(self):
        obs = (
            "PRISONER'S DILEMMA (Qualify at 25, at least 8 rounds). You are Player 0.\n"
            "Round 3 (min 8, max 20).\n"
            "Scores: you 6 (defections: 0), opponent 6 (defections: 0). Quota: 25.\n"
            "Current standing if game ended now: nobody reached 25 and both defected 0 times.\n\n"
            "Round history:\n"
            "  Round 1: you cooperate (+3), opponent cooperate (+3)\n"
            "  Round 2: you cooperate (+3), opponent cooperate (+3)\n"
        )
        act = solve_prisoners_dilemma(["cooperate", "defect"], observation=obs)
        self.assertEqual(act, "cooperate")

    def test_defects_when_quota_reached(self):
        obs = (
            "PRISONER'S DILEMMA (Qualify at 25, at least 8 rounds). You are Player 0.\n"
            "Round 9 (min 8, max 20).\n"
            "Scores: you 27 (defections: 0), opponent 27 (defections: 0). Quota: 25.\n"
            "Current standing if game ended now: both reached quota 25 with equal points 27-27.\n\n"
            "Round history:\n"
            "  Round 8: you cooperate (+3), opponent cooperate (+3)\n"
        )
        act = solve_prisoners_dilemma(["cooperate", "defect"], observation=obs)
        self.assertEqual(act, "defect")


if __name__ == "__main__":
    unittest.main()
