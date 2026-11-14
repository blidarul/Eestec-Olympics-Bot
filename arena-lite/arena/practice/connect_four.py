"""Connect Four: gravity-powered line-making game on vertical grids."""
from __future__ import annotations

import copy
import random
import re

from ..core import Game

MARK = ("X", "O")
_DROP_RE = re.compile(r"^(?:drop|play|move|col|column)?\s*(\d+)$", re.IGNORECASE)


class ConnectFour(Game):
    id = "connect_four"
    name = "Connect Four"
    category = "think"
    blurb = "Gravity-powered tactics: build threats, block lines, and trap your rival in a forced loss."
    howto = "Players take turns dropping discs into columns, where they fall to the bottom. The first to line up enough discs in a row, across, up or diagonally, wins."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "6x7, connect 4", "rows": 6, "cols": 7, "connect": 4},
            {"label": "5x6, connect 4", "rows": 5, "cols": 6, "connect": 4},
            {"label": "7x9, connect 5", "rows": 7, "cols": 9, "connect": 5},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.rows = max(4, min(10, int(self.variant.get("rows", 6))))
        self.cols = max(4, min(12, int(self.variant.get("cols", 7))))
        self.k = max(3, min(max(self.rows, self.cols), int(self.variant.get("connect", 4))))
        self.label = str(self.variant.get("label", f"{self.rows}x{self.cols}, connect {self.k}"))
        self.max_steps = self.rows * self.cols
        self.board: list[list[int | None]] = [[None] * self.cols for _ in range(self.rows)]  # row 0 = top, row rows-1 = bottom
        self.current = 0
        self.moves: list[dict] = []
        self.win_cells: list[list[int]] = []
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _open_cols(self) -> list[int]:
        """1-indexed open columns."""
        return [c + 1 for c in range(self.cols) if self.board[0][c] is None]

    def _lowest_empty_row(self, col_0: int) -> int | None:
        """Find the lowest empty row in column col_0 (falls to the bottom)."""
        for r in range(self.rows - 1, -1, -1):
            if self.board[r][col_0] is None:
                return r
        return None

    def _render(self) -> str:
        nums = " " + " ".join(str(c + 1) for c in range(self.cols))
        bar = "+" + "-" * (2 * self.cols - 1) + "+"
        lines = [nums]
        for r in range(self.rows):
            row_str = " ".join(MARK[v] if v is not None else "." for v in self.board[r])
            lines.append(f"|{row_str}|")
        lines.append(bar)
        lines.append(nums)
        return "\n".join(lines)

    def _line_through(self, r: int, c: int) -> list[list[int]]:
        me = self.board[r][c]
        if me is None:
            return []
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            cells = [[r, c]]
            for sign in (1, -1):
                rr, cc = r + sign * dr, c + sign * dc
                while 0 <= rr < self.rows and 0 <= cc < self.cols and self.board[rr][cc] == me:
                    cells.append([rr, cc])
                    rr, cc = rr + sign * dr, cc + sign * dc
            if len(cells) >= self.k:
                return sorted(cells)
        return []

    def rules(self) -> str:
        return f"""CONNECT FOUR - {self.rows} rows x {self.cols} columns, connect {self.k} to win.

GOAL
Be the first to get {self.k} of your own discs in an unbroken straight line: horizontally,
vertically or diagonally (both diagonal directions count).

BOARD AND PIECES
The board is a vertical grid with {self.rows} rows and {self.cols} columns, numbered 1 to {self.cols} from left to right.
Player 0 plays X and moves first; Player 1 plays O. Players alternate, one disc per turn.
A disc is dropped into a column and falls to the LOWEST empty cell of that column (gravity).
You cannot choose the row, and you cannot drop into a full column. Passing is not allowed.

ACTION FORMAT
    drop <column>
where <column> is a number from 1 to {self.cols} of a column that is not full.
Examples:  "drop 4"   "drop 1"   "drop {self.cols}"
Anything else (a full column, a number out of range, other text) is illegal (first time: a warning
and the same turn again; second time: you lose the game). The arena also sends the list of legal
moves every turn.

WHAT YOU OBSERVE
The board drawn in text, top row first, "." = empty, with column numbers above and below, plus
the move history and the open columns.

HOW THE GAME ENDS AND IS SCORED
- The first player to complete a line of {self.k} (or longer) wins immediately (score 1, loser 0).
- If the board fills up ({self.max_steps} discs, the move cap) without a line, the game is a draw (0.5 each)."""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        return [f"drop {c}" for c in self._open_cols()]

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        a = self.clean(action)
        m = _DROP_RE.match(a)
        if not m:
            return None
        col = int(m.group(1))
        if 1 <= col <= self.cols and col in self._open_cols():
            return f"drop {col}"
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        seat = self.current
        raw = actions.get(seat, "")
        norm_act = self.normalize(seat, raw)
        if norm_act is None:
            raise ValueError(f"illegal action {raw!r} for seat {seat}")
        col = int(norm_act.split()[1])
        c = col - 1
        r = self._lowest_empty_row(c)
        if r is None:
            raise ValueError(f"column {col} is full")
        self.board[r][c] = seat
        self.moves.append({"seat": seat, "col": col, "row": r})
        line = self._line_through(r, c)
        if line:
            self.over, self.winner, self.win_cells = True, seat, line
            self.end_reason = f"seat {seat} ({MARK[seat]}) made {self.k} in a row"
        elif not self._open_cols():
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
        else:
            scores = [0.5, 0.5]
        return {"winner": self.winner, "scores": scores, "reason": self.end_reason}

    def observation(self, seat: int) -> str:
        lines = [
            f"CONNECT FOUR - {self.label}. You are seat {seat} and play {MARK[seat]}; the opponent plays {MARK[1 - seat]}."
        ]
        if self.over:
            lines.append(f"The game is over: {self.end_reason}.")
        elif self.current == seat:
            lines.append(f"Your turn (move {len(self.moves) + 1}). Need {self.k} in a row.")
        else:
            lines.append("Waiting for the opponent.")
        lines.append(self._render())
        open_cols = self._open_cols()
        if open_cols:
            lines.append("Open columns: " + ", ".join(str(c) for c in open_cols))
        if self.moves:
            lines.append("Moves so far: " + ", ".join(f"{MARK[m['seat']]} drop {m['col']}" for m in self.moves))
        return "\n".join(lines)

    def frame(self) -> dict:
        return copy.deepcopy(self._frame())

    def _frame(self) -> dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "connect": self.k,
            "board": [list(r) for r in self.board],
            "moves": self.moves,
            "last": self.moves[-1] if self.moves else None,
            "win_cells": self.win_cells,
            "to_move": [] if self.over else [self.current],
            "over": self.over,
            "result": self.result() if self.over else None,
        }

    def random_action(self, seat: int, rng: random.Random) -> str:
        open_c = self._open_cols()
        if not open_c:
            return "pass"
        return f"drop {rng.choice(open_c)}"
