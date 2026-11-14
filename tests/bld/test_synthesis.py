"""Unit tests for prep/synthesis.py.
Verifies dynamic simulator compilation, parse(observation, seat), and execution across game families.
Owned by agent `bld`.
"""
import os
import shutil
import tempfile
import unittest

from prep.action_parser import ActionGrammar
from prep.classifier import GameClassification
from prep.synthesis import (
    save_synthesized_simulator,
    synthesize_simulator_code,
)
from solvers.adapter import load_simulator_source
from solvers.verify import verify_report


class TestSynthesis(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_synthesis_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_grid_simulator_execution(self):
        cls_info = GameClassification(
            family="grid_board",
            confidence=0.9,
            is_deterministic=True,
            has_hidden_information=False,
            is_simultaneous=False,
            turn_structure="alternating",
        )
        grammar = ActionGrammar(
            kind="grid",
            grid_cols=3,
            grid_rows=3,
            parameters={"connect_k": 3},
        )

        code = synthesize_simulator_code(cls_info, grammar, "test_grid")
        namespace = {}
        exec(code, namespace)

        StateClass = namespace["State"]
        state = StateClass()

        actions = state.legal_actions()
        self.assertEqual(len(actions), 9)
        self.assertIn("B2", actions)

        # Test standard move
        state2 = state.step("B2")
        self.assertEqual(state2.current, 1)
        self.assertEqual(len(state2.legal_actions()), 8)

        # Test move with prefix "place A1"
        state3 = state2.step("place A1")
        self.assertEqual(state3.current, 0)
        self.assertEqual(len(state3.legal_actions()), 7)

    def test_dice_push_simulator_execution(self):
        cls_info = GameClassification(
            family="dice_push",
            confidence=0.9,
            is_deterministic=False,
            has_hidden_information=True,
            is_simultaneous=False,
            turn_structure="push_your_luck",
        )
        grammar = ActionGrammar(
            kind="discrete",
            discrete_actions=["roll", "hold"],
            parameters={"target_score": 50},
        )

        code = synthesize_simulator_code(cls_info, grammar, "test_push")
        namespace = {}
        exec(code, namespace)

        StateClass = namespace["State"]
        state = StateClass()
        self.assertEqual(state.legal_actions(), ["roll", "hold"])

        state_rolled = state.step("roll")
        # With dice chance outcome, turn_total may be 0 (if rolled 1) or > 0 (2..6)
        if state_rolled.turn_total > 0:
            state_held = state_rolled.step("hold")
            self.assertEqual(state_held.current, 1)
            self.assertGreater(state_held.banked[0], 0)

    def test_save_synthesized_simulator(self):
        cls_info = GameClassification(
            family="grid_board",
            confidence=0.9,
            is_deterministic=True,
            has_hidden_information=False,
            is_simultaneous=False,
            turn_structure="alternating",
        )
        grammar = ActionGrammar(kind="grid", grid_cols=3, grid_rows=3)

        path, calib = save_synthesized_simulator(self.temp_dir, cls_info, grammar, "test_save")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(calib.get("calibrated"))
        self.assertTrue(calib.get("usable"))
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("class State:", content)
        self.assertIn("def parse(", content)

    def test_parse_and_verify_tic_tac_toe(self):
        cls_info = GameClassification(
            family="grid_board",
            confidence=0.9,
            is_deterministic=True,
            has_hidden_information=False,
            is_simultaneous=False,
            turn_structure="alternating",
        )
        grammar = ActionGrammar(kind="grid", grid_cols=3, grid_rows=3, parameters={"connect_k": 3})
        code = synthesize_simulator_code(cls_info, grammar, "ttt_test")

        obs = (
            "TIC-TAC-TOE - 3x3 classic. You are seat 0 and play X; the opponent plays O.\n"
            "Your turn (move 1). Need 3 in a row.\n"
            "   A B C\n"
            " 1 . . .\n"
            " 2 . . .\n"
            " 3 . . .\n"
        )
        want_actions = ["A1", "B1", "C1", "A2", "B2", "C2", "A3", "B3", "C3"]
        variant = {"sample_turn": {"observation": obs, "legal_actions": want_actions, "seat": 0}}

        sim = load_simulator_source(code)
        ok, reason = verify_report(sim, variant)
        self.assertTrue(ok, f"Verification failed: {reason}")

    def test_parse_and_verify_pig(self):
        cls_info = GameClassification(
            family="dice_push",
            confidence=0.9,
            is_deterministic=False,
            has_hidden_information=True,
            is_simultaneous=False,
            turn_structure="push_your_luck",
        )
        grammar = ActionGrammar(
            kind="discrete",
            discrete_actions=["roll", "hold"],
            parameters={"target_score": 50},
        )
        code = synthesize_simulator_code(cls_info, grammar, "pig_test")

        obs = (
            "PIG - standard. You are seat 0. Target: 50.\n"
            "Banked: you 10, opponent 15.\n"
            "Turn 3: it is YOUR turn. Turn total: 6 (rolls this turn: 2+4).\n"
            "If you hold now you will have 16. Choose: roll | hold\n"
        )
        variant = {"sample_turn": {"observation": obs, "legal_actions": ["roll", "hold"], "seat": 0}}

        sim = load_simulator_source(code)
        ok, reason = verify_report(sim, variant)
        self.assertTrue(ok, f"Verification failed: {reason}")
        parsed_state = sim.parse(obs, 0)
        self.assertTrue(sim.has_chance(parsed_state))


if __name__ == "__main__":
    unittest.main()
