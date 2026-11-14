"""M6: search on a verified simulator (simsearch, detector in precompute, mdp, determinization)."""
import random
import time

from solvers import catalog, mcts, mdp, simsearch
from solvers.adapter import load_simulator_source
from solvers.precompute import precompute
from tests.alex.games import PIG_SIM, TTT_SIM, pig_sample, ttt_sample


def write(tmp_path, src, name="sim.py"):
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    return str(p)


def dl(s=3):
    return time.monotonic() + s


def test_search_move_alpha_beta_proven_win(tmp_path):
    spec = {"path": write(tmp_path, TTT_SIM), "verified": True, "has_chance": False}
    smp = ttt_sample(list("XX.OO...."))
    r = simsearch.search_move(spec, smp["observation"], smp["legal_actions"], 0, dl())
    assert r["move"] == "C1" and r["proven"] and r["tool"] == "alpha-beta"


def test_search_move_unverified_or_missing_gives_none(tmp_path):
    smp = ttt_sample(list("XX.OO...."))
    assert simsearch.search_move({"path": write(tmp_path, TTT_SIM), "verified": False}, smp["observation"], None, 0, dl()) is None
    assert simsearch.search_move({"path": "/no/such.py", "verified": True}, smp["observation"], None, 0, dl()) is None
    assert simsearch.search_move(None, "x", None, 0, dl()) is None
    assert simsearch.search_move({"path": write(tmp_path, TTT_SIM), "verified": True}, "garbage", None, 0, dl()) is None


def test_search_move_chance_game_uses_mcts_never_proven(tmp_path):
    spec = {"path": write(tmp_path, PIG_SIM), "verified": True, "has_chance": True}
    smp = pig_sample(a=18, b=3, t=2)
    r = simsearch.search_move(spec, smp["observation"], smp["legal_actions"], 0, dl(0.6), random.Random(1))
    assert r["move"] == "hold" and r["tool"] == "mcts" and not r["proven"] and 0 < r["share"] <= 1


def test_precompute_detector_fact_and_certain(tmp_path):
    art = {"simulator": {"path": write(tmp_path, TTT_SIM), "verified": True, "has_chance": False}}
    smp = ttt_sample(list("XX.OO...."))
    f = precompute(smp["observation"], smp["legal_actions"], art, "", time.monotonic() + 0.3, search_deadline=dl(5))
    assert "sim_search" in f.used and f.certain and f.certain["move"] == "C1" and f.certain["tool"] == "sim_search"
    # no search budget -> detector silent
    f = precompute(smp["observation"], smp["legal_actions"], art, "", time.monotonic() + 0.3)
    assert "sim_search" not in f.used


def test_precompute_mcts_is_fact_only(tmp_path):
    art = {"simulator": {"path": write(tmp_path, PIG_SIM), "verified": True, "has_chance": True}}
    smp = pig_sample(a=18, b=3, t=2)
    f = precompute(smp["observation"], smp["legal_actions"], art, "", time.monotonic() + 0.3, search_deadline=dl(0.5))
    assert "sim_search" in f.used and f.certain is None and "Search recommends hold" in " ".join(f.lines)
    f = precompute(smp["observation"], smp["legal_actions"], {"simulator": {"path": "x", "verified": False}}, "",
                   time.monotonic() + 0.3, search_deadline=dl(1))
    assert "sim_search" not in f.used


HIDDEN_SIM = '''
import random
class State:
    """Pick a door: the prize position is hidden; sample_hidden re-draws it, step scores 1 if the pick matches."""
    def __init__(self, prize=None, pick=None):
        self.prize, self.pick, self.current = prize, pick, 0
    def legal_actions(self):
        return [] if self.pick is not None else ["a", "b", "c"]
    def step(self, a):
        return State(self.prize if self.prize is not None else "b", a)
    def is_terminal(self):
        return self.pick is not None
    def evaluate(self, seat):
        return 1.0 if self.pick == self.prize else 0.0
    def sample_hidden(self, rng):
        return State(rng.choice(["b", "b", "b", "a"]), self.pick)
def parse(obs, seat):
    return State()
'''


def test_mcts_determinizes_hidden_state():
    g = load_simulator_source(HIDDEN_SIM)
    assert callable(getattr(g, "determinize", None))
    s = g.parse("x", 0)
    r = mcts.search(g, s, 0, time.monotonic() + 0.4, rng=random.Random(2), min_sims=10 ** 9)
    assert r.action == "b" and r.sims > 100            # prize is 'b' in 3 of 4 worlds


def test_mdp_value_iteration_and_tool():
    # chain: s0 --go--> s1 (reward 1) --go--> end (reward 2); s0 --stay--> s0 (0) is worse
    table = {"s0": {"go": [[1.0, "s1", 1.0]], "stay": [[1.0, "s0", 0.0]]}, "s1": {"go": [[1.0, "end", 2.0]]}, "end": {}}
    res = mdp.solve("s0", lambda s: list(table[s]), lambda s, a: table[s][a], discount=0.9, deadline=dl())
    assert res.converged and res.policy["s0"] == "go" and abs(res.values["s0"] - (1 + 0.9 * 2)) < 1e-6
    r = catalog.call("mdp_solve", {"table": table, "start": "s0", "discount": 0.9}, dl())
    assert r["ok"] and r["result"]["action"] == "go"
    big = mdp.solve(0, lambda s: ["n"], lambda s, a: [(1.0, s + 1, 0.0)], deadline=dl(), max_states=50)
    assert big is None                                  # unbounded state space refused, no hang


def test_mdp_stochastic_choice():
    # risky: 0.5 -> 10, 0.5 -> 0 (EV 5) vs safe 4
    acts = {"start": ["safe", "risky"]}
    tr = {("start", "safe"): [(1.0, "end", 4.0)], ("start", "risky"): [(0.5, "end", 10.0), (0.5, "end", 0.0)]}
    res = mdp.solve("start", lambda s: acts.get(s, []), lambda s, a: tr[(s, a)], deadline=dl())
    assert res.policy["start"] == "risky" and abs(res.values["start"] - 5.0) < 1e-9


def test_sim_search_tool(tmp_path):
    p = write(tmp_path, TTT_SIM)
    smp = ttt_sample(list("XX.OO...."))
    r = catalog.call("sim_search", {"path": p, "observation": smp["observation"], "legal_actions": smp["legal_actions"]}, dl())
    assert r["ok"] and r["result"]["move"] == "C1"
    bad = catalog.call("sim_search", {"path": p, "observation": "nope"}, dl())
    assert bad["ok"] is False
    spec = [t for t in catalog.list_tools() if t.name == "sim_search"][0]
    assert spec.model_callable is False
