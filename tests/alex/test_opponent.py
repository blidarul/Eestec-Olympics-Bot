import json
import random
import time

from solvers import catalog
from solvers import opponent as op
from solvers.precompute import precompute
from solvers.select import select_tools

RPS = ["rock", "paper", "scissors"]
BEATS = {"rock": ["scissors"], "paper": ["rock"], "scissors": ["paper"]}


def dl(s=3):
    return time.monotonic() + s


def pred(opp, mine, **kw):
    args = {"actions": RPS, "beats": BEATS, "opponent_history": opp, "my_history": mine}
    args.update(kw)
    r = catalog.call("opponent_predictor", args, dl())
    assert r["ok"], r
    return r["result"]


def play(opp_fn, rounds=60, seed=1):
    rng = random.Random(seed)
    opp, mine, score = [], [], 0
    u = op._utility(RPS, None, BEATS)
    for t in range(rounds):
        r = pred(opp, mine, seed=seed)
        a = r["action"]
        o = opp_fn(t, mine, rng)
        score += u(a, o)
        opp.append(o)
        mine.append(a)
    return score


def test_beats_constant_opponent():
    assert play(lambda t, m, r: "rock") > 50


def test_beats_cycling_opponent():
    assert play(lambda t, m, r: RPS[t % 3]) > 40


def test_beats_reactive_opponent():
    # plays what would have beaten our previous move
    inv = {"rock": "paper", "paper": "scissors", "scissors": "rock"}
    assert play(lambda t, m, r: inv[m[-1]] if m else "rock") > 35


def test_random_opponent_not_exploited_and_uses_mix():
    r = pred([random.Random(3).choice(RPS) for _ in range(40)], [random.Random(4).choice(RPS) for _ in range(40)])
    assert r["action"] in RPS and abs(sum(r["probs"].values()) - 1) < 0.01


def test_few_rounds_gives_equilibrium_mix():
    r = pred(["rock"], ["paper"])
    assert r["predictor"] == "equilibrium_mix" and r["confidence"] == 0.0
    assert all(abs(p - 1 / 3) < 0.01 for p in r["probs"].values())


def test_payoff_matrix_and_bad_input():
    mat = [[0, -1, 1], [1, 0, -1], [-1, 1, 0]]
    r = catalog.call("opponent_predictor", {"actions": RPS, "payoff": mat, "opponent_history": ["rock"] * 8,
                                            "my_history": ["rock"] * 8}, dl())
    assert r["ok"] and r["result"]["action"] == "paper"
    for bad in ({"actions": RPS, "opponent_history": ["rock"]},
                {"actions": RPS, "beats": BEATS, "opponent_history": ["lizard"]},
                {"actions": ["a"], "beats": BEATS, "opponent_history": []}):
        assert catalog.call("opponent_predictor", bad, dl())["ok"] is False


def test_reciprocity():
    def pol(opp, mine=None, **kw):
        r = catalog.call("reciprocity_policy", dict({"opponent_history": opp, "my_history": mine or []}, **kw), dl())
        assert r["ok"], r
        return r["result"]
    assert pol([])["action"] == "cooperate"
    assert pol(["cooperate"] * 3)["action"] == "cooperate"
    assert pol(["cooperate", "defect", "defect", "defect", "defect"])["p_cooperate"] == 0.0     # exploiter
    assert pol(["cooperate", "cooperate"], rounds_left=1)["action"] == "defect"
    r = pol(["cooperate", "defect"], forgive_prob=0.0)
    assert 0 < r["p_cooperate"] <= 0.4
    runs = {pol(["cooperate", "defect"], seed=s)["action"] for s in range(40)}
    assert runs == {"cooperate", "defect"}                     # forgives sometimes, retaliates mostly
    assert pol(["C", "D"], cooperate_label="C", defect_label="D", seed=0)["action"] in ("C", "D")
    assert catalog.call("reciprocity_policy", {"opponent_history": ["maybe"]}, dl())["ok"] is False


def test_profile_store_merge_and_corruption(tmp_path):
    root = str(tmp_path / "opp")
    assert op.load_profile("team/../x", root) == {}
    op.update_profile("team/../x", {"games": 1, "rounds": 10, "coop_rounds": 8}, "dilemma", root)
    p = op.update_profile("team/../x", {"games": 1, "rounds": 10, "coop_rounds": 2, "evil": 5, "wins": True}, "dilemma", root)
    assert p["games"] == 2 and p["rounds"] == 20 and p["coop_rounds"] == 10 and "evil" not in p and "wins" not in p
    assert p["families"]["dilemma"]["games"] == 2
    assert "50%" in op.profile_summary(p)
    import os
    files = os.listdir(root)
    assert files == ["team_.._x.json"], files               # sanitized name, no stray temp or lock files
    (tmp_path / "opp" / "team_.._x.json").write_text("{broken")
    assert op.load_profile("team/../x", root) == {}
    assert op.update_profile("team/../x", {"games": 1}, None, root)["games"] == 1
    r = catalog.call("profile_store", {"op": "load", "team": "team/../x", "root": root}, dl())
    assert r["ok"] and r["result"]["profile"]["games"] == 1
    assert catalog.call("profile_store", {"op": "nope", "team": "x"}, dl())["ok"] is False


def test_registration_flags():
    names = {s.name: s for s in catalog.list_tools()}
    assert names["opponent_predictor"].model_callable and names["reciprocity_policy"].model_callable
    assert not names["profile_store"].model_callable


RULES_RPS = ("Rock Paper Scissors, played simultaneously. Rock beats scissors, paper beats rock, scissors beats "
             "paper. Pick one each round.")


def test_detector_simultaneous_with_history():
    obs = "Round 1: you rock, opponent paper\nRound 2: you rock, opponent paper\nRound 3: you paper, opponent paper\n" \
          "Round 4: you scissors, opponent paper\nChoose."
    f = precompute(obs, RPS, {"opponent_history": ["paper"] * 4, "my_history": ["rock", "rock", "paper", "scissors"]},
                   RULES_RPS, dl())
    assert "opponent_predictor" in f.used and any("scissors" in l for l in f.lines)
    assert f.certain is None                                  # a prediction is never certain


def test_detector_silent_without_signals():
    f = precompute("Your turn.", RPS, {}, "Tic tac toe on a board.", dl())
    assert "opponent_predictor" not in f.used and "reciprocity_policy" not in f.used
    f = precompute("Your turn.", RPS, {}, RULES_RPS, dl())     # simultaneous but no history yet
    assert "opponent_predictor" not in f.used


def test_detector_cooperation_and_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    op.update_profile("teamB", {"games": 3, "rounds": 30, "coop_rounds": 3})
    rules = "Each round both players secretly choose cooperate or defect. 10 rounds."
    f = precompute("x", ["cooperate", "defect"], {"opponent": "teamB", "opponent_history": ["defect"] * 5,
                                                  "my_history": ["cooperate"] * 5}, rules, dl())
    assert "reciprocity_policy" in f.used and "profile_store" in f.used
    assert any("cooperates 10%" in l for l in f.lines)


def test_select_offers_tools():
    t = select_tools({}, "", RULES_RPS, precompute("", RPS, {}, RULES_RPS, dl()))
    assert "opponent_predictor" in t
    t = select_tools({}, "", "choose cooperate or defect each round", precompute("", None, {}, "", dl()))
    assert "reciprocity_policy" in t


def test_json_safe():
    json.dumps(pred(["rock"] * 6, ["paper"] * 6))
