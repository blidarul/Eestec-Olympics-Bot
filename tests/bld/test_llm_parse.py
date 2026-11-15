"""Unit tests for robust LLM JSON parsing (Rule 7.4)."""
import unittest
from core.llm import parse_json


class TestLLMParse(unittest.TestCase):
    def test_standard_json(self):
        text = '{"a": "B2", "c": "Your move."}'
        res = parse_json(text)
        self.assertEqual(res, {"a": "B2", "c": "Your move."})

    def test_markdown_code_fence(self):
        text = "Here is my move:\n```json\n{\n  \"a\": \"C3\",\n  \"c\": \"Done.\"\n}\n```\nGood luck."
        res = parse_json(text)
        self.assertEqual(res, {"a": "C3", "c": "Done."})

    def test_trailing_comma(self):
        text = '{"a": "D4", "c": "Playing move.",}'
        res = parse_json(text)
        self.assertEqual(res, {"a": "D4", "c": "Playing move."})

    def test_multiple_objects_prefers_final(self):
        text = 'Thought: {"analysis": "opponent threatens C3"} Final answer: {"a": "C3", "c": "Blocked."}'
        res = parse_json(text)
        self.assertEqual(res, {"a": "C3", "c": "Blocked."})

    def test_empty_and_garbage(self):
        self.assertIsNone(parse_json(""))
        self.assertIsNone(parse_json(None))
        self.assertIsNone(parse_json("No json here!"))


if __name__ == "__main__":
    unittest.main()
