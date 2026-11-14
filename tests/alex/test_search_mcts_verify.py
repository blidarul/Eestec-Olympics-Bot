"""Alpha-beta (transposition table, exact flag), MCTS, adapter and verify, on games defined in tests/alex/games.py."""
import random
import time

import pytest

from solvers import mcts, search
from solvers.adapter import load_simulator_source
from solvers.verify import verify, verify_isolated, verify_report
from tests.alex.games import PIG_SIM, TTT_SIM, pig_sample, ttt_sample


def ttt():
    return load_simulator_source(TTT_SIM)


def test_adapter_zobrist_key_is_int_and_distinguishes_states():
    g = ttt()
    s = g.initial()
    a = g.apply(s, "A1")
    b = g.apply(s, "B2")
    assert isinstance(g.key(a), int) and g.key(a) != g.key(b) and g.key(a) != g.key(s)
    assert g.key(g.apply(g.apply(s, "A1"), "B2")) == g.key(g.apply(g.apply(s, "A1"), "B2"))
    assert g.key(a) == g.key(g.apply(g.initial(), "A1"))   # same position, same hash


def test_alpha_beta_solves_empty_board_exactly_with_tt():
    g = ttt()
    r = search.search(g, g.initial(), 0, time.monotonic() + 10)
    assert r.exact and r.value == 0.0 and not r.timed_out        # tic-tac-toe is a draw
    assert r.nodes < 60000                                       # the table prunes transpositions (plain: ~550k)


def test_alpha_beta_wins_and_blocks():
    g = ttt()
    s = g.parse(ttt_sample(list("XX.OO....") )["observation"], 0)
    r = search.search(g, s, 0, time.monotonic() + 5)
    assert r.action == "C1" and r.value == 1.0
    s = g.parse(ttt_sample(list("OO.X....X"))["observation"], 0)     # O threatens C1, X to move: must block
    assert search.search(g, s, 0, time.monotonic() + 5).action == "C1"


def test_alpha_beta_deadline_returns_a_move():
    g = ttt()
    t0 = time.monotonic()
    r = search.search(g, g.initial(), 0, t0 + 0.02)
    assert r.action in g.legal(g.initial()) and time.monotonic() - t0 < 1.0


def test_integer_keys_only_in_table():
    g = ttt()
    tt = search.make_table()
    search.search(g, g.initial(), 0, time.monotonic() + 10, table=tt)
    assert tt.table and all(isinstance(k, int) for k in tt.table)


def test_mcts_takes_win_and_blocks_deterministic_game():
    g = ttt()
    s = g.parse(ttt_sample(list("XX.OO...."))["observation"], 0)
    r = mcts.search(g, s, 0, time.monotonic() + 0.6, rng=random.Random(3))
    assert r.action == "C1" and r.sims > 100
    s = g.parse(ttt_sample(list("X.XO.O..."))["observation"], 0)
    r = mcts.search(g, s, 0, time.monotonic() + 0.6, rng=random.Random(3))
    assert r.action == "B1"          # completes the top row


def test_mcts_chance_game_runs_and_returns_legal_move():
    g = load_simulator_source(PIG_SIM)
    s = g.parse(pig_sample(a=18, b=3, t=2)["observation"], 0)       # 2 points from the target: hold? 18+2 = 20 wins
    r = mcts.search(g, s, 0, time.monotonic() + 0.5, rng=random.Random(1))
    assert r.action == "hold" and r.sims > 50
    assert g.has_chance(s)


def test_mcts_respects_deadline_and_single_move():
    g = load_simulator_source(PIG_SIM)
    s = g.parse(pig_sample(a=0, b=0, t=0)["observation"], 0)         # only "roll"
    assert mcts.search(g, s, 0, time.monotonic() + 5).action == "roll"
    s = g.parse(pig_sample()["observation"], 0)
    t0 = time.monotonic()
    mcts.search(g, s, 0, t0 + 0.2)
    assert time.monotonic() - t0 < 0.6


def test_sims_from_calibration():
    assert mcts.sims_from_calibration({"transitions_per_sec": 44400.0, "usable": True}, 2.0) > 1000
    assert mcts.sims_from_calibration({"usable": False}, 2.0) is None
    assert mcts.sims_from_calibration(None, 2.0) is None


# ---- verify -----------------------------------------------------------------------------------
def test_verify_accepts_good_simulator():
    g = ttt()
    v = {"sample_turn": ttt_sample(list("XO.X....O"))}
    assert verify(g, v)
    assert verify(load_simulator_source(PIG_SIM), {"sample_turn": pig_sample()})


def test_verify_rejects_legal_set_mismatch_missing_sample_and_parse_errors():
    g = ttt()
    bad = ttt_sample(list("XO.X....O"))
    bad["legal_actions"] = bad["legal_actions"][:-1]
    assert verify_report(g, {"sample_turn": bad})[0] is False
    assert verify_report(g, {})[1] == "no sample_turn"
    broken = ttt_sample(list("XO.X....O"))
    broken["observation"] = "nothing parseable here"
    ok, why = verify_report(g, {"sample_turn": broken})
    assert not ok and "ValueError" in why


def test_verify_rejects_simulator_without_parse():
    src = TTT_SIM.split("def parse")[0]
    g = load_simulator_source(src)
    ok, why = verify_report(g, {"sample_turn": ttt_sample(list("XO.X....O"))})
    assert not ok and "parse" in why


def test_verify_rejects_endless_playout():
    src = '''
class State:
    def __init__(self): self.current = 0
    def legal_actions(self): return ["a"]
    def step(self, a): return State()
    def is_terminal(self): return False
    def evaluate(self, seat): return 0.0
def parse(obs, seat): return State()
'''
    g = load_simulator_source(src)
    ok, why = verify_report(g, {"sample_turn": {"observation": "x", "legal_actions": ["a"]}})
    assert not ok and "500" in why


def test_verify_isolated_good_and_hanging(tmp_path):
    p = tmp_path / "sim.py"
    p.write_text(TTT_SIM, encoding="utf-8")
    out = verify_isolated(str(p), {"sample_turn": ttt_sample(list("XO.X....O"))}, timeout=30)
    assert out["verified"] is True and out["has_chance"] is False
    hang = tmp_path / "hang.py"
    hang.write_text("while True:\n    pass\n", encoding="utf-8")
    t0 = time.monotonic()
    out = verify_isolated(str(hang), {"sample_turn": ttt_sample(list("XO.X....O"))}, timeout=3)
    assert out["verified"] is False and time.monotonic() - t0 < 10
