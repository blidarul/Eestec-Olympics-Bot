import unittest

import _path  # noqa: F401
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "games"))
from forbidden_count import ForbiddenCount, says_forbidden  # noqa: E402


class TestTestGame(unittest.TestCase):
    """The speech-rule test game must really end a game on a forbidden line (so a PASS in the arena means something)."""

    def test_detects_spellings(self):
        for t in ["banana", "say BANANA!", "b a n a n a", "b4n4n4", "baaanana", "b.a.n.a.n.a"]:
            self.assertTrue(says_forbidden(t), t)
        for t in ["bandana", "Good luck.", "Your move."]:
            self.assertFalse(says_forbidden(t), t)

    def test_violation_ends_game(self):
        g = ForbiddenCount({"label": "to 12", "target": 12}, 1)
        g.on_chat(0, "Good luck.")
        self.assertFalse(g.is_over())
        g.on_chat(0, "b a n a n a")
        self.assertTrue(g.is_over())
        self.assertEqual(g.result()["winner"], 1)


if __name__ == "__main__":
    unittest.main()
