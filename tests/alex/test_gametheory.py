"""P4 tools: matrix_nash, sample_action, best_response, nim_analysis, minimax_small, csp_backtrack."""
import functools
import itertools
import json
import random
import time
from fractions import Fraction

import solvers  # noqa: F401  (registers the tools)
from solvers import catalog

MODEL = ["matrix_nash", "sample_action", "best_response", "nim_analysis"]
HARNESS = ["minimax_small", "csp_backtrack"]


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
    exported = {t["function"]["name"] for t in catalog.openai_tools()}
    assert set(MODEL) <= callable_names and set(MODEL) <= exported
    assert not set(HARNESS) & callable_names and not set(HARNESS) & exported
    json.dumps(catalog.openai_tools(MODEL))


# ---- matrix_nash

def probs(r, key="row_strategy"):
    return {e["index"]: Fraction(e["p"]) for e in r[key]}


def test_rock_paper_scissors():
    m = [[0, -1, 1], [1, 0, -1], [-1, 1, 0]]
    r = ok("matrix_nash", {"matrix": m})
    assert r["value"] == "0" and probs(r) == {0: Fraction(1, 3), 1: Fraction(1, 3), 2: Fraction(1, 3)}
    assert probs(r, "col_strategy") == probs(r) and r["pure"] is False


def test_matching_pennies_and_2x2_formula():
    r = ok("matrix_nash", {"matrix": [[1, -1], [-1, 1]], "row_labels": ["heads", "tails"]})
    assert r["value"] == "0" and r["row_strategy"][0]["label"] == "heads" and r["row_strategy"][0]["p"] == "1/2"
    r = ok("matrix_nash", {"matrix": [[3, -1], [-2, 1]]})
    assert r["value"] == "1/7" and probs(r) == {0: Fraction(3, 7), 1: Fraction(4, 7)}


def test_saddle_point_dominance_and_fractions():
    r = ok("matrix_nash", {"matrix": [[4, 2, 3], [1, 0, 5], [3, 2, 2]]})
    assert r["value"] == "2" and r["pure"] is True
    r = ok("matrix_nash", {"matrix": [["1/2", "1/3"]]})
    assert r["value"] == "1/3" and probs(r) == {0: Fraction(1)}
    r = ok("matrix_nash", {"matrix": [[5]]})
    assert r["value"] == "5" and r["pure"]
    r = ok("matrix_nash", {"matrix": [[7, 7], [7, 7]]})          # duplicates
    assert r["value"] == "7"


def test_matrix_nash_random_matrices_are_exactly_optimal():
    rng = random.Random(1)
    for _ in range(60):
        m, n = rng.randint(1, 6), rng.randint(1, 6)
        A = [[rng.randint(-5, 9) for _ in range(n)] for _ in range(m)]
        r = ok("matrix_nash", {"matrix": A})          # the tool also self-checks, we recheck independently
        v = Fraction(r["value"])
        x = [Fraction(0)] * m
        y = [Fraction(0)] * n
        for e in r["row_strategy"]:
            x[e["index"]] = Fraction(e["p"])
        for e in r["col_strategy"]:
            y[e["index"]] = Fraction(e["p"])
        assert sum(x) == 1 and sum(y) == 1
        assert min(sum(x[i] * A[i][j] for i in range(m)) for j in range(n)) == v
        assert max(sum(y[j] * A[i][j] for j in range(n)) for i in range(m)) == v
        maximin = max(min(row) for row in A)
        minimax = min(max(A[i][j] for i in range(m)) for j in range(n))
        assert maximin <= v <= minimax


def test_matrix_nash_errors():
    assert bad("matrix_nash", {"matrix": [[1, 2], [3]]})
    assert bad("matrix_nash", {"matrix": [["a", 1]]})
    assert bad("matrix_nash", {"matrix": [[1, 2]], "row_labels": ["x", "y"]})
    assert bad("matrix_nash", {"matrix": []})
    assert bad("matrix_nash", {"matrix": [[1] * 31]})


def test_matrix_nash_30x30_within_budget():
    rng = random.Random(2)
    A = [[rng.randint(-9, 9) for _ in range(30)] for _ in range(30)]
    t0 = time.monotonic()
    r = catalog.call("matrix_nash", {"matrix": A}, deadline=time.monotonic() + 3)
    assert r["ok"] or "deadline" in r["error"] or "timeout" in r["error"]
    assert time.monotonic() - t0 < 3.5


# ---- sample_action

def test_sample_action_reproducible_and_distribution():
    a = ok("sample_action", {"probs": [1, 1, 1], "seed": 4})
    assert a == ok("sample_action", {"probs": [1, 1, 1], "seed": 4})
    counts = [0, 0, 0]
    for s in range(3000):
        counts[ok("sample_action", {"probs": ["1/2", "1/4", "1/4"], "seed": s})["index"]] += 1
    assert abs(counts[0] / 3000 - 0.5) < 0.05 and abs(counts[1] / 3000 - 0.25) < 0.05


