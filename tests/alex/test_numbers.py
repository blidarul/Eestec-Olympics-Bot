"""binary_search_next, bisect_predicate_points, dice_sum_distribution on normal and edge inputs."""
import itertools
from fractions import Fraction

import pytest

import solvers  # noqa: F401  (registers the tools)
from solvers import catalog


def ok(name, args):
    r = catalog.call(name, args)
    assert r["ok"], r
    return r["result"]


def bad(name, args):
    r = catalog.call(name, args)
    assert r["ok"] is False, r
    return r["error"]


# ---- binary_search_next

def test_bsn_fresh_interval():
    r = ok("binary_search_next", {"lo": 1, "hi": 100})
    assert (r["lo"], r["hi"], r["next_guess"], r["candidates"], r["max_guesses_left"]) == (1, 100, 50, 100, 7)


def test_bsn_follows_feedback():
    r = ok("binary_search_next", {"lo": 1, "hi": 100, "history": [{"guess": 50, "feedback": "higher"}]})
    assert (r["lo"], r["hi"], r["next_guess"], r["candidates"], r["max_guesses_left"]) == (51, 100, 75, 50, 6)
    r = ok("binary_search_next", {"lo": 1, "hi": 100, "history": [{"guess": 50, "feedback": "lower"}, {"guess": 25, "feedback": "higher"}]})
    assert (r["lo"], r["hi"]) == (26, 49)


def test_bsn_single_candidate_and_found():
    r = ok("binary_search_next", {"lo": 7, "hi": 7})
    assert r["next_guess"] == 7 and r["candidates"] == 1 and r["max_guesses_left"] == 1
    r = ok("binary_search_next", {"lo": 1, "hi": 10, "history": [{"guess": 4, "feedback": "correct"}]})
    assert r["found"] and r["next_guess"] == 4


def test_bsn_errors():
    assert "lo must be <= hi" in bad("binary_search_next", {"lo": 5, "hi": 1})
    assert "contradicts" in bad("binary_search_next", {"lo": 1, "hi": 10, "history": [{"guess": 5, "feedback": "higher"}, {"guess": 6, "feedback": "lower"}]})
    assert bad("binary_search_next", {"lo": 1, "hi": 10, "history": [{"guess": 5, "feedback": "warmer"}]})
    assert bad("binary_search_next", {"lo": 1})


