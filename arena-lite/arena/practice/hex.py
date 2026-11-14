"""Hex: pure topological connection game on a diamond grid; draws are impossible."""
from __future__ import annotations

import collections
import re

from ..core import Game

_PLACE_RE = re.compile(r"^(?:place\s+)?([a-z])(\d+)$", re.IGNORECASE)


class Hex(Game):
    id = "hex"
    name = "Hex"
    category = "think"
    blurb = "Pure connection strategy on a diamond grid: bridge your edges, block your rival, and never settle for a draw."
    howto = "Player 0 connects top to bottom; Player 1 connects left to right. Players alternate placing stones on empty hexes. Hex never ends in a draw."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "7x7", "size": 7, "swap": False},
            {"label": "5x5", "size": 5, "swap": False},
            {"label": "7x7 with swap rule", "size": 7, "swap": True},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.size = max(3, min(11, int(self.variant.get("size", 7))))
        self.swap_rule = bool(self.variant.get("swap", False))
        self.label = str(self.variant.get("label", f"{self.size}x{self.size}"))

        self.board: list[list[int | None]] = [[None] * self.size for _ in range(self.size)]  # [row][col]
        self.current = 0
        self.moves = 0
        self.history: list[dict] = []
        self.last: dict | None = None
        self.swapped = False
        self.win_path: list[list[int]] = []
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _neighbours(self, r: int, c: int) -> list[tuple[int, int]]:
        candidates = [
            (r, c - 1),
            (r, c + 1),
            (r - 1, c),
            (r - 1, c + 1),
            (r + 1, c - 1),
            (r + 1, c),
        ]
        return [(nr, nc) for nr, nc in candidates if 0 <= nr < self.size and 0 <= nc < self.size]

    def _check_win(self, seat: int) -> list[list[int]]:
        """BFS to check if `seat` has an unbroken path connecting their edges."""
        # Seat 0 connects row 0 to row size-1
        # Seat 1 connects col 0 to col size-1
        queue = collections.deque()
        visited = set()
        parent: dict[tuple[int, int], tuple[int, int] | None] = {}

        if seat == 0:
            for c in range(self.size):
                if self.board[0][c] == 0:
                    queue.append((0, c))
                    visited.add((0, c))
                    parent[(0, c)] = None
        else:
            for r in range(self.size):
                if self.board[r][0] == 1:
                    queue.append((r, 0))
                    visited.add((r, 0))
                    parent[(r, 0)] = None

        goal_node = None
        while queue:
            r, c = queue.popleft()
            if (seat == 0 and r == self.size - 1) or (seat == 1 and c == self.size - 1):
                goal_node = (r, c)
                break
            for nr, nc in self._neighbours(r, c):
                if (nr, nc) not in visited and self.board[nr][nc] == seat:
                    visited.add((nr, nc))
                    parent[(nr, nc)] = (r, c)
                    queue.append((nr, nc))

        if not goal_node:
            return []

        path = []
        curr = goal_node
        while curr:
            path.append([curr[0], curr[1]])
            curr = parent[curr]
        path.reverse()
        return path

    def rules(self) -> str:
        n = self.size
        last_col = chr(ord("a") + n - 1)
        swap_desc = " The swap rule is in effect: on move 2, Player 1 may choose to swap colors instead of placing a stone." if self.swap_rule else ""
        return f"""HEX - {self.label} board.{swap_desc}

BOARD
The board is a rhombus (diamond) of {n}x{n} = {n * n} hexagonal cells. Columns are letters a..{last_col}
from left to right, rows are numbers 1..{n} from top to bottom; a cell is letter + number, e.g. c3.
Because the cells are hexagons, every row is shifted half a cell to the right of the row above, and
each cell touches up to 6 neighbours.

PLAYERS AND GOAL
Player 0 plays X and must connect the TOP edge (row 1) to the BOTTOM edge (row {n}) with an unbroken
chain of touching X stones. Player 1 plays O and must connect the LEFT edge (column a) to the RIGHT
edge (column {last_col}) with a chain of touching O stones. The first player to complete a chain wins.

TURN ORDER
Player 0 (X) moves first; then the players alternate. On your turn you place one stone of your
symbol on any empty cell. Stones never move and are never removed. Passing is not allowed.

ACTION FORMAT
    place <cell>
Examples:  "place c3"   "place a1"   "place {last_col}{n}"
Placing on an occupied cell, a cell outside the board or any other text is illegal (first time: a
warning and the same turn again; second time: you lose the game). The arena sends the complete list
of legal moves every turn.

WHAT YOU OBSERVE
The board drawn as a slanted grid, "." = empty, the move history and whose turn it is.

HOW THE GAME ENDS AND IS SCORED
The game ends as soon as one player completes a chain between their two edges: that player wins
(score 1, loser 0). A draw is impossible in Hex: when the board is full one player always has a
chain, so the game lasts at most {n * n} moves (the move cap).
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        moves = []
        if self.swap_rule and self.moves == 1 and not self.swapped:
            moves.append("swap")
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] is None:
                    moves.append(f"place {chr(ord('a') + c)}{r + 1}")
        return self.cap_list(moves)

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        c_act = self.clean(action)
        if c_act == "swap":
            if self.swap_rule and self.moves == 1 and not self.swapped:
                return "swap"
            return None
        m = _PLACE_RE.match(c_act)
        if not m:
            return None
        c = ord(m.group(1).lower()) - ord("a")
        r = int(m.group(2)) - 1
        if 0 <= r < self.size and 0 <= c < self.size and self.board[r][c] is None:
            return f"place {chr(ord('a') + c)}{r + 1}"
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        if norm == "swap":
            # Swap: seat 1 takes over seat 0's move (transposing it)
            self.swapped = True
            # Find stone placed in move 0
            prev = self.history[0]
            old_r, old_c = prev["r"], prev["c"]
            self.board[old_r][old_c] = None
            # Place at transposed position for seat 1
            new_r, new_c = old_c, old_r
            self.board[new_r][new_c] = 1
            self.moves += 1
            rec = {"seat": self.current, "action": "swap", "r": new_r, "c": new_c, "swap": True}
            self.history.append(rec)
            self.last = rec
            self.current = 1 - self.current
            return

        m = _PLACE_RE.match(norm)
        c = ord(m.group(1).lower()) - ord("a")
        r = int(m.group(2)) - 1
        self.board[r][c] = self.current
        self.moves += 1

        rec = {"seat": self.current, "action": norm, "r": r, "c": c, "swap": False}
        self.history.append(rec)
        self.last = rec

        # Check win
        path = self._check_win(self.current)
        if path:
            self.over = True
            self.winner = self.current
            self.win_path = path
            self.end_reason = f"seat {self.current} connected their edges with a chain of {len(path)} stones"
        elif self.moves >= self.size * self.size:
            # Full board: Hex theorem ensures one player must have won
            self.over = True
            p0 = self._check_win(0)
            if p0:
                self.winner = 0
                self.win_path = p0
                self.end_reason = "seat 0 completed a chain on the full board"
            else:
                self.winner = 1
                self.win_path = self._check_win(1)
                self.end_reason = "seat 1 completed a chain on the full board"
        else:
            self.current = 1 - self.current

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        sym = "X" if seat == 0 else "O"
        lines = [
            f"HEX ({self.label}). You are Player {seat} ('{sym}').",
            f"Your goal: connect {'TOP to BOTTOM' if seat == 0 else 'LEFT to RIGHT'} with an unbroken chain.",
            f"Current turn: Player {self.current} (move {self.moves + 1}).",
            "",
            "Board:",
            "  " + " ".join(chr(ord("a") + c) for c in range(self.size)) + "        (X joins top<->bottom, O joins left<->right)",
        ]
        mark = {0: "X", 1: "O", None: "."}
        for r in range(self.size):
            indent = " " * (r + 1)
            row_cells = " ".join(mark[self.board[r][c]] for c in range(self.size))
            lines.append(f"{indent}{r + 1:>2}  {row_cells}  {r + 1}")
        lines.append(" " * (self.size + 3) + " ".join(chr(ord("a") + c) for c in range(self.size)))

        if self.history:
            lines.append("")
            lines.append(f"Last move: Player {self.history[-1]['seat']} played {self.history[-1]['action']}.")
        return "\n".join(lines)

    def result(self) -> dict:
        scores = [0, 0]
        if self.winner is not None:
            scores[self.winner] = 1
        return {
            "winner": self.winner,
            "scores": scores,
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "size": self.size,
            "swap_rule": self.swap_rule,
            "swapped": self.swapped,
            "board": [list(row) for row in self.board],
            "history": list(self.history),
            "last": self.last,
            "win_path": list(self.win_path),
            "moves": self.moves,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
