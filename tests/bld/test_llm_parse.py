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

    def test_validate_int_action(self):
        from core.validate import validate
        res = validate(42, ["42", "43"])
        self.assertEqual(res, "42")

    def test_generic_action_and_chat_keys(self):
        from core.generic import Generic
        from strategies.base import TurnState
        class FakeLLM:
            def available(self): return True
            def over_budget(self): return False
            def ask_json(self, system, user, **kw):
                return {"action": "B2", "chat": "Move made."}

        st = TurnState(
            game_id="test", rules="grid game", variant={}, seat=0,
            observation="board: ...", legal_actions=["A1", "B2"], turn=1,
            warning=None, opponent_chat=[], artifacts={}, chat_full=[],
            my_actions=[], new_feedback=[], match_id="m1", game_index=1,
            opponent="bot", deadline=1000000.0, llm=FakeLLM()
        )
        gen = Generic()
        dec = gen.decide(st)
        self.assertEqual(dec.action, "B2")
        self.assertEqual(dec.chat, "Move made.")


if __name__ == "__main__":
    unittest.main()
