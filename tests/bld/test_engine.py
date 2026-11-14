"""Unit tests for prep/engine.py.
Owned by agent `bld`.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add arena-lite to path for importing practice games
repo_root = Path(__file__).resolve().parents[2]
arena_dir = repo_root / "arena-lite"
if str(arena_dir) not in sys.path:
    sys.path.insert(0, str(arena_dir))

from arena.practice.tic_tac_toe import TicTacToe
from optimization.serializer import load_json
from prep.engine import PrepEngine


class TestPrepEngine(unittest.TestCase):
    def setUp(self):
        self.temp_mem = tempfile.mkdtemp(prefix="test_prep_mem_")
        self.engine = PrepEngine(memory_dir=self.temp_mem)

    def tearDown(self):
        shutil.rmtree(self.temp_mem, ignore_errors=True)

    def test_run_prep_tic_tac_toe(self):
        # Build mock prep message
        variants = []
        for v in TicTacToe.variants():
            game = TicTacToe(dict(v), seed=42)
            variants.append({
                "label": v.get("label", ""),
                "rules": game.rules(),
                "sample_turn": {
                    "type": "turn",
                    "game_index": 1,
                    "turn": 1,
                    "observation": game.observation(0),
                    "legal_actions": ["A1", "A2", "B1", "B2"],
                },
            })

        msg = {
            "type": "prep",
            "game_id": "tic_tac_toe",
            "game_name": "Tic-Tac-Toe",
            "variants": variants,
            "seconds": 600.0,
            "you": "linux-pioneers",
        }

        res = self.engine.run_prep(msg)
        self.assertEqual(res["type"], "ready")
        self.assertEqual(res["game_id"], "tic_tac_toe")
        self.assertEqual(res["family"], "grid_board")
        self.assertTrue(os.path.exists(res["manifest_path"]))
        game_dir = os.path.join(self.temp_mem, "tic_tac_toe")
        self.assertTrue(os.path.exists(os.path.join(game_dir, "simulator.py")))
        self.assertTrue(os.path.exists(os.path.join(game_dir, "simulator_0.py")))
        self.assertTrue(os.path.exists(os.path.join(game_dir, "simulator_1.py")))

        manifest = load_json(res["manifest_path"])
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["game_id"], "tic_tac_toe")
        self.assertEqual(len(manifest["variants"]), len(variants))
        self.assertTrue(manifest["variants"][0]["sample_validation_passed"])
        self.assertIn("simulator_path", manifest["variants"][0])
        self.assertIn("simulator_path", manifest["variants"][1])
        self.assertTrue(os.path.exists(manifest["variants"][0]["simulator_path"]))
        self.assertTrue(os.path.exists(manifest["variants"][1]["simulator_path"]))


if __name__ == "__main__":
    unittest.main()
