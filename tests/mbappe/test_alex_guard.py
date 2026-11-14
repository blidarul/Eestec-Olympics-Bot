"""Issue #40: solvers/guard.py as a second opinion in SpeechRules (plurals, spacing, no false hit on 'class')."""
import unittest

import _path  # noqa: F401
from chat.speech_rules import SpeechRules


class TestAlexGuard(unittest.TestCase):
    def test_hits_and_clean(self):
        r = SpeechRules(["ass"], True)
        for t in ("what an a55", "so many asses", "a s s"):
            self.assertTrue(r.mentions_forbidden(t), t)
        for t in ("a classy move", "good luck", ""):
            self.assertFalse(r.mentions_forbidden(t), t)

    def test_no_terms_no_hit(self):
        self.assertFalse(SpeechRules([], False).mentions_forbidden("anything"))


if __name__ == "__main__":
    unittest.main()
