"""solvers/deduce.py (layer 3, M1): every feedback model solved with simulated secrets, never repeats, tool + detector."""
import random
import time

import pytest

from solvers import catalog
from solvers.deduce import best_guess, deduce, make_model
from solvers.precompute import precompute


def play(model, params, secret, cap, mode="entropy", words=None, expect_text=False):
    m = make_model(model, params, words)
    hist, made = [], []
    for n in range(1, cap + 1):
        r = deduce(model, params, hist, mode, time.monotonic() + 3, words=words)
        g = r["next_guess"]
        g = tuple(g) if isinstance(g, list) else g
        assert g not in made, "repeated guess"
        made.append(g)
        fb = m.feedback(secret, g)
        if m.won(fb):
            return n
        hist.append({"guess": m.fmt(g), "feedback": list(fb) if isinstance(fb, tuple) else fb})
    return None


def test_numeric_binary_search_bound():
    rnd = random.Random(1)
    for _ in range(25):
        s = rnd.randint(1, 100)
        assert play("numeric", {"lo": 1, "hi": 100}, s, 7, "minimax") is not None


@pytest.mark.parametrize("mode", ["entropy", "minimax"])
def test_pegs_solved_within_limit(mode):
    p = {"length": 4, "alphabet": "123456", "repeat": True}
    rnd = random.Random(2)
    for _ in range(4):
        s = tuple(rnd.choice("123456") for _ in range(4))
        assert play("pegs", p, s, 9, mode) is not None


def test_pegs_no_repeat_alphabet_digits():
    p = {"length": 3, "alphabet": "0123456789", "repeat": False}
    for s in [("1", "2", "3"), ("9", "0", "5")]:
        assert play("pegs", p, s, 8) is not None


def test_pegs_feedback_values():
    m = make_model("pegs", {"length": 4, "alphabet": "123456"})
    assert m.feedback(tuple("1123"), tuple("1211")) == (1, 2)
    assert m.parse_feedback("2 exact, 1 partial") == (2, 1)
    assert m.parse_feedback("1 cow 2 bulls") == (2, 1)


WORDS = ["crane", "slate", "trace", "crate", "plate", "place", "grace", "brace", "stare", "share", "shale", "whale",
         "while", "write", "wrote", "grate", "irate", "skate", "state", "stake", "snake", "shake", "spade", "space"]


def test_positional_with_wordlist():
    for s in WORDS[:8]:
        assert play("positional", {"length": 5}, s, 6, words=WORDS) is not None


def test_positional_duplicate_letters():
    m = make_model("positional", {"length": 5}, WORDS)
    assert m.feedback("crate", "eerie") == (0, 0, 1, 0, 2)
    assert m.parse_feedback("gyxxg") == (2, 1, 0, 0, 2)


def test_distance_exact_and_buckets():
    assert play("distance", {"lo": 1, "hi": 100}, 37, 8) is not None
    assert play("distance", {"lo": 1, "hi": 100, "edges": [2, 10, 30]}, 61, 12) is not None


def test_best_guess_never_repeats_and_sampling():
    cands = list(range(1000))
    fb = lambda s, g: (s > g) - (s < g)
    g = best_guess(cands, cands, fb, "minimax", time.monotonic() + 1, exclude={500})
    assert g != 500 and 300 < g < 700
    assert best_guess([7], [7, 8], fb, "entropy", None) == 7
    assert best_guess([7], [7], fb, "entropy", None, exclude={7}) is None


def test_deadline_respected_on_large_space():
    p = {"length": 5, "alphabet": "abcdefghij", "repeat": True}   # 100000 > cap -> clean error, no hang
    t = time.monotonic()
    r = catalog.call("deduce_next", {"model": "pegs", "params": p, "history": []}, time.monotonic() + 1)
    assert time.monotonic() - t < 2
    assert r["ok"] is False
    p = {"length": 5, "alphabet": "abcdefg", "repeat": True}      # 16807 candidates
    t = time.monotonic()
    r = catalog.call("deduce_next", {"model": "pegs", "params": p, "history": []}, time.monotonic() + 1.0)
    assert time.monotonic() - t < 1.6


def test_tool_json_roundtrip_and_contradiction():
    r = catalog.call("deduce_next", {"model": "numeric", "params": {"lo": 1, "hi": 100},
                                     "history": [{"guess": 50, "feedback": "higher"}, {"guess": 75, "feedback": "lower"}]})
    assert r["ok"] and r["result"]["candidates"] == 24 and 50 < r["result"]["next_guess"] < 75
    r = catalog.call("deduce_next", {"model": "numeric", "params": {"lo": 1, "hi": 10},
                                     "history": [{"guess": 5, "feedback": "higher"}, {"guess": 6, "feedback": "lower"}]})
    assert r["ok"] and r["result"]["contradictory_history"]
    assert catalog.call("deduce_next", {"model": "nope", "params": {}})["ok"] is False
    assert catalog.call("deduce_next", {"model": "pegs", "params": {"length": 4}})["ok"] is False


def test_certain_when_one_candidate():
    r = catalog.call("deduce_next", {"model": "numeric", "params": {"lo": 1, "hi": 100},
                                     "history": [{"guess": 50, "feedback": "higher"}, {"guess": 75, "feedback": "lower"},
                                                 {"guess": 62, "feedback": "higher"}, {"guess": 68, "feedback": "lower"},
                                                 {"guess": 65, "feedback": "higher"}, {"guess": 66, "feedback": "higher"}]})
    assert r["result"]["candidates"] == 1 and r["result"]["certain"] and r["result"]["next_guess"] == 67


# ---- detector (precompute)

PEG_RULES = ("CODE BREAKER. The opponent picks a secret code of 4 digits (0-9, no repeated digits). Each round you guess "
             "a code; you are told how many digits are exact (right digit, right place) and partial. Action: guess <code>.")


def run(obs, legal, rules, art=None):
    return precompute(obs, legal, art or {}, rules, time.monotonic() + 5)


def test_detector_pegs_fact_and_time():
    obs = "Round 3 of 10.\n  Round 1: you guessed 1234 -> 1 exact, 1 partial\n  Round 2: you guessed 1567 -> 0 exact, 1 partial\n"
    t = time.monotonic()
    f = run(obs, None, PEG_RULES)
    assert time.monotonic() - t < 0.5
    assert "deduce_next" in f.used and any("candidate" in l for l in f.lines)
    assert any("1234" in l for l in f.lines)


def test_detector_silent_on_unrelated_rules():
    f = run("Your move.", None, "Tic-tac-toe on a 3x3 board. Three in a row wins.")
    assert "deduce_next" not in f.used


def test_detector_numeric_left_to_binary_search():
    rules = "Guess the secret number between 1 and 100. Feedback: higher or lower."
    f = run("Round 1.\n", None, rules)
    assert "deduce_next" not in f.used


def test_prepared_feedback_model_is_used():
    class FM:
        def space(self):
            return list(range(1, 21))

        def feedback(self, s, g):
            return "correct" if s == g else ("higher" if s > g else "lower")

    obs = "  Round 1: you guessed 10 -> higher\n"
    f = run(obs, None, "Guess the secret value, we tell you the feedback.", {"feedback_model": FM()})
    assert "deduce_next" in f.used and any("10 candidates" in l for l in f.lines)
