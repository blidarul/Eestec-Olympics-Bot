"""Unit tests for prep/action_parser.py.
Tested against real practice games: Tic-Tac-Toe, Guess the Number, Pig.
Owned by agent `bld`.
"""
import sys
import unittest
from pathlib import Path

# Add arena-lite to path for importing practice games
repo_root = Path(__file__).resolve().parents[2]
arena_dir = repo_root / "arena-lite"
if str(arena_dir) not in sys.path:
    sys.path.insert(0, str(arena_dir))

from arena.practice.guess_number import GuessNumber
from arena.practice.pig import Pig
from arena.practice.tic_tac_toe import TicTacToe
from prep.action_parser import (
    ActionGrammar,
    ObservationSchema,
    extract_forbidden_keywords,
    extract_game_parameters,
    infer_observation_schema,
    parse_action_grammar,
    parse_observation_layout,
)


class TestActionParser(unittest.TestCase):
    def test_tic_tac_toe_grammar(self):
        game = TicTacToe(TicTacToe.variants()[0], seed=42)
        rules = game.rules()

        grammar = parse_action_grammar(rules)
        self.assertEqual(grammar.kind, "grid")
        self.assertEqual(grammar.grid_cols, 3)
        self.assertEqual(grammar.grid_rows, 3)

        # Test validation
        self.assertTrue(grammar.validate("A1"))
        self.assertTrue(grammar.validate("b2"))
        self.assertTrue(grammar.validate("place C3"))
        self.assertFalse(grammar.validate("D4"))  # 3x3 out of bounds
        self.assertFalse(grammar.validate("invalid"))

        # Test normalization
        self.assertEqual(grammar.normalize("b2"), "B2")
        self.assertEqual(grammar.normalize("place a1"), "A1")

    def test_tic_tac_toe_5x5_grammar(self):
        game = TicTacToe(TicTacToe.variants()[1], seed=42)
        rules = game.rules()

        grammar = parse_action_grammar(rules)
        self.assertEqual(grammar.kind, "grid")
        self.assertEqual(grammar.grid_cols, 5)
        self.assertEqual(grammar.grid_rows, 5)

        self.assertTrue(grammar.validate("D4"))
        self.assertTrue(grammar.validate("E5"))
        self.assertFalse(grammar.validate("F6"))

    def test_pig_discrete_grammar(self):
        game = Pig(Pig.variants()[0], seed=42)
        rules = game.rules()

        grammar = parse_action_grammar(rules)
        self.assertEqual(grammar.kind, "discrete")
        self.assertIn("roll", grammar.discrete_actions)
        self.assertIn("hold", grammar.discrete_actions)

        self.assertTrue(grammar.validate("roll"))
        self.assertTrue(grammar.validate("HOLD"))
        self.assertTrue(grammar.validate("Roll"))
        self.assertFalse(grammar.validate("pass"))

        self.assertEqual(grammar.normalize("ROLL"), "roll")
        self.assertEqual(grammar.normalize("Hold"), "hold")

    def test_guess_number_numeric_grammar(self):
        game = GuessNumber(GuessNumber.variants()[0], seed=42)
        rules = game.rules()

        grammar = parse_action_grammar(rules)
        self.assertEqual(grammar.kind, "numeric_range")
        self.assertEqual(grammar.numeric_min, 1)
        self.assertEqual(grammar.numeric_max, 100)

        self.assertTrue(grammar.validate("guess 50"))
        self.assertTrue(grammar.validate("50"))
        self.assertTrue(grammar.validate("1"))
        self.assertTrue(grammar.validate("100"))
        self.assertFalse(grammar.validate("105"))
        self.assertFalse(grammar.validate("guess 0"))

        self.assertEqual(grammar.normalize("50"), "guess 50")
        self.assertEqual(grammar.normalize("guess 25"), "guess 25")

    def test_observation_layout_parsing(self):
        # Test Tic-Tac-Toe observation
        ttt = TicTacToe(TicTacToe.variants()[0], seed=42)
        obs_ttt = ttt.observation(0)
        layout_ttt = parse_observation_layout(obs_ttt)

        self.assertIn("lines", layout_ttt)
        self.assertIn("grid", layout_ttt)
        self.assertEqual(layout_ttt["grid_size"], (3, 3))

        # Test GuessNumber observation
        gn = GuessNumber(GuessNumber.variants()[0], seed=42)
        obs_gn = gn.observation(0)
        layout_gn = parse_observation_layout(obs_gn)

        self.assertEqual(layout_gn.get("seat"), 0)
        self.assertEqual(layout_gn.get("round"), 1)

    def test_fallback_action(self):
        grammar_grid = ActionGrammar(kind="grid", grid_cols=3, grid_rows=3)
        self.assertEqual(grammar_grid.fallback_action(), "A1")

        grammar_discrete = ActionGrammar(kind="discrete", discrete_actions=["roll", "hold"])
        self.assertEqual(grammar_discrete.fallback_action(), "roll")

        grammar_numeric = ActionGrammar(kind="numeric_range", numeric_min=1, numeric_max=100, numeric_prefix="guess ")
        self.assertEqual(grammar_numeric.fallback_action(), "guess 50")

    def test_forbidden_keywords_extraction(self):
        sample_rules = """GAME RULES
FORBIDDEN WORDS: apple, "banana peel", cherry
You must never mention "secret_code" in chat or you will be penalized.
        """
        forbidden = extract_forbidden_keywords(sample_rules)
        self.assertIn("apple", forbidden)
        self.assertIn("banana peel", forbidden)
        self.assertIn("secret_code", forbidden)

    def test_game_parameters_extraction(self):
        pig_rules = Pig(Pig.variants()[0], seed=42).rules()
        params = extract_game_parameters(pig_rules)
        self.assertEqual(params.get("target_score"), 50)
        self.assertEqual(params.get("move_cap"), 200)

        ttt_rules = TicTacToe(TicTacToe.variants()[1], seed=42).rules()
        params_ttt = extract_game_parameters(ttt_rules)
        self.assertEqual(params_ttt.get("connect_k"), 4)

    def test_observation_schema_inference(self):
        gn = GuessNumber(GuessNumber.variants()[0], seed=42)
        obs_gn = gn.observation(0)
        schema_gn = infer_observation_schema(obs_gn)

        self.assertIn("round", schema_gn.patterns)
        self.assertIn("secret", schema_gn.patterns)

        extracted = schema_gn.extract(obs_gn)
        self.assertEqual(extracted.get("round"), 1)
        self.assertEqual(extracted.get("secret"), gn.secrets[0])

        ttt = TicTacToe(TicTacToe.variants()[0], seed=42)
        schema_ttt = infer_observation_schema(ttt.observation(0))
        self.assertTrue(schema_ttt.has_grid)
        self.assertEqual((schema_ttt.grid_rows, schema_ttt.grid_cols), (3, 3))


if __name__ == "__main__":
    unittest.main()
