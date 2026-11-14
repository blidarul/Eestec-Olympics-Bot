"""P3 tools: combinatorics, count_hands, hypergeometric, binomial_tail, expected_value, best_option,
bayes_update, monte_carlo_estimate, abstain_threshold."""
import itertools
import json
import math
import time
from fractions import Fraction

import solvers  # noqa: F401  (registers the tools)
from solvers import catalog

NAMES = ["combinatorics", "count_hands", "hypergeometric", "binomial_tail", "expected_value", "best_option",
         "bayes_update", "abstain_threshold"]


def ok(name, args, **kw):
    r = catalog.call(name, args, **kw)
    assert r["ok"], r
    return r["result"]


def bad(name, args):
    r = catalog.call(name, args)
    assert r["ok"] is False, r
    return r["error"]


def test_registration_and_export():
    callable_names = {s.name for s in catalog.list_tools(model_callable=True)}
    assert set(NAMES) <= callable_names
    assert "monte_carlo_estimate" not in callable_names
    assert "monte_carlo_estimate" in {s.name for s in catalog.list_tools(model_callable=False)}
    exported = {t["function"]["name"] for t in catalog.openai_tools()}
    assert set(NAMES) <= exported and "monte_carlo_estimate" not in exported
    json.dumps(catalog.openai_tools(NAMES))


# ---- combinatorics

def test_combinatorics_values():
    assert ok("combinatorics", {"kind": "ncr", "n": 52, "k": 5})["value"] == 2598960
    assert ok("combinatorics", {"kind": "npr", "n": 5, "k": 2})["value"] == 20
    assert ok("combinatorics", {"kind": "factorial", "n": 10})["value"] == 3628800
    assert ok("combinatorics", {"kind": "multinomial", "parts": [2, 3, 1]})["value"] == 60
    assert ok("combinatorics", {"kind": "ncr", "n": 3, "k": 5})["value"] == 0
    assert ok("combinatorics", {"kind": "ncr", "n": 0, "k": 0})["value"] == 1


def test_combinatorics_huge_and_errors():
    r = ok("combinatorics", {"kind": "factorial", "n": 1000})
    assert isinstance(r["value"], str) and r["digits"] == 2568
    assert bad("combinatorics", {"kind": "ncr", "n": 5})
    assert bad("combinatorics", {"kind": "ncr", "k": 5})
    assert bad("combinatorics", {"kind": "multinomial"})
    assert bad("combinatorics", {"kind": "multinomial", "parts": [2000, 2000]})
    assert bad("combinatorics", {"kind": "ncr", "n": -1, "k": 0})
    assert bad("combinatorics", {"kind": "nope"})


# ---- count_hands

def test_count_hands_poker_two_aces():
    cats = [{"name": "ace", "count": 4, "min": 2, "max": 2}, {"name": "other", "count": 48, "min": 0}]
    r = ok("count_hands", {"categories": cats, "k": 5})
    assert r["ways"] == math.comb(4, 2) * math.comb(48, 3)
    assert Fraction(r["probability"]) == Fraction(math.comb(4, 2) * math.comb(48, 3), math.comb(52, 5))


def test_count_hands_matches_enumeration():
    cats = [{"count": 3, "min": 1}, {"count": 2, "max": 1}, {"count": 4}]
    deck = [0] * 3 + [1] * 2 + [2] * 4
    want = 0
    for hand in itertools.combinations(range(9), 4):
        a = sum(1 for i in hand if deck[i] == 0)
        b = sum(1 for i in hand if deck[i] == 1)
        want += a >= 1 and b <= 1
    r = ok("count_hands", {"categories": cats, "k": 4})
    assert r["ways"] == want and r["total_hands"] == math.comb(9, 4)


def test_count_hands_impossible_and_errors():
    r = ok("count_hands", {"categories": [{"count": 2, "min": 2}, {"count": 5}], "k": 1})
    assert r["ways"] == 0 and r["probability"] == "0"
    assert bad("count_hands", {"categories": [{"count": 2}], "k": 3})
    assert bad("count_hands", {"categories": [{"count": 2, "min": 3}], "k": 1})
    assert bad("count_hands", {"categories": [], "k": 1})


# ---- hypergeometric / binomial

def test_hypergeometric_matches_formula():
    r = ok("hypergeometric", {"population": 52, "successes": 4, "draws": 5, "x": 1})
    want = Fraction(math.comb(4, 1) * math.comb(48, 4), math.comb(52, 5))
    assert Fraction(r["p_exactly"]) == want
    pmf = [Fraction(math.comb(4, s) * math.comb(48, 5 - s), math.comb(52, 5)) for s in range(5)]
    assert Fraction(r["p_at_least"]) == sum(pmf[1:]) and Fraction(r["p_at_most"]) == sum(pmf[:2])
    assert abs(r["mean"] - 5 * 4 / 52) < 1e-4


