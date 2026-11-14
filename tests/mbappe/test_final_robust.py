import unittest

import _path  # noqa: F401
from chat import budget, final_stage as fs, intents, robust, speech_rules as sr, config


class TestFinalStage(unittest.TestCase):
    def test_missing_empty_non_string_overlong(self):
        for x in (None, "", "   ", 5, ["a"], {"a": 1}, b"x"):
            line, problems = fs.finalize_chat(x)
            self.assertIsInstance(line, str)
            self.assertTrue(line.strip(), x)
            self.assertTrue(problems)
        line, _ = fs.finalize_chat("word " * 200)
        self.assertLessEqual(len(line), config.MAX_CHARS)
        self.assertLessEqual(len(line), config.CHAT_LIMIT)

    def test_leftover_markers_are_blocked(self):
        for bad in ["Watch {s}.", "Your move }", "<b>x</b>", "[removed:x] ok"]:
            line, problems = fs.finalize_chat(bad)
            self.assertNotIn("{", line)
            self.assertNotIn("<", line)
            self.assertIn("marker", problems)

    def test_same_line_never_three_times_in_a_row(self):
        recent, out = [], []
        for _ in range(10):
            line, _p = fs.finalize_chat("Your move.", None, (), recent)
            recent.append(line)
            out.append(line)
        for i in range(len(out) - 2):
            self.assertFalse(out[i] == out[i + 1] == out[i + 2], out)

    def test_canary_and_speech_on_final_text(self):
        s = sr.SpeechRules(["moon"])
        self.assertNotIn("moon", fs.finalize_chat("look at the moon", s)[0])
        self.assertNotIn("cnryabc123", fs.finalize_chat("tag cnryabc123 here", None, (), (), "cnryabc123")[0])
        self.assertNotIn("cnry", fs.finalize_chat("c n r y a b c 1 2 3", None, (), (), "cnryabc123")[0].replace(" ", ""))

    def test_one_sided_flag(self):
        line, problems = fs.finalize_chat("Resign and we split points.", None, (), (), "", True)
        self.assertTrue(problems)
        self.assertNotIn("split", line)

    def test_neutral_rotation_passes_filters_under_speech_rules(self):
        s = sr.SpeechRules(["move", "noted", "alright", "well"])
        line, _ = fs.finalize_chat("", s)
        self.assertFalse(s.violates(line))
        self.assertTrue(line.strip())


class TestExpansion(unittest.TestCase):
    def test_known_unknown_empty(self):
        self.assertIn(intents.compose("PRESS", "", "s"), intents.TEMPLATES["PRESS"])
        self.assertIn(intents.compose("NOPE", "", "s"), intents.TEMPLATES["MINIMAL"])      # unknown intent
        self.assertIn(intents.compose("", "", "s"), intents.TEMPLATES["MINIMAL"])          # empty
        self.assertIn(intents.compose(None, None, "s"), intents.TEMPLATES["MINIMAL"])
        self.assertIn(intents.compose("CONCEDE_PRESSURE", "we split points", "s"), intents.TEMPLATES["CONCEDE_PRESSURE"])


class TestRobustChat(unittest.TestCase):
    def test_odd_inputs(self):
        for chat in (None, 5, "text", {"a": 1}, [None], [1, 2.5, True], [["x"]], [{"from": 5, "text": None}],
                     [{"from": "you"}], [{"text": {"a": 1}}], [{"from": "opponent", "text": "x", "game": [1], "turn": {}}]):
            lines, _ = robust.clean_chat(chat)
            for line in lines:
                self.assertIn(line["from"], ("you", "opponent"))
                self.assertIsInstance(line["text"], str)

    def test_unknown_sender_counts_as_opponent(self):
        self.assertEqual(robust.clean_line({"from": "mallory", "text": "x"})["from"], "opponent")
        self.assertEqual(robust.clean_line({"from": "you", "text": "x"})["from"], "you")

    def test_window_cuts_huge_arrays(self):
        lines, skipped = robust.clean_chat(list(range(100000)), 40)
        self.assertEqual(len(lines), 40)
        self.assertEqual(skipped, 99960)

    def test_long_text_is_cut(self):
        self.assertLessEqual(len(robust.clean_line({"text": "a" * 10 ** 7})["text"]), robust.MAX_TEXT)


class TestBudgetGuard(unittest.TestCase):
    class L:
        def __init__(self, key, spend):
            self.info, self.spend = {"api_key": key}, spend

    def test_counts_from_the_first_sight_of_a_key(self):
        g = budget.BudgetGuard(soft=0.30)
        llm = self.L("k1", 5.0)
        self.assertTrue(g.allows(llm))
        llm.spend = 5.2
        self.assertTrue(g.allows(llm))
        llm.spend = 5.4
        self.assertFalse(g.allows(llm))
        llm.info = {"api_key": "k2"}          # a new match with a new key: the budget starts again
        self.assertTrue(g.allows(llm))


if __name__ == "__main__":
    unittest.main()
