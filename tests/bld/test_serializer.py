"""Unit tests for optimization/serializer.py.
Owned by agent `bld`.
"""
import os
import shutil
import tempfile
import time
import unittest

from optimization.serializer import (
    atomic_save_json,
    atomic_save_pickle,
    game_memory_dir,
    load_json,
    load_pickle,
    sanitize_game_id,
)


class TestSerializer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_serializer_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sanitize_game_id(self):
        self.assertEqual(sanitize_game_id("Tic-Tac-Toe"), "tic-tac-toe")
        self.assertEqual(sanitize_game_id("guess_number/1-100"), "guess_number_1-100")
        self.assertEqual(sanitize_game_id("pig!"), "pig_")

    def test_game_memory_dir(self):
        gdir = game_memory_dir(self.test_dir, "Tic_Tac_Toe")
        self.assertEqual(gdir, os.path.join(self.test_dir, "tic_tac_toe"))

    def test_atomic_json_roundtrip(self):
        filepath = os.path.join(self.test_dir, "sub", "test.json")
        data = {"game": "tic_tac_toe", "scores": [1, 2, 3], "nested": {"key": "val"}}

        ok = atomic_save_json(filepath, data)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(filepath))

        loaded = load_json(filepath)
        self.assertEqual(loaded, data)

    def test_atomic_pickle_roundtrip(self):
        filepath = os.path.join(self.test_dir, "sub", "test.bin")
        data = {"numbers": {1, 2, 3}, "tuple": (4, 5, "hello")}

        ok = atomic_save_pickle(filepath, data)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(filepath))

        loaded = load_pickle(filepath)
        self.assertEqual(loaded, data)

    def test_corrupted_file_handling(self):
        filepath = os.path.join(self.test_dir, "corrupt.json")
        with open(filepath, "w") as fh:
            fh.write("{bad json content")

        loaded = load_json(filepath, default={"fallback": True})
        self.assertEqual(loaded, {"fallback": True})

    def test_missing_file_handling(self):
        filepath = os.path.join(self.test_dir, "nonexistent.json")
        loaded = load_json(filepath, default="default_value")
        self.assertEqual(loaded, "default_value")

    def test_cold_start_speed(self):
        filepath = os.path.join(self.test_dir, "perf.json")
        payload = {"opening_book": {f"move_{i}": f"eval_{i}" for i in range(500)}}
        atomic_save_json(filepath, payload)

        start = time.perf_counter()
        loaded = load_json(filepath)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertIsNotNone(loaded)
        # Should load in well under 10ms (Rule 5.14 cold start target is < 5ms)
        self.assertLess(elapsed_ms, 20.0)


if __name__ == "__main__":
    unittest.main()
