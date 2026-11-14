"""strategies/guessing/deduce: model verification, prepare(), decide() on a simulated guessing game (tests only)."""
import random
import time

import pytest

from core import registry
from solvers.deduction import best_split
from strategies.base import TurnState
from strategies.guessing import deduce
from strategies.guessing.deduce import model as fm
from strategies.guessing.deduce import prepare as prep_mod
from tests.alex.games import GUESS_MODEL_CODE, guess_obs, guess_rules


def variant(lo=1, hi=100, cap=12, history=((30, "higher"), (60, "lower"))):
    return {"label": f"{lo}-{hi}", "rules": guess_rules(lo, hi, cap),
            "sample_turn": {"type": "turn", "turn": 5, "observation": guess_obs(list(history), lo, hi, cap),
                            "legal_actions": None, "seconds": 20, "chat": []}}


def test_model_verifies():
    ok, why, stats = fm.verify_model(GUESS_MODEL_CODE, variant())
    assert ok, why
    assert stats["max_guesses_used"] <= 12 and stats["avg_guesses"] < 8 and stats["space"] == 100


@pytest.mark.parametrize("patch,reason", [
    ('return "correct" if guess == secret else ("higher" if secret > guess else "lower")',
     'return "correct" if guess == secret else ("lower" if secret > guess else "higher")'),   # reversed feedback
    ('return "guess %d" % guess', 'return "pick %d\\nplease" % guess'),                          # bad action format
    ('return range(lo, hi + 1)', 'return range(lo, lo + 1)'),                                    # one candidate only
    ('out.append((int(m.group(1)), m.group(2)))', 'pass'),                                       # history never found
])
def test_model_rejected(patch, reason):
    bad = GUESS_MODEL_CODE.replace(patch, reason)
    assert bad != GUESS_MODEL_CODE
    ok, why, _ = fm.verify_model(bad, variant())
    assert not ok, why


def test_model_sandbox_blocks_io_and_isolated_timeout():
    with pytest.raises(Exception):
        fm.Model("import os\n" + GUESS_MODEL_CODE)
    with pytest.raises(Exception):
        fm.Model(GUESS_MODEL_CODE + "\nopen('x')\n").feedback  # open() is not a builtin there; fails when called
        exec  # noqa
    loop = GUESS_MODEL_CODE.replace('return "correct" if guess == secret', "while True: pass\n    return 'x' if guess == secret")
    t0 = time.monotonic()
    ok, why, _ = fm.verify_isolated(loop, variant(), timeout=4)
    assert not ok and time.monotonic() - t0 < 12


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def available(self):
        return True

    def over_budget(self):
        return False

    def ask(self, system, user, **kw):
        self.calls.append(kw)
        return self.replies.pop(0) if self.replies else None


def test_prepare_verifies_saves_and_retries(tmp_path):
    v = variant()
    v["memory_dir"] = str(tmp_path / "g" / "h")
    bad = "```python\ndef nothing():\n    pass\n```"
    good = f"Here you go:\n```python{GUESS_MODEL_CODE}```"
    llm = FakeLLM([bad, good])
    res = prep_mod.prepare(v["rules"], v, llm, time.monotonic() + 200)
    assert res["verified"] and res["attempt"] == 2 and "code" in res
    assert (tmp_path / "g" / "h" / "feedback_model.py").read_text(encoding="utf-8").strip() == GUESS_MODEL_CODE.strip()
    assert llm.calls and all(c["prep"] and c["budget"] >= 1024 and c["max_tokens"] >= c["budget"] + 1500 for c in llm.calls)  # 7.3
    assert prep_mod.prepare(v["rules"], v, FakeLLM([bad, bad]), time.monotonic() + 200)["verified"] is False
    assert prep_mod.prepare(v["rules"], v, None, time.monotonic() + 200)["verified"] is False
    assert prep_mod.prepare(v["rules"], {"rules": "x"}, llm, time.monotonic() + 200)["verified"] is False  # no sample_turn


