import io
import contextlib

from solvers.precompute import Facts
from solvers.select import select_tools
from solvers import catalog

CALLABLE = {s.name for s in catalog.list_tools(model_callable=True)}


def sel(art, obs="", rules="", facts=None, limit=6):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        out = select_tools(art, obs, rules, facts or Facts(), limit)
    return out, err.getvalue()


def test_every_family_short_valid_list():
    for fam in ("guessing", "think_ahead", "truth", "deduction", "bluff", "generic", "zzz"):
        out, _ = sel({"family": fam})
        assert 0 < len(out) <= 6 and len(set(out)) == len(out) and set(out) <= CALLABLE


def test_family_tools_present():
    assert "binary_search_next" in sel({"family": "guessing"})[0]
    out = sel({"family": "think_ahead"})[0]
    assert any(n.startswith("grid_") or n == "board_lines" for n in out)
    assert "abstain_threshold" in sel({"family": "truth"})[0]


def test_unknown_family_general_only():
    out, _ = sel({"family": "zzz"})
    for n in out:
        assert "any" in next(s.families for s in catalog.list_tools() if s.name == n)


def test_never_non_callable():
    out, _ = sel({"family": "think_ahead"})
    assert "minimax_small" not in out and "monte_carlo_estimate" not in sel({})[0]


def test_given_facts_dropped_partial_kept():
    f = Facts(used=["dice_sum_distribution", "board_lines"])
    out, _ = sel({"family": "think_ahead"}, "roll the dice", "dice game", f)
    assert "dice_sum_distribution" not in out
    assert out[0] == "board_lines"


def test_hints_and_limit():
    out, _ = sel({}, "", "two dice are rolled; payoff matrix", limit=3)
    assert len(out) == 3 and "matrix_nash" in out or "dice_sum_distribution" in out
    assert sel({}, limit=0)[0] == []


def test_deterministic_and_logged():
    a, e = sel({"family": "guessing"})
    b, _ = sel({"family": "guessing"})
    assert a == b and all(n in e for n in a)


def test_garbage_never_raises():
    for art, obs, rules, facts in ((None, None, None, None), (5, 5, 5, object()), ({"family": 3}, b"x", [], 1)):
        out = select_tools(art, obs, rules, facts)
        assert isinstance(out, list)