def test_bsn_never_repeats_and_always_converges():
    for lo, hi in [(1, 1), (1, 2), (0, 99), (-50, 50), (1, 1000)]:
        for secret in {lo, hi, (lo + hi) // 2, lo + (hi - lo) // 3}:
            hist, seen = [], set()
            for step in range(20):
                r = ok("binary_search_next", {"lo": lo, "hi": hi, "history": hist})
                g = r["next_guess"]
                assert g not in seen
                if step == 0:
                    bound = r["max_guesses_left"]
                seen.add(g)
                fb = "correct" if g == secret else ("higher" if secret > g else "lower")
                hist.append({"guess": g, "feedback": fb})
                if fb == "correct":
                    assert len(hist) <= bound
                    break
            else:
                pytest.fail("did not converge")


def test_bsn_huge_range():
    r = ok("binary_search_next", {"lo": -10 ** 15, "hi": 10 ** 15})
    assert r["max_guesses_left"] == (2 * 10 ** 15 + 1).bit_length()


def test_bsn_odd_feedback_still_avoids_repeat():
    # a repeated guess marked "higher" with no other info must not be guessed again
    r = ok("binary_search_next", {"lo": 1, "hi": 3, "history": [{"guess": 2, "feedback": "higher"}]})
    assert r["next_guess"] == 3 and r["candidates"] == 1


# ---- bisect_predicate_points

def test_bisect_bracket_and_next():
    r = ok("bisect_predicate_points", {"points": [{"x": 1, "ok": False}, {"x": 9, "ok": True}, {"x": 3, "ok": False}]})
    assert r["bracket"] == [3, 9] and r["next_x"] == 6 and not r["done"]


def test_bisect_done():
    r = ok("bisect_predicate_points", {"points": [{"x": 4, "ok": False}, {"x": 5, "ok": True}]})
    assert r["done"] and r["threshold"] == 5 and r["next_x"] is None


def test_bisect_only_one_side():
    r = ok("bisect_predicate_points", {"points": [{"x": 4, "ok": False}], "hi": 10})
    assert 4 < r["next_x"] <= 10
    r = ok("bisect_predicate_points", {"points": [{"x": 4, "ok": False}]})
    assert r["next_x"] == 8                      # exponential search upward
    r = ok("bisect_predicate_points", {"points": [{"x": 8, "ok": True}], "lo": 0})
    assert 0 <= r["next_x"] < 8
    r = ok("bisect_predicate_points", {"points": [{"x": 10, "ok": False}], "hi": 10})
    assert r["done"] and r["status"] == "no_yes_in_range" and r["threshold"] is None
    r = ok("bisect_predicate_points", {"points": [{"x": 0, "ok": True}], "lo": 0})
    assert r["done"] and r["threshold"] == 0


def test_bisect_no_points():
    r = ok("bisect_predicate_points", {"points": [], "lo": 0, "hi": 100})
    assert r["next_x"] == 50
    assert "lo and hi" in bad("bisect_predicate_points", {"points": []})


def test_bisect_not_monotone():
    assert "not monotone" in bad("bisect_predicate_points", {"points": [{"x": 5, "ok": True}, {"x": 5, "ok": False}]})
    assert "not monotone" in bad("bisect_predicate_points", {"points": [{"x": 7, "ok": False}, {"x": 3, "ok": True}]})


def test_bisect_floats():
    r = ok("bisect_predicate_points", {"points": [{"x": 0.0, "ok": False}, {"x": 1.0, "ok": True}]})
    assert r["next_x"] == 0.5
    r = ok("bisect_predicate_points", {"points": [{"x": 0.0, "ok": False}, {"x": 1e-12, "ok": True}]})
    assert r["done"]


def test_bisect_converges_on_ints():
    for thr in (0, 1, 37, 99, 100):
        pts = []
        for _ in range(20):
            r = ok("bisect_predicate_points", {"points": pts, "lo": 0, "hi": 100})
            if r["done"]:
                break
            pts.append({"x": r["next_x"], "ok": r["next_x"] >= thr})
        assert r["done"] and r["threshold"] == thr, (thr, r)


# ---- dice_sum_distribution

def brute(dice):
    total = 1
    for f in dice:
        total *= f
    counts = {}
    for roll in itertools.product(*[range(1, f + 1) for f in dice]):
        counts[sum(roll)] = counts.get(sum(roll), 0) + 1
    return {s: Fraction(c, total) for s, c in counts.items()}


@pytest.mark.parametrize("dice", [[6], [6, 6], [4, 6, 8], [2, 2, 2, 2], [1, 6], [20, 3], [6, 6, 6]])
def test_dice_matches_brute_force(dice):
    r = ok("dice_sum_distribution", {"dice": dice, "target": 5})
    want = brute(dice)
    got = {d["sum"]: Fraction(d["p"]) for d in r["distribution"]}
    assert got == want
    assert Fraction(r["p_equal"]) == want.get(5, 0)
    assert Fraction(r["p_at_least"]) == sum((p for s, p in want.items() if s >= 5), Fraction(0))
    assert Fraction(r["p_at_most"]) == sum((p for s, p in want.items() if s <= 5), Fraction(0))
    assert Fraction(r["expected_value"]) == sum(s * p for s, p in want.items())


def test_dice_two_d6_strings():
    r = ok("dice_sum_distribution", {"dice": [6, 6], "target": 7})
    assert r["distribution"][0] == {"sum": 2, "p": "1/36", "decimal": round(1 / 36, 6)}
    assert r["p_equal"] == "1/6" and r["p_at_least"] == "7/12" and r["expected_value"] == "7"
    assert r["most_likely_sum"] == 7


def test_dice_target_out_of_range():
    r = ok("dice_sum_distribution", {"dice": [6], "target": 99})
    assert r["p_equal"] == "0" and r["p_at_least"] == "0" and r["p_at_most"] == "1"
    r = ok("dice_sum_distribution", {"dice": [6], "target": -3})
    assert r["p_at_least"] == "1"


def test_dice_large_is_summarised_and_small_result():
    r = catalog.call("dice_sum_distribution", {"dice": [100] * 30, "target": 1500})
    assert r["ok"], r
    assert "distribution_omitted" in r["result"] and "truncated" not in r["result"]
    assert 0 < Fraction(r["result"]["p_at_least"]) < 1


def test_dice_bad_args():
    assert bad("dice_sum_distribution", {"dice": []})
    assert bad("dice_sum_distribution", {"dice": [0]})
    assert bad("dice_sum_distribution", {"dice": [6] * 31})
    assert bad("dice_sum_distribution", {"dice": [6.5]})
    assert bad("dice_sum_distribution", {"dice": [6], "target": "7"})
