"""Tests for core.clocks deadline management and core.actionfmt word length template filling.
Owned by agent `bld`.
"""
import unittest

from core import actionfmt, clocks


class TestClocks(unittest.TestCase):
    def test_turn_deadline(self):
        # 20s standard move clock -> capped at 12.0s
        self.assertEqual(clocks.compute_turn_deadline(20.0), 12.0)
        # Short clock (e.g. 10s blitz) -> 0.6 * 10 = 6.0s
        self.assertEqual(clocks.compute_turn_deadline(10.0), 6.0)

    def test_study_deadline(self):
        self.assertEqual(clocks.compute_study_deadline(30.0, is_cold=False), 2.0)
        self.assertEqual(clocks.compute_study_deadline(120.0, is_cold=True), 2.0)

    def test_prep_deadline(self):
        # 600s prep -> 540s
        self.assertEqual(clocks.compute_prep_deadline(600.0), 540.0)

    def test_deadline_tracker(self):
        tracker = clocks.DeadlineTracker(10.0)
        self.assertFalse(tracker.expired(buffer_seconds=1.0))
        self.assertGreater(tracker.remaining(), 8.0)
        self.assertGreaterEqual(tracker.elapsed(), 0.0)


class TestActionFormatWordLength(unittest.TestCase):
    def test_wordle_template_length_extraction(self):
        rules = "Wordle Duel. Each round enter your 5-letter word: ACTION FORMAT: guess <word>."
        fmt = actionfmt.parse_template(rules)
        self.assertIsNotNone(fmt)
        ph = fmt["placeholders"][0]
        self.assertEqual(ph["type"], "word")
        self.assertEqual(ph["length"], 5)

    def test_wordle_fill_respects_extracted_length(self):
        rules = "Wordle Duel. Each round enter your 5-letter word: ACTION FORMAT: guess <word>."
        fmt = actionfmt.parse_template(rules)
        filled = actionfmt.fill(fmt, avoid=set(), observation="")
        self.assertIsNotNone(filled)
        self.assertTrue(filled.startswith("guess "))
        word = filled.split()[1]
        self.assertEqual(len(word), 5)
        self.assertTrue(word.isalpha())

    def test_4_letter_word_template_fill(self):
        rules = "Word game. 4-letter guess: ACTION FORMAT: guess <word>."
        fmt = actionfmt.parse_template(rules)
        filled = actionfmt.fill(fmt, avoid=set(), observation="")
        self.assertIsNotNone(filled)
        word = filled.split()[1]
        self.assertEqual(len(word), 4)


if __name__ == "__main__":
    unittest.main()