def test_sample_action_zero_weights_and_errors():
    for s in range(50):
        assert ok("sample_action", {"probs": [0, 3, 0], "seed": s, "labels": ["a", "b", "c"]})["label"] == "b"
    assert bad("sample_action", {"probs": [0, 0]})
    assert bad("sample_action", {"probs": [-1, 2]})
    assert bad("sample_action", {"probs": [1, 2], "labels": ["a"]})


# ---- best_response

def test_best_response():
    rps = [[0, -1, 1], [1, 0, -1], [-1, 1, 0]]
    r = ok("best_response", {"matrix": rps, "opponent_freq": [6, 2, 2], "row_labels": ["rock", "paper", "scissors"]})
    assert r["label"] == "paper" and Fraction(r["ev"]) == Fraction(4, 10)
    r = ok("best_response", {"matrix": rps, "opponent_freq": [1, 1, 1]})
    assert r["ties"] == [0, 1, 2] and r["best_action"] == 0
    assert bad("best_response", {"matrix": rps, "opponent_freq": [1, 1]})
    assert bad("best_response", {"matrix": rps, "opponent_freq": [0, 0, 0]})
    assert bad("best_response", {"matrix": rps, "opponent_freq": [-1, 1, 1]})


# ---- nim_analysis

def brute_nim(heaps, removals, misere):
    @functools.lru_cache(maxsize=None)
    def win(state):
        if not state:
            return misere
        for idx, h in enumerate(state):
            for s in (range(1, h + 1) if removals is None else [s for s in removals if s <= h]):
                new = list(state)
                new[idx] -= s
                if not win(tuple(sorted(x for x in new if x))):
                    return True
        return False
    return win(tuple(sorted(h for h in heaps if h)))


def test_nim_classic():
    r = ok("nim_analysis", {"heaps": [3, 4, 5]})
    assert r["nim_sum"] == 2 and r["first_player_wins"] and r["winning_move"] == {"heap": 0, "remove": 2, "new_size": 1}
    r = ok("nim_analysis", {"heaps": [1, 2, 3]})
    assert r["nim_sum"] == 0 and r["first_player_wins"] is False and r["winning_move"] is None


def test_subtraction_game_grundy():
    r = ok("nim_analysis", {"heaps": [10], "removals": [1, 2, 3]})
    assert r["grundy"] == [2] and r["first_player_wins"] and r["winning_move"]["new_size"] == 8
    r = ok("nim_analysis", {"heaps": [8], "removals": [1, 2, 3]})
    assert r["grundy"] == [0] and r["first_player_wins"] is False


def test_misere_nim():
    r = ok("nim_analysis", {"heaps": [1, 1, 1], "misere": True})
    assert r["first_player_wins"] is False
    r = ok("nim_analysis", {"heaps": [3, 1], "misere": True})
    assert r["first_player_wins"] and r["winning_move"] == {"heap": 0, "remove": 3, "new_size": 0}
    assert ok("nim_analysis", {"heaps": [], "misere": True})["first_player_wins"] is True
    assert ok("nim_analysis", {"heaps": [0, 0]})["first_player_wins"] is False


def test_nim_matches_brute_force():
    rng = random.Random(9)
    sets = [None, [1], [1, 2], [2, 3], [1, 3, 4]]
    for _ in range(80):
        heaps = [rng.randint(0, 6) for _ in range(rng.randint(0, 4))]
        rem = rng.choice(sets)
        mis = rng.random() < 0.5
        r = ok("nim_analysis", {"heaps": heaps, "removals": rem or "any", "misere": mis})
        assert r["first_player_wins"] == brute_nim(heaps, rem, mis), (heaps, rem, mis)
        for mv in r["winning_moves"]:       # every reported move really leads to a lost position
            new = list(heaps)
            new[mv["heap"]] -= mv["remove"]
            assert mv["new_size"] == new[mv["heap"]] >= 0
            assert not brute_nim(new, rem, mis)


def test_nim_errors_and_limits():
    assert bad("nim_analysis", {"heaps": [1] * 13})
    assert bad("nim_analysis", {"heaps": [5], "removals": []})
    assert bad("nim_analysis", {"heaps": [5], "removals": [0]})
    assert bad("nim_analysis", {"heaps": [5], "removals": "some"})
    assert bad("nim_analysis", {"heaps": [30, 31], "removals": [1, 2], "misere": True})
    r = ok("nim_analysis", {"heaps": [1000] * 12})        # big normal-play position stays fast
    assert r["nim_sum"] == 0 and r["winning_move"] is None