def test_hypergeometric_edges():
    r = ok("hypergeometric", {"population": 10, "successes": 3, "draws": 10, "x": 3})
    assert r["p_exactly"] == "1"
    r = ok("hypergeometric", {"population": 10, "successes": 3, "draws": 4, "x": 5})
    assert r["p_exactly"] == "0" and r["p_at_least"] == "0" and r["p_at_most"] == "1"
    assert bad("hypergeometric", {"population": 5, "successes": 6, "draws": 1, "x": 0})
    assert bad("hypergeometric", {"population": 5, "successes": 1, "draws": 6, "x": 0})


def test_binomial_dice_bid():
    # at least 3 sixes among 12 unseen dice
    r = ok("binomial_tail", {"n": 12, "p": "1/6", "x": 3})
    p, q = Fraction(1, 6), Fraction(5, 6)
    want = 1 - sum(math.comb(12, s) * p ** s * q ** (12 - s) for s in range(3))
    assert Fraction(r["p_at_least"]) == want
    assert abs(r["p_at_least_decimal"] - float(want)) < 1e-5


def test_binomial_edges_and_p_forms():
    assert ok("binomial_tail", {"n": 0, "p": 0.5, "x": 0})["p_exactly"] == "1"
    assert ok("binomial_tail", {"n": 5, "p": 1, "x": 5})["p_exactly"] == "1"
    assert ok("binomial_tail", {"n": 5, "p": 0, "x": 1})["p_at_least"] == "0"
    a = ok("binomial_tail", {"n": 4, "p": 0.25, "x": 2})["p_exactly"]
    b = ok("binomial_tail", {"n": 4, "p": "1/4", "x": 2})["p_exactly"]
    assert a == b
    assert bad("binomial_tail", {"n": 4, "p": 1.5, "x": 1})
    assert bad("binomial_tail", {"n": 4, "p": "abc", "x": 1})
    assert bad("binomial_tail", {"n": 501, "p": 0.5, "x": 1})


# ---- expected value / best option

def test_expected_value():
    r = ok("expected_value", {"outcomes": [{"p": 0.5, "value": 10}, {"p": "1/2", "value": -4}]})
    assert r["expected_value"] == "3" and r["variance"] == 49 and r["std_dev"] == 7
    assert r["best_case"] == 10 and r["worst_case"] == -4


def test_expected_value_probability_checks():
    assert "sum" in bad("expected_value", {"outcomes": [{"p": 0.5, "value": 1}]})
    r = ok("expected_value", {"outcomes": [{"p": 0.2, "value": 1}, {"p": 0.2, "value": 5}], "normalize": True})
    assert r["expected_value"] == "3"
    assert bad("expected_value", {"outcomes": [{"p": 1, "value": "x"}]})
    assert bad("expected_value", {"outcomes": []})
    # three 1/3 given as decimals within tolerance
    assert ok("expected_value", {"outcomes": [{"p": 0.333333, "value": 3}, {"p": 0.333333, "value": 3}, {"p": 0.333334, "value": 3}]})


def test_best_option():
    r = ok("best_option", {"options": [
        {"name": "safe", "outcomes": [{"p": 1, "value": 3}]},
        {"name": "gamble", "outcomes": [{"p": "1/2", "value": 8}, {"p": "1/2", "value": 0}]},
        {"name": "bad", "outcomes": [{"p": 1, "value": -1}]}]})
    assert r["best"] == "gamble" and r["best_index"] == 1 and r["margin"] == 1 and r["tie"] is False
    assert [x["name"] for x in r["ranking"]] == ["gamble", "safe", "bad"]


def test_best_option_tie_single_and_defaults():
    r = ok("best_option", {"options": [{"outcomes": [{"p": 1, "value": 2}]}, {"outcomes": [{"p": 1, "value": 2}]}]})
    assert r["tie"] is True and r["best_index"] == 0 and r["best"] == "option 1"
    r = ok("best_option", {"options": [{"outcomes": [{"p": 1, "value": 2}]}]})
    assert r["margin"] is None and r["tie"] is False
    assert "sum" in bad("best_option", {"options": [{"name": "x", "outcomes": [{"p": 0.1, "value": 2}]}]})


# ---- bayes

def test_bayes_classic_disease_test():
    r = ok("bayes_update", {"hypotheses": [
        {"name": "sick", "prior": "1/100", "likelihood": "9/10"},
        {"name": "healthy", "prior": "99/100", "likelihood": "1/10"}]})
    post = {h["name"]: Fraction(h["posterior"]) for h in r["posterior"]}
    assert post["sick"] == Fraction(9, 108)
    assert sum(post.values()) == 1 and r["most_likely"] == "healthy"


def test_bayes_unnormalised_prior_and_impossible_evidence():
    r = ok("bayes_update", {"hypotheses": [{"prior": 1, "likelihood": 0.5}, {"prior": 1, "likelihood": 0.5}]})
    assert [h["posterior"] for h in r["posterior"]] == ["1/2", "1/2"]
    assert "probability 0" in bad("bayes_update", {"hypotheses": [{"prior": 0.5, "likelihood": 0}, {"prior": 0.5, "likelihood": 0}]})
    assert "distinct" in bad("bayes_update", {"hypotheses": [{"name": "a", "prior": 1, "likelihood": 1}, {"name": "a", "prior": 1, "likelihood": 1}]})
    assert bad("bayes_update", {"hypotheses": [{"prior": 1, "likelihood": 2}]})


