import json
import os
import tempfile
import threading
import time
import unittest

import _path  # noqa: F401
from opponent import patterns
from opponent.tracker import OpponentTracker, neutral_profile, safe_name


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = OpponentTracker(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, name="team-beta"):
        return os.path.join(self.tmp.name, "opponents", safe_name(name) + ".json")

    def test_unseen_opponent_gets_the_neutral_profile(self):
        p = self.t.get_profile("nobody")
        self.assertEqual(p, neutral_profile())
        self.assertFalse(p["known"])
        self.assertEqual((p["cooperation_rate"], p["bluff_rate"], p["dominant_actions"]), (0.5, 0.5, []))

    def test_recording_and_profile(self):
        for i, move in enumerate(["rock", "rock", "paper", "rock", "scissors"]):
            self.t.record_turn("team-beta", "rps", "paper", move, "hello", {"match_id": "m%d" % (i // 3)})
        p = self.t.get_profile("team-beta")
        self.assertTrue(p["known"])
        self.assertEqual(p["turns"], 5)
        self.assertEqual(p["match_count"], 2)
        self.assertEqual(p["dominant_actions"][0], "rock")
        self.assertEqual(p["recent_moves"], ["rock", "rock", "paper", "rock", "scissors"])
        self.assertTrue(os.path.exists(self.file()))

    def test_cooperation_and_bluff_rates(self):
        for move in ["cooperate", "cooperate", "defect", "cooperate"]:
            self.t.record_turn("pd", "dilemma", "cooperate", move, None)
        self.assertAlmostEqual(self.t.get_profile("pd")["cooperation_rate"], 0.75)
        for bluffed in (True, False, True, True):
            self.t.record_turn("bluffer", "poker", "call", "bet", None, {"bluffed": bluffed})
        self.assertAlmostEqual(self.t.get_profile("bluffer")["bluff_rate"], 0.75)
        self.t.record_turn("x", "g", "a", "b", None, {"cooperated": False})
        self.assertEqual(self.t.get_profile("x")["cooperation_rate"], 0.0)

    def test_cycle_period_and_chat_counters(self):
        for move in ["rock", "paper", "scissors"] * 3:
            self.t.record_turn("cyc", "rps", "rock", move, "fold now")
        p = self.t.get_profile("cyc")
        self.assertEqual(p["cycle_period"], 3)
        self.assertEqual(p["pressure_rate"], 1.0)
        self.assertEqual(p["repeat_rate"], 8 / 9)

    def test_chat_text_is_not_stored(self):
        self.t.record_turn("t", "g", "a", "b", "a secret sentence xyz")
        data = json.load(open(self.file("t"), encoding="utf-8"))
        self.assertNotIn("xyz", json.dumps({k: v for k, v in data.items() if k != "last_chat"}))

    def test_missing_corrupt_partial_and_wrong_shape_files(self):
        os.makedirs(os.path.join(self.tmp.name, "opponents"))
        for content in ['{"turns": ', "not json", "[]", '{"turns": "many", "recent": 5, "overall": []}', ""]:
            with open(self.file("bad"), "w", encoding="utf-8") as fh:
                fh.write(content)
            self.assertFalse(self.t.get_profile("bad")["known"] and content == "")
            self.t.record_turn("bad", "g", "a", "rock", None)          # starts again instead of failing
            self.assertEqual(self.t.get_profile("bad")["dominant_actions"], ["rock"])
            os.remove(self.file("bad"))

    def test_unwritable_memory_never_raises(self):
        with tempfile.NamedTemporaryFile() as f:                       # a FILE used as the memory folder
            t = OpponentTracker(f.name)
            t.record_turn("a", "g", "x", "y", "z")
            self.assertFalse(t.get_profile("a")["known"])

    def test_garbage_arguments_never_raise(self):
        for args in [(None, None, None, None, None), (5, [], {}, 7, b"x"), ("n", "g", "a", "", ""), ("n/../../etc", "g", "a", "b", None)]:
            self.t.record_turn(*args)
            self.t.get_profile(args[0])
        self.t.record_turn("n", "g", "a", "b", None, "not a dict")
        self.assertTrue(all(".." not in f for f in os.listdir(os.path.join(self.tmp.name, "opponents"))))

    def test_atomic_write_leaves_no_temp_files(self):
        for i in range(20):
            self.t.record_turn("a", "g", "x", "m%d" % i, None)
        names = os.listdir(os.path.join(self.tmp.name, "opponents"))
        self.assertEqual(names, ["a.json"])
        self.assertLessEqual(len(self.t.get_profile("a")["recent_moves"]), 20)

    def test_file_stays_small(self):
        for i in range(400):
            self.t.record_turn("big", "g", "x", "move%d" % i, None, {"match_id": "m%d" % i})
        self.assertLess(os.path.getsize(self.file("big")), 40000)
        p = self.t.get_profile("big")
        self.assertLessEqual(p["match_count"], 200)

    def test_parallel_writers_do_not_corrupt_the_file(self):
        def work(k):
            tr = OpponentTracker(self.tmp.name)
            for i in range(25):
                tr.record_turn("shared", "g", "x", "m%d" % k, None)
        threads = [threading.Thread(target=work, args=(k,)) for k in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        json.load(open(self.file("shared"), encoding="utf-8"))          # still valid JSON
        self.assertTrue(self.t.get_profile("shared")["known"])

    def test_lookup_is_fast(self):
        for i in range(50):
            self.t.record_turn("fast", "g", "x", "rock", "hi")
        t0 = time.perf_counter()
        for _ in range(100):
            self.t.get_profile("fast")
        self.assertLess((time.perf_counter() - t0) / 100, 0.005)

    def test_names_are_sanitized(self):
        self.assertEqual(safe_name("a/b\\c:d"), "a_b_c_d")
        self.assertEqual(safe_name(""), "unknown")
        self.assertEqual(safe_name(None), "unknown")
        self.assertLessEqual(len(safe_name("x" * 500)), 60)


class TestPatterns(unittest.TestCase):
    def test_cycles(self):
        self.assertEqual(patterns.detect_cycle(["a", "b"] * 3), 2)
        self.assertEqual(patterns.detect_cycle(["a", "b", "c"] * 2), 3)
        self.assertEqual(patterns.detect_cycle(["x", "x", "x"]), 1)
        self.assertIsNone(patterns.detect_cycle(["a", "b", "c", "a", "c", "b"]))
        self.assertIsNone(patterns.detect_cycle([]))

    def test_predictions(self):
        seq = ["rock", "paper", "scissors"] * 4
        self.assertEqual(patterns.predict_next(seq, ["rock", "paper", "scissors"])[:1], ("rock",))
        self.assertEqual(patterns.predict_next(["rock", "paper"], ["rock", "paper", "scissors"])[2], "none")
        move, conf, how = patterns.predict_next(["rock"] * 7 + ["paper", "rock", "rock"], ["rock", "paper", "scissors"])
        self.assertEqual(move, "rock")


if __name__ == "__main__":
    unittest.main()
