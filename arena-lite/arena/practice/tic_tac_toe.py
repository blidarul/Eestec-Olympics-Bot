"""Tic-Tac-Toe (practice): 3x3 classic and 5x5 four-in-a-row. Coordinates are a column letter
plus a row number, A1 = top-left."""
from __future__ import annotations

import copy
import random
import re

from ..core import Game

MARK = ("X", "O")
_CELL_RE = re.compile(r"^(?:place|play|move)?\s*([a-z])\s*(\d{1,2})$")
_CELL_RE_REV = re.compile(r"^(?:place|play|move)?\s*(\d{1,2})\s*([a-z])$")


class TicTacToe(Game):
    id = "tic_tac_toe"
    name = "Tic-Tac-Toe"
    category = "practice"
    blurb = "The classic grid duel, plus a roomier 5x5 board where you need four in a row."
    howto = "Players take turns putting their mark in an empty square. The first to get enough marks in a row, across, down or diagonally, wins."
    duplicate_safe = True  # open board, no randomness: a replay leaks nothing (core.Game.duplicate_safe)

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "3x3 classic", "size": 3, "connect": 3},
            {"label": "5x5, four in a row", "size": 5, "connect": 4},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.size = max(3, min(9, int(self.variant.get("size", 3))))
        self.k = max(3, min(self.size, int(self.variant.get("connect", 3))))
        self.label = str(self.variant.get("label", ""))
        self.max_steps = self.size * self.size
        self.board: list[list[int | None]] = [[None] * self.size for _ in range(self.size)]  # [row][col]
        self.current = 0
        self.moves: list[dict] = []
        self.win_cells: list[list[int]] = []
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    # ---------------------------------------------------------------- helpers
    def _name(self, r: int, c: int) -> str:
        return f"{chr(ord('A') + c)}{r + 1}"

    def _empty(self) -> list[tuple[int, int]]:
        return [(r, c) for r in range(self.size) for c in range(self.size) if self.board[r][c] is None]

    def _render(self) -> str:
        cols = "   " + " ".join(chr(ord("A") + c) for c in range(self.size))
        rows = [cols]
        for r in range(self.size):
            cells = [MARK[v] if v is not None else "." for v in self.board[r]]
            rows.append(f"{r + 1:>2} " + " ".join(cells))
        return "\n".join(rows)

    def _line_through(self, r: int, c: int) -> list[list[int]]:
        me = self.board[r][c]
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            cells = [[r, c]]
            for sign in (1, -1):
                rr, cc = r + sign * dr, c + sign * dc
                while 0 <= rr < self.size and 0 <= cc < self.size and self.board[rr][cc] == me:
                    cells.append([rr, cc])
                    rr, cc = rr + sign * dr, cc + sign * dc
            if len(cells) >= self.k:
                return sorted(cells)
        return []

    # --------------------------------------------------------------- interface
    def rules(self) -> str:
        n, k = self.size, self.k
        last_col = chr(ord("A") + n - 1)
        empty = "\n".join(
            ["   " + " ".join(chr(ord("A") + c) for c in range(n))]
            + [f"{r + 1:>2} " + " ".join("." for _ in range(n)) for r in range(n)])
        return f"""TIC-TAC-TOE - {self.label}. 2 players, alternating turns.

GOAL
Be the first to get {k} of your marks in an unbroken straight line: horizontally, vertically
or diagonally.

BOARD
A {n}x{n} grid. Columns are letters A-{last_col} (left to right), rows are numbers 1-{n} (top to
bottom). A1 is the top-left corner, {last_col}{n} the bottom-right corner:
{empty}
Seat 0 plays X and moves first; seat 1 plays O. On your turn you put one mark on any EMPTY cell.

END AND SCORING
The first player with {k} in a row wins (score 1, loser 0). If the board fills up with no line,
the game is a draw (0-0). The game cannot last more than {n * n} moves (move cap).

ACTION FORMAT
A cell name: column letter + row number, e.g. "B2". Case does not matter and "place B2" also
works. Examples: "A1", "c3", "place {last_col}{n}". Occupied or non-existent cells are illegal
(first time: a warning and the same turn again; second time: you lose the game). You also receive
the list of legal moves every turn.

WHAT YOU OBSERVE EACH TURN
The board as a text grid (X, O, and . for empty), which mark is yours, and the list of moves
played so far."""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        return self.cap_list([self._name(r, c) for r, c in self._empty()])

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        a = self.clean(action).strip(" .!\"'`")
        m = _CELL_RE.match(a)
        if m:
            col, row = m.group(1), m.group(2)
        else:
            m = _CELL_RE_REV.match(a)
            if not m:
                return None
            row, col = m.group(1), m.group(2)
        c = ord(col) - ord("a")
        r = int(row) - 1
        if not (0 <= r < self.size and 0 <= c < self.size) or self.board[r][c] is not None:
            return None
        return self._name(r, c)

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        seat = self.current
        a = self.normalize(seat, actions.get(seat, ""))
        if a is None:
            raise ValueError(f"illegal action {actions.get(seat)!r} for seat {seat}")
        c = ord(a[0]) - ord("A")
        r = int(a[1:]) - 1
        self.board[r][c] = seat
        self.moves.append({"seat": seat, "cell": a, "row": r, "col": c})
        line = self._line_through(r, c)
        if line:
            self.over, self.winner, self.win_cells = True, seat, line
            self.end_reason = f"seat {seat} ({MARK[seat]}) made {self.k} in a row"
        elif not self._empty():
            self.over, self.winner = True, None
            self.end_reason = "board full, no line: draw"
        else:
            self.current = 1 - seat

    def is_over(self) -> bool:
        return self.over

    def result(self) -> dict:
        if not self.over:
            return {"winner": None, "scores": [0, 0], "reason": "in progress"}
        scores = [0, 0]
        if self.winner is not None:
            scores[self.winner] = 1
        return {"winner": self.winner, "scores": scores, "reason": self.end_reason}

    def observation(self, seat: int) -> str:
        L = [f"TIC-TAC-TOE - {self.label}. You are seat {seat} and play {MARK[seat]}; "
             f"the opponent plays {MARK[1 - seat]}."]
        if self.over:
            L.append(f"The game is over: {self.end_reason}.")
        elif self.current == seat:
            L.append(f"Your turn (move {len(self.moves) + 1}). Need {self.k} in a row.")
        else:
            L.append("Waiting for the opponent.")
        L.append(self._render())
        if self.moves:
            L.append("Moves so far: " + ", ".join(
                f"{MARK[m['seat']]} {m['cell']}" for m in self.moves))
        return "\n".join(L)

    def frame(self) -> dict:
        return copy.deepcopy(self._frame())  # snapshot: never share live lists

    def _frame(self) -> dict:
        return {
            "label": self.label, "size": self.size, "connect": self.k,
            "board": [list(r) for r in self.board], "moves": self.moves,
            "last": self.moves[-1] if self.moves else None,
            "to_move": None if self.over else self.current,
            "win_cells": self.win_cells, "over": self.over,
            "result": self.result() if self.over else None,
        }

    def random_action(self, seat: int, rng: random.Random) -> str:
        r, c = rng.choice(self._empty())
        return self._name(r, c)