def test_prepare_accepts_json_reply(tmp_path):
    import json
    v = variant()
    res = prep_mod.prepare(v["rules"], v, FakeLLM([json.dumps({"a": "", "c": "x", "code": GUESS_MODEL_CODE})]), time.monotonic() + 200)
    assert res["verified"]


def artifacts(verified=True, family="guessing"):
    res = {"verified": verified, "code": GUESS_MODEL_CODE, "sha": "x"} if verified else {"verified": False, "reason": "no"}
    return {"family": family, "prepared": {"deduce": res}, "forbidden_terms": []}


def play(secret, lo=1, hi=100, cap=12, art=None, sent_net=True, strategy=None):
    """Play one game of the arena's guess game against `secret` (the hidden opponent number); returns the guesses."""
    strategy = strategy or deduce.STRATEGY
    art = art or artifacts()
    rules = guess_rules(lo, hi, cap)
    hist, mine = [], []
    for turn in range(1, cap + 1):
        st = TurnState("guess_number", rules, {"label": "x"}, 0, guess_obs(hist, lo, hi, cap), None, turn, None, [], art,
                       time.monotonic() + 8, None, my_actions=list(mine), match_id="m", game_index=1)
        d = strategy.decide(st)
        assert d.chat and len(d.chat) <= 200 and "17" not in d.chat.replace(d.action, "")  # our own secret (17) never in chat
        assert d.action not in mine, "repeated guess"
        mine.append(d.action)
        n = int(d.action.split()[1])
        if n == secret:
            return mine
        hist.append((n, "higher" if secret > n else "lower"))
    return mine


def test_deduce_never_repeats_and_solves_within_limit():
    rng = random.Random(5)
    lens = []
    for secret in [1, 100, 46, 50] + [rng.randint(1, 100) for _ in range(30)]:
        g = play(secret)
        assert g[-1] == f"guess {secret}" and len(set(g)) == len(g) and len(g) <= 7
        lens.append(len(g))
    assert sum(lens) / len(lens) < 6.5


def test_deduce_1000_range():
    for secret in (1, 777, 1000):
        g = play(secret, 1, 1000, 15, art=artifacts())
        assert g[-1] == f"guess {secret}" and len(g) <= 10


def test_deduce_info_and_candidates_left():
    st = TurnState("guess_number", guess_rules(), {"label": "x"}, 0, guess_obs([(50, "higher")]), None, 2, None, ["hi"],
                   artifacts(), time.monotonic() + 8, None, match_id="m2", game_index=1)
    d = deduce.STRATEGY.decide(st)
    assert d.info["tool"] == "deduction" and d.info["candidates_left"] == 50 and d.source == "strategy"
    assert int(d.action.split()[1]) in (75, 76)     # median of 51..100


def test_contradicting_feedback_falls_back_to_generic():
    bad = [(50, "higher"), (60, "lower"), (55, "higher"), (56, "higher"), (57, "higher"), (58, "higher"), (59, "higher")]
    # 51..59 all "higher" is inconsistent with "60 lower" -> empty candidate set
    st = TurnState("guess_number", guess_rules(), {"label": "x"}, 0, guess_obs(bad), None, 8, None, [], artifacts(),
                   time.monotonic() + 8, None, my_actions=[f"guess {n}" for n, _ in bad], match_id="m3", game_index=1)
    d = deduce.STRATEGY.decide(st)
    assert "core/generic" in d.info["reason"] and d.source in ("fallback", "model")
    assert isinstance(d.action, str) and d.action not in st.my_actions


def test_matches_requires_family_and_verified_model():
    assert deduce.STRATEGY.matches("r", artifacts()) > 0.5
    assert deduce.STRATEGY.matches("r", artifacts(verified=False)) == 0.0
    assert deduce.STRATEGY.matches("r", artifacts(family="grid_board")) == 0.0


def test_chat_lines_survive_the_output_filters():
    # chat/ rewrites lines with digits or strategy words into neutral fillers: ours must stay as written (move and chat from one decision)
    import chat
    for t in deduce.WIDE + deduce.MID + deduce.NEAR + deduce.LAST:
        assert chat.filter_out(t, []) == t
