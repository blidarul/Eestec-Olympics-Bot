"""Solver tests with games written INSIDE the tests (no game-specific code in the bot, 10.7)."""
import itertools
import time

from solvers.deduction import best_split, eliminate
from solvers.search import best_move

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


class TTT:
    """state = (board tuple of '.XO', player to move)."""
    @staticmethod
    def parse(obs):
        rows = [r for r in obs.split("\n") if r.strip()]
        cells = "".join(rows).replace(" ", "")
        b = tuple(cells)
        return b, "X" if b.count("X") == b.count("O") else "O"

    def legal(self, s):
        return [] if self.winner(s[0]) else [i for i, c in enumerate(s[0]) if c == "."]

    def apply(self, s, a):
        b = list(s[0]); b[a] = s[1]
        return tuple(b), "O" if s[1] == "X" else "X"

    def winner(self, b):
        for l in LINES:
            if b[l[0]] != "." and b[l[0]] == b[l[1]] == b[l[2]]:
                return b[l[0]]

    def is_terminal(self, s):
        return bool(self.winner(s[0])) or "." not in s[0]

    def score(self, s, seat):  # seat = 'X' or 'O'
        w = self.winner(s[0])
        return 0.0 if not w else (1.0 if w == seat else -1.0)

    def to_move(self, s):
        return s[1]


def test_takes_immediate_win():
    g = TTT()
    s = g.parse("XX.\nOO.\n...")
    a, v, d = best_move(g, s, "X", time.monotonic() + 2)
    assert a == 2 and v == 1.0


def test_blocks_loss():
    g = TTT()
    s = g.parse("OO.\nX..\n..X")  # X to move must block at 2 (O threatens 0,1,2)
    a, v, _ = best_move(g, s, "X", time.monotonic() + 2)
    assert a == 2


def test_empty_board_is_a_draw_value_and_perfect_play_never_loses():
    g = TTT()
    a, v, d = best_move(g, g.parse("...\n...\n..."), "X", time.monotonic() + 5)
    assert v == 0.0 and d >= 9
    # perfect vs perfect: draw
    s = g.parse("...\n...\n...")
    while not g.is_terminal(s):
        m, _, _ = best_move(g, s, s[1], time.monotonic() + 2)
        s = g.apply(s, m)
    assert g.winner(s[0]) is None


def test_hard_deadline_returns_a_legal_move_fast():
    g = TTT()
    s = g.parse("...\n...\n...")
    t0 = time.monotonic()
    a, v, d = best_move(g, s, "X", t0 + 0.0)  # deadline already passed
    assert time.monotonic() - t0 < 0.5 and a in g.legal(s)


def test_no_moves_and_single_move():
    g = TTT()
    full = g.parse("XOX\nXOO\nOXX")
    assert best_move(g, full, "X", time.monotonic() + 1)[0] is None
    one = g.parse("XOX\nXOO\nOX.")
    assert best_move(g, one, "O", time.monotonic() + 1)[0] == 8


def test_deduction_mastermind_like():
    # secret is 3-digit code; feedback = number of exact position matches
    cands = ["".join(p) for p in itertools.product("0123", repeat=3)]
    comp = lambda c, g: sum(a == b for a, b in zip(c, g))
    secret = "213"
    pool = list(cands)
    steps = 0
    while len(pool) > 1 and steps < 10:
        g = best_split(pool, cands, comp)
        pool = eliminate(pool, g, comp(secret, g), comp)
        steps += 1
    assert pool == [secret] and steps <= 6


def test_eliminate_never_empties_and_split_handles_deadline():
    comp = lambda c, g: c == g
    assert eliminate(["a", "b"], "a", "zz", comp) == ["a", "b"]
    assert best_split(["a", "b", "c", "d"], None, comp, deadline=time.monotonic() - 1) == "a"
    assert best_split([], None, comp) is None