# ---- abstain

def test_abstain_threshold_values():
    r = ok("abstain_threshold", {"reward_correct": 1, "penalty_wrong": 1, "reward_unknown": 0})
    assert r["threshold"] == "1/2"
    r = ok("abstain_threshold", {"reward_correct": 1, "penalty_wrong": 0, "reward_unknown": 0})
    assert r["policy"] == "always answer"
    r = ok("abstain_threshold", {"reward_correct": 2, "penalty_wrong": 3, "reward_unknown": 1, "confidence": "4/5"})
    assert r["threshold"] == "4/5" and r["decision"] == "answer"
    r = ok("abstain_threshold", {"reward_correct": 2, "penalty_wrong": 3, "reward_unknown": 1, "confidence": 0.79})
    assert r["decision"] == "unknown"


def test_abstain_never_answer_and_errors():
    r = ok("abstain_threshold", {"reward_correct": 1, "penalty_wrong": 0, "reward_unknown": 2, "confidence": 1})
    assert r["decision"] == "unknown" and "never" in r["policy"]
    assert bad("abstain_threshold", {"reward_correct": 0, "penalty_wrong": 0, "reward_unknown": 0})
    assert bad("abstain_threshold", {"reward_correct": 1, "penalty_wrong": -1, "reward_unknown": 0})
    assert bad("abstain_threshold", {"reward_correct": 1, "penalty_wrong": 1})


# ---- monte carlo (harness only)

def test_monte_carlo_estimate():
    r = ok("monte_carlo_estimate", {"sampler": lambda rng: rng.random() < 0.3, "max_samples": 20000, "seed": 5})
    assert r["n"] == 20000 and r["stopped_by"] == "samples" and abs(r["mean"] - 0.3) < 4 * r["stderr"] + 1e-9
    again = ok("monte_carlo_estimate", {"sampler": lambda rng: rng.random() < 0.3, "max_samples": 20000, "seed": 5})
    assert again["mean"] == r["mean"]


def test_monte_carlo_stops_at_deadline_and_survives_bad_sampler():
    t0 = time.monotonic()
    r = ok("monte_carlo_estimate", {"sampler": lambda rng: rng.random(), "max_samples": 10 ** 7},
           deadline=time.monotonic() + 0.3)
    assert r["stopped_by"] == "deadline" and r["n"] > 100 and time.monotonic() - t0 < 0.6
    assert bad("monte_carlo_estimate", {"sampler": lambda rng: 1 / 0})
    assert bad("monte_carlo_estimate", {"sampler": "print(1)"})
    r = ok("monte_carlo_estimate", {"sampler": lambda rng: 1.0, "max_samples": 1})
    assert r["n"] == 1 and r["stderr"] is None


def test_monte_carlo_not_reachable_from_json():
    # a model can only send JSON: a string is never executed, and the tool is not exported
    r = catalog.call("monte_carlo_estimate", json.dumps({"sampler": "__import__('os').system('echo x')"}))
    assert r["ok"] is False


# ---- #25: MDP value iteration (solvers/probability.py) ----
def test_mdp_gamblers_ruin_and_eu():
    from solvers.probability import value_iteration, calculate_expected_utility
    p = 0.4
    states = list(range(0, 6))
    actions = ["bet"]
    tr, rw = {}, {}
    for s in range(1, 5):
        tr[(s, "bet")] = [(p, s + 1), (1 - p, s - 1)]
        rw[(s, "bet")] = 0.0
    rw[(4, "bet")] = p  # reward on reaching 5 (gamma=1 -> win prob)
    V, pol = value_iteration(states, actions, tr, rw, gamma=1.0, max_iters=2000, tol=1e-12)
    q = 1 - p; r = q / p
    exact = (1 - r ** 2) / (1 - r ** 5)  # win prob from 2 to 5
    assert abs(V[2] - exact) < 1e-6 and pol[0] is None and V[0] == 0.0
    # choice: safe vs risky
    V, pol = value_iteration([0, 1], ["safe", "risk"],
                             {(0, "safe"): [(1.0, 1)], (0, "risk"): [(0.5, 1), (0.5, 1)]},
                             {(0, "safe"): 3.0, (0, "risk"): 1.0}, gamma=0.9)
    assert pol[0] == "safe" and abs(V[0] - 3.0) < 1e-9
    assert value_iteration([], [], {}, {}) == ({}, {})
    assert calculate_expected_utility(["a", "b"], {"a": [(0.5, 10), (0.5, 0)], "b": [(1.0, 4)]}) == ("a", 5.0)
    assert calculate_expected_utility([], {}) == (None, 0.0)
    assert calculate_expected_utility(["a"], {"a": []}) == (None, 0.0)
