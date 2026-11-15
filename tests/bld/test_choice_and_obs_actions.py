"""Tests for enumerated options parsing in action templates and observation action extraction."""
import unittest

from core import actionfmt, fallback


class TestChoiceAndObsActions(unittest.TestCase):
    def test_options_from_rules_extracted(self):
        rules = (
            "ELEMENTAL DUEL. 2 players, simultaneous moves.\n"
            "ACTION FORMAT\n"
            "Cast a spell by typing: CAST <spell_name>\n"
            "Where <spell_name> is one of: MEDITATE, FIREBALL, ICE_BARRIER, LIGHTNING, GROUND_SPIKE, SIPHON.\n"
            "Examples: \"CAST MEDITATE\"."
        )
        opts = actionfmt._options_from_rules(rules, "spell_name")
        self.assertIsNotNone(opts)
        self.assertEqual(opts, ["MEDITATE", "FIREBALL", "ICE_BARRIER", "LIGHTNING", "GROUND_SPIKE", "SIPHON"])

    def test_parse_template_with_options(self):
        rules = (
            "ACTION FORMAT\n"
            "Cast a spell by typing: CAST <spell_name>\n"
            "Where <spell_name> is one of: MEDITATE, FIREBALL, ICE_BARRIER, LIGHTNING, GROUND_SPIKE, SIPHON.\n"
            "Examples: \"CAST MEDITATE\"."
        )
        fmt = actionfmt.parse_template(rules)
        self.assertIsNotNone(fmt)
        self.assertEqual(fmt["placeholders"][0]["type"], "choice")
        self.assertTrue(actionfmt.matches(fmt, "CAST MEDITATE"))
        self.assertTrue(actionfmt.matches(fmt, "CAST FIREBALL"))
        # Invalid / hallucinated words must NOT match
        self.assertFalse(actionfmt.matches(fmt, "CAST glint"))
        self.assertFalse(actionfmt.matches(fmt, "CAST brick"))

    def test_fill_uses_options(self):
        rules = (
            "ACTION FORMAT\n"
            "Cast a spell by typing: CAST <spell_name>\n"
            "Where <spell_name> is one of: MEDITATE, FIREBALL, ICE_BARRIER, LIGHTNING, GROUND_SPIKE, SIPHON.\n"
        )
        fmt = actionfmt.parse_template(rules)
        cand = actionfmt.fill(fmt, avoid={"CAST MEDITATE"})
        self.assertIsNotNone(cand)
        self.assertTrue(cand.startswith("CAST "))
        spell = cand.split()[1]
        self.assertIn(spell, ["FIREBALL", "ICE_BARRIER", "LIGHTNING", "GROUND_SPIKE", "SIPHON"])
        self.assertNotEqual(cand, "CAST MEDITATE")

    def test_extract_obs_actions_affordable_spells(self):
        obs = (
            "ELEMENTAL DUEL - Standard Arcana (100 HP, 5 rounds). Round 1/5.\n"
            "Your status: HP=100/100, Mana=30/60.\n"
            "Affordable spells: CAST MEDITATE, CAST FIREBALL, CAST ICE_BARRIER.\n"
            "It is your turn."
        )
        acts = fallback.extract_obs_actions(obs)
        self.assertEqual(acts, ["CAST MEDITATE", "CAST FIREBALL", "CAST ICE_BARRIER"])

    def test_extract_obs_actions_none_when_unmentioned(self):
        obs = "Connect Four. Board is empty. You are X."
        self.assertEqual(fallback.extract_obs_actions(obs), [])

    def test_multi_placeholder_candidate(self):
        rules = (
            "ACTION FORMAT\n"
            "offer <my_share> <their_share>   OR   accept\n"
            "Examples: \"offer 50 50\", \"accept\"."
        )
        cands = actionfmt._candidate_templates(rules)
        self.assertIn("offer <my_share> <their_share>", cands)


if __name__ == "__main__":
    unittest.main()
