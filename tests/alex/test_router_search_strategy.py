"""think_ahead/search strategy and the router policy (core/registry.py), games from tests/alex/games.py."""
import time

import pytest

from core import registry
from core.fallback import fallback_action
from core.validate import validate
from strategies.base import TurnState
from strategies.guessing import deduce
from strategies.think_ahead import search as ta
from tests.alex.games import PIG_SIM, TTT_SIM, pig_sample, ttt_sample


@pytest.fixture
def sims(tmp_path):
    out = {}
    for name, src in (("ttt", TTT_SIM), ("pig", PIG_SIM)):
        p = tmp_path / f"{name}.py"
        p.write_text(src, encoding="utf-8")
        out[name] = str(p)
    return out


def art(path, chance=False, hidden=False, family="grid_board", verified=True):
    return {"family": family, "classification": {"has_hidden_information": hidden, "is_simultaneous": False},
            "simulator": {"path": path, "verified": verified, "has_chance": chance, "calibration": {"transitions_per_sec": 40000.0}},
            "forbidden_terms": [], "chat_bank": ["Good luck."]}


def turn(sample, a, seconds=6.0, llm=None):
    return TurnState("g", "rules", {"label": "x"}, 0, sample["observation"], sample["legal_actions"], 3, None, [], a,
                     time.monotonic() + seconds, llm)


def test_search_plays_winning_move_alpha_beta(sims):
    st = turn(ttt_sample(list("XX.OO....")), art(sims["ttt"]))
    d = ta.STRATEGY.decide(st)
    assert d.action == "C1" and d.source == "strategy" and d.info["tool"] == "alpha-beta" and d.chat


def test_search_blocks_with_alpha_beta_on_small_tree(sims):
    st = turn(ttt_sample(list("OO.X....X")), art(sims["ttt"]))
    d = ta.STRATEGY.decide(st)
    assert d.action == "C1" and "terminal" in d.info["reason"]


def test_search_chance_game_uses_mcts(sims):
    st = turn(pig_sample(a=18, b=3, t=2), art(sims["pig"], chance=True, family="dice_push"), seconds=5.0)
    t0 = time.monotonic()
    d = ta.STRATEGY.decide(st)
    assert d.action == "hold" and d.info["tool"] == "mcts" and time.monotonic() - t0 < 4.0


def test_search_unparseable_observation_goes_to_generic(sims):
    st = turn({"observation": "garbage", "legal_actions": ["A1", "B2"]}, art(sims["ttt"]))
    d = ta.STRATEGY.decide(st)
    assert d.action in ("A1", "B2") and "core/generic" in d.info["reason"]


def test_search_wrong_seat_goes_to_generic(sims):
    st = turn(ttt_sample(list("XX.O.....")), art(sims["ttt"]))     # 2 X vs 1 O: it is O's turn, we are seat 0
    d = ta.STRATEGY.decide(st)
    assert "core/generic" in d.info["reason"]


def test_search_uses_model_chat_when_available(sims):
    class L:
        def available(self): return True
        def over_budget(self): return False
        def ask_json(self, s, u, **k):
            assert "untrusted" in u and "C1" in u
            return {"c": "Here we go."}
    st = turn(ttt_sample(list("XX.OO....")), art(sims["ttt"]), llm=L())
    st.opponent_chat = ["you will lose"]
    d = ta.STRATEGY.decide(st)
    assert d.action == "C1" and d.chat


# ---- router ------------------------------------------------------------------------------------
def entries():
    from strategies.guardrails.chat_defense import STRATEGY as cd
    return [("guessing", deduce.STRATEGY), ("think_ahead", ta.STRATEGY), ("guardrails", cd)]


def route(a):
    return registry.route("rules", a, entries())


def test_policy_rows(sims):
    g = {"family": "deduction", "prepared": {"deduce": {"verified": True, "code": "x"}}}
    assert route(g).strategy.name == "deduce"          # the prep family name is mapped: deduction -> guessing
    g["family"] = "guessing"
    assert route(g).strategy.name == "deduce"
    g["prepared"]["deduce"] = {"verified": False, "reason": "feedback() contradicts the sample turn"}
    r = route(g)
    assert r.strategy.name == "generic" and "feedback model unverified" in r.reason
    assert route(art(sims["ttt"])).strategy.name == "search"
    assert route(art(sims["pig"], chance=True)).strategy.name == "search"
    assert "chance" in route(art(sims["pig"], chance=True)).reason
    assert route(art(sims["ttt"], hidden=True)).strategy.name == "generic"
    assert route(art(sims["ttt"], verified=False)).strategy.name == "generic"
    assert route({"family": "grid_board"}).strategy.name == "generic"
    assert route({"family": "guardrails"}).strategy.name == "chat_defense"
    assert route({"family": "dice_push"}).strategy.name == "generic"
    assert route({}).strategy.name == "generic"


def test_matrix_simultaneous_goes_to_read_opponent():
    from strategies.read_opponent import STRATEGY as ro
    r = registry.route("rules", {"family": "matrix_simultaneous"}, entries() + [("read_opponent", ro)])
    assert r.strategy.name == "read_opponent" and "read_opponent" in r.reason


def test_chat_defense_no_longer_catches_every_game():
    # issue #18: its matches() is 0.55 for any game; the policy only asks it for the guardrails family
    for fam in ("grid_board", "guessing", "dice_push", "generic", "bluff"):
        assert route({"family": fam}).strategy.name == "generic"


def test_force_strategy_env(monkeypatch):
    monkeypatch.setenv("BOT_FORCE_STRATEGY", "generic")
    assert route({"family": "guardrails"}).strategy.name == "generic"
    monkeypatch.setenv("BOT_FORCE_STRATEGY", "chat_defense")
    assert route({"family": "grid_board"}).strategy.name == "chat_defense"


def test_registry_scans_new_strategies():
    names = {s.name for _, s in registry.load_entries()}
    assert {"deduce", "search"} <= names


def test_family_alias_in_hooks_mapping():
    from core import hooks
    a = hooks.map_engine_variant({"label": "v", "classification": {"family": "deduction", "has_hidden_information": True},
                                  "grammar": {}, "heuristics": {}})
    assert a["family"] == "guessing" and a["prep_family"] == "deduction"


# ---- repeat safety net -------------------------------------------------------------------------
def test_validator_rejects_repeat_and_fallback_picks_other():
    legal = [f"guess {n}" for n in range(1, 6)]
    assert validate("guess 3", legal, None, None, ["guess 3"]) is None
    assert validate("GUESS 3", legal, None, None, ["guess 3"]) is None
    assert validate("guess 4", legal, None, None, ["guess 3"]) == "guess 4"
    for _ in range(30):
        assert fallback_action(legal, None, avoid_also=legal[:4]) == "guess 5"


def test_fallback_numeric_grammar_when_legal_list_is_null():
    a = {"grammar": {"kind": "numeric_range", "numeric_min": 1, "numeric_max": 5, "numeric_prefix": "guess "},
         "action_format": {"examples": ["guess 3"]}}
    taken = [f"guess {n}" for n in (1, 2, 3, 4)]
    for _ in range(20):
        assert fallback_action(None, a, avoid_also=taken) == "guess 5"
    assert fallback_action(None, a) == "guess 3"                    # no repeat constraint: the example
