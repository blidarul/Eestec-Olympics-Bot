"""Tests for Pipeline Audit and Breakage Fixes.
Verifies:
1. Cross-game artifact isolation in main.py pick_artifacts().
2. Wordle uppercase and lowercase detection, validation, and fallback casing.
3. Runtime wiring of Connect Four bitboard solver in generic.decide().
4. Runtime wiring of Wordle Duel entropy solver in generic.decide().
5. Simulator calibration terminal verification.
6. new_lines observation diffing robustness.
"""
import pytest
import main
from core import fallback, generic, validate
from prep.action_parser import parse_action_grammar, ActionGrammar
from prep.synthesis import calibrate_simulator, synthesize_simulator_code
from prep.classifier import GameClassification
from strategies.base import TurnState
from tests.bld.test_connect_four import C4_6X7_OBS


def test_pick_artifacts_game_isolation():
    """Ensure artifacts from Game A never leak into Game B."""
    main.STATE["prep"] = {
        "game_id": "game_a",
        "by_label": {"3x3": {"family": "tic_tac_toe", "grammar": {"kind": "grid"}}},
        "first": "3x3",
    }
    class DummyWk:
        def ask(self, req, timeout):
            return {"artifacts": {"family": "game_b_family", "from_memory": True}}

    wk = DummyWk()
    # Game B starts
    msg_b = {"game_id": "game_b", "rules": "Wordle rules", "variant": {"label": "duel"}}
    art = main.pick_artifacts(msg_b, wk)
    assert art.get("family") == "game_b_family", "Game A artifacts must not leak into Game B!"


def test_wordle_uppercase_case_detection_and_validation():
    """Wordle games with uppercase examples / rules must validate and fallback to uppercase."""
    rules_upper = """WORDLE DUEL
    Guess the secret 5-letter word in ALL CAPS.
    ACTION FORMAT:
    Reply with one word: "CRANE", "SLATE", "AUDIO"
    """
    grammar = parse_action_grammar(rules_upper)
    assert grammar.case == "upper"
    assert grammar.to_dict()["case"] == "upper"

    artifacts = {
        "family": "wordle",
        "grammar": grammar.to_dict(),
        "action_format": {"examples": ["CRANE", "SLATE"]},
    }
    # Validator should output uppercase
    v = validate.validate("crane", None, artifacts)
    assert v == "CRANE", f"Expected uppercase CRANE, got {v}"

    # Fallback should output uppercase
    fb = fallback.fallback_action(None, artifacts)
    assert fb.isupper(), f"Expected uppercase fallback, got {fb}"


def test_wordle_lowercase_case_detection_and_validation():
    """Word games with lowercase examples must validate to lowercase."""
    rules_lower = """Word game: guess a 5-letter word like 'crane' or 'slate'."""
    grammar = parse_action_grammar(rules_lower)
    assert grammar.case == "lower"
    artifacts = {
        "family": "wordle",
        "grammar": grammar.to_dict(),
        "action_format": {"examples": ["crane", "slate"]},
    }
    v = validate.validate("CRANE", None, artifacts)
    assert v == "crane", f"Expected lowercase crane, got {v}"


def test_connect_four_runtime_wiring():
    """TurnState for Connect Four must be solved via bitboard solver in generic.decide()."""
    rules = "Connect Four on a 6x7 board. Drop a disc into a column. Four in a row wins."
    art = {
        "family": "grid_board",
        "grammar": {
            "kind": "grid",
            "grid_rows": 6,
            "grid_cols": 7,
            "parameters": {"gravity": True, "connect_k": 4},
        },
    }
    state = TurnState(
        game_id="c4_game",
        rules=rules,
        variant={"label": "6x7"},
        seat=0,
        observation=C4_6X7_OBS,
        legal_actions=["drop 1", "drop 2", "drop 3", "drop 4", "drop 5", "drop 6", "drop 7"],
        turn=5,
        warning=None,
        opponent_chat=[],
        artifacts=art,
        deadline=100.0,
    )
    decision = generic.STRATEGY.decide(state)
    assert decision.action == "drop 4", f"Expected winning move drop 4, got {decision.action}"
    assert decision.source == "strategy"
    assert decision.info.get("engine") == "python_bitboard"


def test_wordle_duel_runtime_wiring():
    """TurnState for Wordle Duel must be solved via entropy solver in generic.decide()."""
    rules = "Wordle Duel: guess the secret 5-letter word."
    art = {
        "family": "wordle",
        "grammar": {"kind": "word", "word_length": 5, "case": "upper"},
        "action_format": {"examples": ["SLATE"]},
    }
    state = TurnState(
        game_id="wordle_game",
        rules=rules,
        variant={"label": "duel"},
        seat=0,
        observation="Round 1: guess a word",
        legal_actions=None,
        turn=1,
        warning=None,
        opponent_chat=[],
        artifacts=art,
        deadline=100.0,
    )
    decision = generic.STRATEGY.decide(state)
    assert len(decision.action) == 5
    assert decision.action.isupper()
    assert decision.source == "strategy"
    assert decision.info.get("tool") == "wordle_duel_entropy"


def test_simulator_calibration_terminal_verified():
    """calibrate_simulator must verify that a game can reach terminal state."""
    cls = GameClassification(
        family="grid_board",
        confidence=1.0,
        is_deterministic=True,
        has_hidden_information=False,
        is_simultaneous=False,
        turn_structure="alternating",
    )
    grammar = ActionGrammar(kind="grid", grid_rows=3, grid_cols=3, grid_col_letters=["A", "B", "C"])
    code = synthesize_simulator_code(cls, grammar, "test_ttt")
    ns = {}
    exec(code, ns)
    calib = calibrate_simulator(ns["State"])
    assert calib["calibrated"] is True
    assert calib["is_terminal_verified"] is True, "Tic-Tac-Toe simulator must reach terminal in playouts"


def test_new_lines_whitespace_robustness():
    """new_lines must compare trimmed lines and return trimmed content."""
    prev = "  Round 1  \nScore: 0\n"
    obs = "  Round 1  \nScore: 0\n  New Event Occurred  \n"
    diff = main.new_lines(obs, prev)
    assert diff == ["New Event Occurred"]
