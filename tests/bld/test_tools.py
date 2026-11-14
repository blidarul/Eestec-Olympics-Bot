"""Unit tests for prep/tools.py (LLM tool synthesizer and executor).
Owned by agent `bld`.
"""
import shutil
import tempfile
import unittest

from prep.action_parser import parse_action_grammar
from prep.classifier import classify_rules
from prep.engine import PrepEngine
from prep.heuristics import compute_heuristics
from prep.tools import (
    ToolDefinition,
    ToolRegistry,
    synthesize_tools,
)


class TestToolSynthesizer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_tools_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tool_definition_and_schema_export(self):
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"arg1": {"type": "string"}},
                "required": ["arg1"],
            },
            handler=lambda arg1: {"echo": arg1},
        )
        schema = tool.to_openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "test_tool")
        self.assertEqual(schema["function"]["description"], "A test tool")
        self.assertIn("arg1", schema["function"]["parameters"]["properties"])

        d = tool.to_dict()
        self.assertEqual(d["name"], "test_tool")
        self.assertNotIn("handler", d)

    def test_tool_registry_execution(self):
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="add_nums",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
            handler=lambda a, b: {"sum": a + b},
        )
        registry.register(tool)

        # Execution success
        res = registry.execute("add_nums", {"a": 10, "b": 25})
        self.assertTrue(res["success"])
        self.assertEqual(res["result"]["sum"], 35)

        # Missing tool
        missing = registry.execute("non_existent", {})
        self.assertFalse(missing["success"])
        self.assertIn("not found", missing["error"])

        # Format for prompt
        prompt_txt = registry.format_for_prompt()
        self.assertIn("add_nums", prompt_txt)

    def test_universal_tools(self):
        rules = "Tic-Tac-Toe is played on a 3x3 grid. Legal moves: A1, A2, A3, B1, B2, B3, C1, C2, C3.\nFORBIDDEN WORDS: secret_key"
        cls = classify_rules(rules)
        grammar = parse_action_grammar(rules)
        heuristics = compute_heuristics(cls, grammar, rules)
        registry = synthesize_tools(cls, grammar, heuristics, rules)

        # check_move_legality
        res_legality = registry.execute("check_move_legality", {"action": "A1"})
        self.assertTrue(res_legality["success"])
        self.assertTrue(res_legality["result"]["is_legal"])

        bad_legality = registry.execute("check_move_legality", {"action": "INVALID_COORD_999"})
        self.assertTrue(bad_legality["success"])
        self.assertFalse(bad_legality["result"]["is_legal"])

        # sanitize_and_verify_chat
        res_chat = registry.execute("sanitize_and_verify_chat", {"message": "Hello, don't mention secret_key!"})
        self.assertTrue(res_chat["success"])
        self.assertIn("[redacted]", res_chat["result"]["safe_message"])
        self.assertIn("secret_key", res_chat["result"]["forbidden_keywords_found"])
        self.assertFalse(res_chat["result"]["is_clean"])

        clean_chat = registry.execute("sanitize_and_verify_chat", {"message": "Good luck!"})
        self.assertTrue(clean_chat["result"]["is_clean"])

    def test_grid_board_tools(self):
        rules = "Tic-Tac-Toe is played on a 3x3 grid. Line of 3 marks wins."
        cls = classify_rules(rules)
        grammar = parse_action_grammar(rules)
        heuristics = compute_heuristics(cls, grammar, rules)
        registry = synthesize_tools(cls, grammar, heuristics, rules)

        self.assertIsNotNone(registry.get("evaluate_board_position"))
        self.assertIsNotNone(registry.get("find_line_threats"))
        self.assertIsNotNone(registry.get("get_symmetry_equivalent_moves"))

        board_str = "A: X . .\nB: . X .\nC: . . O"
        eval_res = registry.execute("evaluate_board_position", {"board_observation": board_str, "my_mark": "X"})
        self.assertTrue(eval_res["success"])
        self.assertEqual(eval_res["result"]["my_pieces"], 2)
        self.assertEqual(eval_res["result"]["opp_pieces"], 1)

        sym_res = registry.execute("get_symmetry_equivalent_moves", {"move": "A1"})
        self.assertTrue(sym_res["success"])
        self.assertEqual(sym_res["result"]["orbit_size"], 4)  # Corners

    def test_dice_push_tools(self):
        rules = "Pig is a push-your-luck game. Roll a six-sided die. Accumulate turn points or hold to bank."
        cls = classify_rules(rules)
        grammar = parse_action_grammar(rules)
        heuristics = compute_heuristics(cls, grammar, rules)
        registry = synthesize_tools(cls, grammar, heuristics, rules)

        self.assertIsNotNone(registry.get("calculate_stopping_threshold"))
        self.assertIsNotNone(registry.get("estimate_bust_risk"))

        # Threshold test - below threshold rolls
        roll_res = registry.execute(
            "calculate_stopping_threshold",
            {"turn_score": 10, "my_bank": 30, "opp_bank": 20, "target_score": 100},
        )
        self.assertTrue(roll_res["success"])
        self.assertEqual(roll_res["result"]["recommended_action"], "roll")

        # Threshold test - above threshold holds
        hold_res = registry.execute(
            "calculate_stopping_threshold",
            {"turn_score": 25, "my_bank": 30, "opp_bank": 20, "target_score": 100},
        )
        self.assertTrue(hold_res["success"])
        self.assertEqual(hold_res["result"]["recommended_action"], "hold")

        # Immediate win holds
        win_res = registry.execute(
            "calculate_stopping_threshold",
            {"turn_score": 15, "my_bank": 90, "opp_bank": 50, "target_score": 100},
        )
        self.assertTrue(win_res["result"]["is_endgame_win"])
        self.assertEqual(win_res["result"]["recommended_action"], "hold")

        # Bust risk
        bust_res = registry.execute("estimate_bust_risk", {"turn_score": 20, "dice_sides": 6})
        self.assertTrue(bust_res["success"])
        self.assertAlmostEqual(bust_res["result"]["p_bust"], 1.0 / 6, places=3)

    def test_deduction_tools(self):
        rules = "Guess the secret number between 1 and 100. Feedback will be higher or lower."
        cls = classify_rules(rules)
        grammar = parse_action_grammar(rules)
        heuristics = compute_heuristics(cls, grammar, rules)
        registry = synthesize_tools(cls, grammar, heuristics, rules)

        self.assertIsNotNone(registry.get("compute_binary_search_guess"))
        self.assertIsNotNone(registry.get("update_search_interval"))

        guess_res = registry.execute("compute_binary_search_guess", {"min_val": 1, "max_val": 100})
        self.assertTrue(guess_res["success"])
        self.assertEqual(guess_res["result"]["recommended_guess"], 50)
        self.assertEqual(guess_res["result"]["candidate_count"], 100)

        # Update interval
        upd_res = registry.execute(
            "update_search_interval",
            {"last_guess": 50, "feedback": "Your guess is too low (target is higher)", "current_min": 1, "current_max": 100},
        )
        self.assertTrue(upd_res["success"])
        self.assertEqual(upd_res["result"]["updated_min"], 51)
        self.assertEqual(upd_res["result"]["updated_max"], 100)

    def test_cards_hidden_tools(self):
        rules = "Poker with cards, deck, bet, call, raise, pot, bluff."
        cls = classify_rules(rules)
        grammar = parse_action_grammar(rules)
        heuristics = compute_heuristics(cls, grammar, rules)
        registry = synthesize_tools(cls, grammar, heuristics, rules)

        self.assertIsNotNone(registry.get("calculate_pot_odds"))
        self.assertIsNotNone(registry.get("estimate_bluff_frequency"))

        odds_res = registry.execute("calculate_pot_odds", {"pot_size": 100.0, "call_cost": 25.0})
        self.assertTrue(odds_res["success"])
        self.assertEqual(odds_res["result"]["required_equity_percent"], 20.0)

        bluff_res = registry.execute("estimate_bluff_frequency", {"bet_size": 50.0, "pot_size": 100.0})
        self.assertTrue(bluff_res["success"])
        self.assertGreater(bluff_res["result"]["optimal_bluff_frequency"], 0.0)

    def test_negotiation_tools(self):
        rules = "Negotiate a trade. Propose an offer to divide the surplus deal."
        cls = classify_rules(rules)
        grammar = parse_action_grammar(rules)
        heuristics = compute_heuristics(cls, grammar, rules)
        registry = synthesize_tools(cls, grammar, heuristics, rules)

        self.assertIsNotNone(registry.get("evaluate_split_fairness"))
        self.assertIsNotNone(registry.get("calculate_counter_offer"))

        fair_res = registry.execute("evaluate_split_fairness", {"our_offer": 50.0, "opp_offer": 50.0, "total_pool": 100.0})
        self.assertTrue(fair_res["success"])
        self.assertTrue(fair_res["result"]["is_fair_split"])

    def test_prep_engine_generates_tools_json(self):
        msg = {
            "game_id": "test_ttt_game",
            "game_name": "Tic Tac Toe",
            "seconds": 600,
            "variants": [
                {
                    "label": "standard",
                    "rules": "Tic-Tac-Toe is played on a 3x3 grid. Line of 3 wins. Forbidden keyword: cheater.",
                    "sample_turn": {
                        "observation": "A: . . .\nB: . . .\nC: . . .",
                        "legal_actions": ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"],
                    },
                }
            ],
        }
        engine = PrepEngine(memory_dir=self.temp_dir)
        res = engine.run_prep(msg)
        self.assertEqual(res["type"], "ready")

        # Verify manifest has tools
        import json
        import os
        manifest_path = res["manifest_path"]
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertIn("tools", manifest)
        self.assertGreater(len(manifest["tools"]), 0)
        tool_names = [t["function"]["name"] for t in manifest["tools"]]
        self.assertIn("check_move_legality", tool_names)
        self.assertIn("evaluate_board_position", tool_names)
        self.assertIn("find_line_threats", tool_names)

        # Verify tools.json exists in game directory
        tools_path = os.path.join(os.path.dirname(manifest_path), "tools.json")
        self.assertTrue(os.path.exists(tools_path))
        with open(tools_path, "r", encoding="utf-8") as f:
            tools_json = json.load(f)
        self.assertEqual(len(tools_json), len(manifest["tools"]))


if __name__ == "__main__":
    unittest.main()