# ---- minimax_small

def _nim_game(heaps, take=(1, 2, 3)):
    moves = lambda s: [(i, t) for i, h in enumerate(s) for t in take if t <= h]
    apply = lambda s, m: tuple(sorted(h - (m[1] if i == m[0] else 0) for i, h in enumerate(s)))
    terminal = lambda s: sum(s) == 0
    value = lambda s: -1                    # player to move at the end has no item left to take: lost
    return {"state": heaps, "moves": moves, "apply": apply, "terminal": terminal, "value": value}


def test_minimax_solves_small_nim():
    r = ok("minimax_small", _nim_game((7,)))
    assert r["complete"] and r["value"] == 1 and r["best_move"] == [0, 3]   # JSON round trip: tuples come back as lists
    r = ok("minimax_small", _nim_game((8,)))
    assert r["value"] == -1
    r = ok("minimax_small", _nim_game((3, 4, 5), take=(1, 2, 3, 4, 5)))
    assert r["value"] == 1


def test_minimax_terminal_depth_and_unhashable():
    g = _nim_game((0,))
    assert ok("minimax_small", g)["best_move"] is None
    g = _nim_game((20,))
    r = ok("minimax_small", dict(g, max_depth=2, value=lambda s: 0))
    assert r["value"] == 0 and r["complete"]
    # unhashable states still work (no memoisation)
    r = ok("minimax_small", {"state": [2], "moves": lambda s: [1] if s[0] else [], "apply": lambda s, m: [s[0] - m],
                             "terminal": lambda s: s[0] == 0, "value": lambda s: -1})
    assert r["value"] == -1   # two single steps: the mover loses


def test_minimax_deadline_returns_partial_or_error():
    g = _nim_game((60, 60, 60, 60), take=(1, 2, 3))
    t0 = time.monotonic()
    r = catalog.call("minimax_small", g, deadline=time.monotonic() + 0.4)
    assert time.monotonic() - t0 < 0.7
    assert (not r["ok"]) or r["result"]["complete"] is False
    assert bad("minimax_small", dict(_nim_game((3,)), moves="not callable"))


# ---- csp_backtrack

def test_csp_n_queens():
    n = 6
    cons = [{"vars": ["q%d" % i, "q%d" % j], "check": (lambda d: lambda a, b: abs(a - b) != d)(j - i)}
            for i in range(n) for j in range(i + 1, n)]
    r = ok("csp_backtrack", {"variables": {"q%d" % i: list(range(n)) for i in range(n)}, "constraints": cons,
                             "all_different": [["q%d" % i for i in range(n)]], "mode": "count"})
    assert r["count"] == 4 and r["complete"] and "solutions" not in r


def test_csp_solutions_cap_and_unsat():
    doms = {"a": [1, 2, 3], "b": [1, 2, 3]}
    r = ok("csp_backtrack", {"variables": doms, "constraints": [{"vars": ["a", "b"], "check": lambda a, b: a < b}]})
    assert r["count"] == 3 and {(s["a"], s["b"]) for s in r["solutions"]} == {(1, 2), (1, 3), (2, 3)}
    r = ok("csp_backtrack", {"variables": doms, "max_solutions": 2})
    assert len(r["solutions"]) == 2 and r["stopped_by"] == "cap" and r["complete"] is False
    r = ok("csp_backtrack", {"variables": doms, "constraints": [{"vars": ["a"], "check": lambda a: a > 5}]})
    assert r["count"] == 0 and r["complete"]


def test_csp_unary_deadline_and_errors():
    r = ok("csp_backtrack", {"variables": {"x": [1, 2, 3]}, "constraints": [{"vars": ["x"], "check": lambda x: x % 2 == 1}]})
    assert [s["x"] for s in r["solutions"]] == [1, 3]
    big = {"v%d" % i: list(range(10)) for i in range(12)}
    t0 = time.monotonic()
    r = catalog.call("csp_backtrack", {"variables": big, "mode": "count"}, deadline=time.monotonic() + 0.3)
    assert time.monotonic() - t0 < 0.7 and r["ok"] and r["result"]["complete"] is False and r["result"]["stopped_by"] == "deadline"
    assert bad("csp_backtrack", {"variables": {}})
    assert bad("csp_backtrack", {"variables": {"a": [1]}, "constraints": [{"vars": ["zz"], "check": lambda z: True}]})
    assert bad("csp_backtrack", {"variables": {"a": [1]}, "constraints": [{"vars": ["a"], "check": "a>0"}]})
    assert bad("csp_backtrack", {"variables": {"a": [1]}, "constraints": [{"vars": ["a"], "check": lambda a: 1 / 0}]})
