"""Large boards (5x5 k-in-row, 7x6 gravity): a tool turn plus its chat call stays under 8 s (X2.3)."""
import time

import pytest

from strategies.base import TurnState
from strategies.think_ahead import search as ta

SIM = r'''
R, C, K, GRAV = {R}, {C}, {K}, {GRAV}

def _name(r, c):
    return chr(65 + c) + str(r + 1)

class State:
    def __init__(self, board=None, current=0):
        self.board = list(board) if board else [None] * (R * C)
        self.current = current

    def _win(self, p):
        b = self.board
        for r in range(R):
            for c in range(C):
                for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    if all(0 <= r + i * dr < R and 0 <= c + i * dc < C and b[(r + i * dr) * C + c + i * dc] == p for i in range(K)):
                        return True
        return False

    def winner(self):
        for p in (0, 1):
            if self._win(p):
                return p
        return None

    def legal_actions(self):
        if self.winner() is not None:
            return []
        out = []
        for c in range(C):
            if GRAV:
                for r in range(R - 1, -1, -1):
                    if self.board[r * C + c] is None:
                        out.append(_name(r, c)); break
            else:
                out += [_name(r, c) for r in range(R) if self.board[r * C + c] is None]
        return out

    def step(self, action):
        c, r = ord(action[0]) - 65, int(action[1:]) - 1
        b = list(self.board); b[r * C + c] = self.current
        return State(b, 1 - self.current)

    def is_terminal(self):
        return self.winner() is not None or all(x is not None for x in self.board)

    def evaluate(self, seat):
        w = self.winner()
        return 0.0 if w is None else (1.0 if w == seat else -1.0)

def parse(obs, seat):
    rows = [l for l in obs.split("\n") if l[:2].strip().isdigit()]
    cells = []
    for l in rows:
        cells += l.split()[1:]
    board = [None if x == "." else (0 if x == "X" else 1) for x in cells]
    return State(board, 0 if board.count(0) == board.count(1) else 1)
'''


def _obs(R, C, cells):
    head = "   " + " ".join(chr(65 + c) for c in range(C))
    return "\n".join(["BOARD", head] + [f"{r + 1:>2} " + " ".join(cells[r * C:(r + 1) * C]) for r in range(R)])


class SlowLLM:
    def available(self): return True
    def over_budget(self): return False

    def ask_json(self, s, u, timeout=2.5, **k):
        time.sleep(min(timeout, 1.0))
        return {"c": "Here we go."}


@pytest.mark.parametrize("R,C,K,GRAV,cells", [
    (5, 5, 4, 0, list("X...." "O...." "....." "....." ".....")),
    (6, 7, 4, 1, list("." * 40 + "OX")),
])
def test_large_board_turn_under_8s(tmp_path, R, C, K, GRAV, cells):
    p = tmp_path / "sim.py"
    p.write_text(SIM.format(R=R, C=C, K=K, GRAV=GRAV), encoding="utf-8")
    art = {"family": "grid_board", "classification": {}, "forbidden_terms": [], "chat_bank": ["Good luck."],
           "simulator": {"path": str(p), "verified": True, "has_chance": False, "calibration": {"transitions_per_sec": 20000.0}}}
    from importlib import import_module
    game = import_module("solvers.adapter").load_simulator(str(p))
    legal = game.legal(game.parse(_obs(R, C, cells), 0))
    for n in range(3):
        st = TurnState("g", "rules", {}, 0, _obs(R, C, cells), legal, n + 1, None, ["hello"] if n == 1 else [], art,
                       time.monotonic() + 20.0, SlowLLM(), match_id="big", game_index=n)
        t0 = time.monotonic()
        d = ta.STRATEGY.decide(st)
        dt = time.monotonic() - t0
        print(f"{R}x{C} turn {n}: {dt:.2f}s via {d.info}")
        assert d.action in legal and d.chat and dt < 8.0


def test_search_budget_shrinks_with_the_clock(tmp_path):
    p = tmp_path / "sim.py"
    p.write_text(SIM.format(R=5, C=5, K=4, GRAV=0), encoding="utf-8")
    art = {"family": "grid_board", "classification": {}, "forbidden_terms": [], "chat_bank": ["Good luck."],
           "simulator": {"path": str(p), "verified": True, "has_chance": False, "calibration": {"transitions_per_sec": 20000.0}}}
    cells = list("X...." "O...." "....." "....." ".....")
    st = TurnState("g", "rules", {}, 0, _obs(5, 5, cells), None, 1, None, [], art, time.monotonic() + 4.0, None, match_id="s", game_index=1)
    t0 = time.monotonic()
    d = ta.STRATEGY.decide(st)
    assert d.chat and time.monotonic() - t0 < 2.5   # 4 s clock: search stops at half of it
