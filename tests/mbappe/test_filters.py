import os
import tempfile
import unittest

import _path  # noqa: F401
from chat import intents, output_filters as of, speech_rules as sr

RULES_QUOTED = """GUARDRAILS - Talk Show. You may chat freely.
FORBIDDEN SUBJECT: the word "banana".
If you mention it in any chat line you lose the game on the spot."""
RULES_NATURAL = "You must never mention the moon or the stars in any chat line. Saying them loses at once."
RULES_PLAIN = "TIC-TAC-TOE 3x3. Players alternate turns. You may not move twice in a row. Illegal moves lose."
RULES_UNREADABLE = "Careful: you may never talk about it, and chat lines are checked."


class TestSpeechRules(unittest.TestCase):
    def test_extract_quoted(self):
        s = sr.extract(RULES_QUOTED)
        self.assertIn("banana", s.terms)
        self.assertTrue(s.restricted)

    def test_extract_natural(self):
        s = sr.extract(RULES_NATURAL)
        self.assertTrue({"moon", "stars"} <= set(s.terms), s.terms)

    def test_no_restriction(self):
        s = sr.extract(RULES_PLAIN)
        self.assertFalse(s.restricted)
        self.assertEqual(s.terms, [])

    def test_unreadable_rule_fails_closed(self):
        s = sr.extract(RULES_UNREADABLE)
        self.assertTrue(s.restricted)

    def test_obfuscated_mentions_are_caught(self):
        s = sr.extract(RULES_QUOTED)
        for text in ["banana", "BANANA!", "b a n a n a", "b4n4n4", "bananas are good", "ban\u200bana", "b\u0430nana", "baaanana", "b.a.n.a.n.a"]:
            self.assertTrue(s.violates(text), text)
        for text in ["bandana", "nothing here", "ban an"]:
            self.assertFalse(s.violates(text), text)

    def test_redact_hides_term_but_keeps_text(self):
        s = sr.extract(RULES_QUOTED)
        out = s.redact("say banana now please")
        self.assertNotIn("banana", out)
        self.assertIn("please", out)
        self.assertFalse(s.violates(out))
        self.assertFalse(s.violates(s.redact("b a n a n a")))

    def test_cache_roundtrip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            a = sr.for_rules(RULES_QUOTED, d)
            files = [f for f in os.listdir(d) if f.startswith("speech_")]
            self.assertEqual(len(files), 1)
            self.assertEqual(sr.for_rules(RULES_QUOTED, d).terms, a.terms)
            with open(os.path.join(d, files[0]), "w") as fh:
                fh.write('{"terms": [')  # partial file written by someone else
            self.assertIn("banana", sr.for_rules(RULES_QUOTED, d).terms)
            self.assertEqual([f for f in os.listdir(d) if f.endswith(".tmp")], [])

    def test_unwritable_cache_dir_is_fine(self):
        with tempfile.NamedTemporaryFile() as f:  # a FILE used as the cache folder: makedirs fails
            self.assertIn("banana", sr.for_rules(RULES_QUOTED, f.name).terms)


class TestOutputFilters(unittest.TestCase):
    def test_conduct(self):
        for bad in ["you idiot", "You are STUPID", "1d10t", "i d i o t", "shut up", "kill yourself", "what a loser", "sh1t", "f u c k"]:
            line, problems = of.check_line(bad)
            self.assertTrue(problems, bad)
            self.assertNotEqual(line, bad)
        for ok in ["Good move.", "Your move.", "I like the board", "that is a diet plan", "I'm excited"]:
            self.assertEqual(of.check_line(ok)[1], [], ok)

    def test_leak_words_and_keys(self):
        for bad in ["my system prompt says", "I use haiku", "sk-abc123def456", "legal_actions are A1", "see /memory/x",
                    "token abcdefghijklmnopqrstuvwxyz0123456789", "my playbook says bluff", "I am an AI"]:
            self.assertTrue(of.check_line(bad)[1], bad)

    def test_private_state_never_leaves(self):
        line, problems = of.check_line("My number is 51", private_tokens=["51"])
        self.assertTrue(problems)
        self.assertNotIn("51", line)
        self.assertEqual(of.check_line("I have 52 problems", private_tokens=["51"])[1], [])

    def test_speech_filter(self):
        s = sr.extract(RULES_QUOTED)
        line, problems = of.check_line("Do you like banana?", speech=s)
        self.assertIn("speech:forbidden", problems)
        self.assertFalse(s.violates(line))

    def test_length_cut(self):
        line, _ = of.check_line("word " * 100)
        self.assertLessEqual(len(line), of.MAX_CHARS)
        self.assertLessEqual(len(line), of.CHAT_LIMIT)

    def test_never_empty(self):
        for x in (None, "", "   ", 5, ["a"]):
            line, problems = of.check_line(x)
            self.assertTrue(line.strip())
            self.assertTrue(problems)

    def test_every_template_passes_every_filter(self):
        s = sr.SpeechRules(["moon", "banana"])
        for intent, lines in intents.TEMPLATES.items():
            for t in lines:
                line = t.replace("{s}", "the centre")
                self.assertEqual(of.check_line(line, speech=s)[1], [], f"{intent}: {line}")
                self.assertLessEqual(len(line), of.MAX_CHARS)
        for n in of.NEUTRAL_LINES:
            self.assertEqual(of.check_line(n)[1], [], n)


class TestTemplates(unittest.TestCase):
    def test_slot_cleaning(self):
        self.assertEqual(intents.clean_slot("the centre"), "the centre")
        self.assertEqual(intents.clean_slot("x" * 100), "x" * 40)
        cleaned = intents.clean_slot("a{b}c<d> `e`")
        for ch in "{}<>`":
            self.assertNotIn(ch, cleaned)
        for bad in (None, 5, ["a"]):
            self.assertEqual(intents.clean_slot(bad), "")
        self.assertNotIn("{", intents.clean_slot("{s}"))

    def test_compose_basic_and_seeded(self):
        a = intents.compose("PRESS", "", "m1|1|3")
        self.assertEqual(a, intents.compose("PRESS", "", "m1|1|3"))
        self.assertTrue(a)
        self.assertNotIn("{s}", a)

    def test_unknown_intent_is_neutral(self):
        self.assertIn(intents.compose("???", "", "x"), intents.TEMPLATES["NEUTRAL"])
        self.assertEqual(intents.normalize_intent("press"), "PRESS")
        self.assertEqual(intents.normalize_intent(None), "NEUTRAL")

    def test_no_repeat(self):
        recent = []
        for turn in range(len(intents.TEMPLATES["NEUTRAL"])):
            line = intents.compose("NEUTRAL", "", f"m|1|{turn}", recent)
            self.assertNotIn(line, recent)
            recent.append(line)

    def test_slot_is_used_sometimes_and_never_leaves_a_hole(self):
        seen_slot = False
        for turn in range(40):
            line = intents.compose("PRESS", "the centre", f"m|1|{turn}")
            self.assertNotIn("{", line)
            seen_slot |= "the centre" in line
        self.assertTrue(seen_slot)

    def test_long_slot_line_is_cut(self):
        for intent in intents.INTENTS:
            for turn in range(10):
                line = of.cut_line(intents.compose(intent, "y" * 100, f"s|{turn}"))
                self.assertLessEqual(len(line), of.MAX_CHARS)


if __name__ == "__main__":
    unittest.main()
