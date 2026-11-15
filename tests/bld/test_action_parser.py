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

    def test_multiline_action_section_and_t1_games(self):
        # Connect four multi-line rules
        c4_rules = """CONNECT FOUR - 6 rows x 7 columns, connect 4 to win.
GOAL
Be the first to connect 4.
ACTION FORMAT
    drop <column>
where <column> is a number from 1 to 7 of a column that is not full.
Examples:  "drop 4"   "drop 1"   "drop 7"
Anything else is illegal.

WHAT YOU OBSERVE
"""
        g_c4 = parse_action_grammar(c4_rules)
        self.assertIn("drop 4", g_c4.examples)
        self.assertIn("drop 1", g_c4.examples)

        # Mini poker rules: must be discrete, not word game!
        poker_rules = """MINI POKER - Leduc poker, 8 hands.
ONE HAND
Betting round 1: bet size 2 chips.
ACTION FORMAT
Reply with exactly one word: check | bet | call | raise | fold
Examples: "bet", "raise", "fold"

WHAT YOU OBSERVE
"""
        g_poker = parse_action_grammar(poker_rules)
        self.assertEqual(g_poker.kind, "discrete")
        self.assertEqual(g_poker.discrete_actions, ["check", "bet", "call", "raise", "fold"])

        # Colonel blotto multi-line rules:
        blotto_rules = """COLONEL BLOTTO - 100 soldiers, 5 equal fields.
ACTION FORMAT
Your action is exactly 5 whole numbers >= 0 that add up to EXACTLY 100,
listed in battlefield order F1 to F5, separated by spaces.
Examples: "20 20 20 20 20", "35 35 30 0 0", "0 0 34 33 33".
Wrong total is illegal.

WHAT YOU OBSERVE
"""
        g_blotto = parse_action_grammar(blotto_rules)
        self.assertIn("20 20 20 20 20", g_blotto.examples)

    def test_fallback_action_with_rules(self):
        from core.fallback import fallback_action
        c4_rules = """CONNECT FOUR
ACTION FORMAT
drop <col>
Examples: "drop 4", "drop 1"

OBSERVATION
"""
        # When artifacts is empty, fallback_action extracts examples from rules
        act = fallback_action(None, {}, rules=c4_rules)
        self.assertEqual(act, "drop 4")

        # When avoid has first example, it picks second
        act2 = fallback_action(None, {}, avoid_also=["drop 4"], rules=c4_rules)
        self.assertEqual(act2, "drop 1")

    def test_word_grammar_case_fallback(self):
        g_lower = ActionGrammar(kind="word", word_length=5, word_prefix="guess ", case="lower")
        fb_l = g_lower.fallback_action()
        self.assertTrue(fb_l.startswith("guess "))
        self.assertTrue(fb_l[6:].islower())

        g_upper = ActionGrammar(kind="word", word_length=5, word_prefix="guess ", case="upper", case_sensitive=True)
        fb_u = g_upper.fallback_action()
        self.assertTrue(fb_u.startswith("guess "))
        self.assertTrue(fb_u[6:].isupper())

    def test_grid_validation_without_explicit_dims(self):
        g = ActionGrammar(kind="grid", grid_cols=0, grid_rows=0)
        self.assertTrue(g.validate("A1"))
        self.assertTrue(g.validate("B2"))
        self.assertTrue(g.validate("move C3"))
        self.assertFalse(g.validate("invalid_token"))


if __name__ == "__main__":
    unittest.main()
