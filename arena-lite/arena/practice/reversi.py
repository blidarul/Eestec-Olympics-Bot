"""Reversi / Othello 6x6 (Think Ahead Family): line-trapping and directional stone-flipping board game."""
from __future__ import annotations

import re

from ..core import Game

_PLACE_RE = re.compile(r"^(?:place\s+)?([a-f])([1-6])$", re.IGNORECASE)
DIRECTIONS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


class Reversi(Game):
    id = "reversi"
    name = "Reversi"
    category = "think"
    blurb = "6x6 Othello board tactics: bracket enemy lines, flip their pieces, and dominate the board."
    howto = "Players take turns placing stones (X for Player 0, O for Player 1) on a 6x6 grid. A move must bracket one or more enemy stones in a straight line, flipping them to your color. If no move is possible, pass. Most stones wins."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "6x6 standard", "size": 6},
            {"label": "6x6 corner handicap", "size": 6, "handicap": True},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "6x6 standard"))
        self.size = 6
        self.handicap = bool(self.variant.get("handicap", False))

        self.board: list[list[int | None]] = [[None] * self.size for _ in range(self.size)]
        # Center initial stones:
        # Row 2, Col 2 = O (1), Row 2, Col 3 = X (0)
        # Row 3, Col 2 = X (0), Row 3, Col 3 = O (1)
        self.board[2][2] = 1
        self.board[2][3] = 0
        self.board[3][2] = 0
        self.board[3][3] = 1

        self.current = 0  # 0 plays X, 1 plays O
        self.moves = 0
        self.consecutive_passes = 0
        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _flips_in_direction(self, r: int, c: int, dr: int, dc: int, seat: int) -> list[tuple[int, int]]:
        opp = 1 - seat
        curr_r, curr_c = r + dr, c + dc
        flips = []
        while 0 <= curr_r < self.size and 0 <= curr_c < self.size and self.board[curr_r][curr_c] == opp:
            flips.append((curr_r, curr_c))
            curr_r += dr
            curr_c += dc
        if 0 <= curr_r < self.size and 0 <= curr_c < self.size and self.board[curr_r][curr_c] == seat and flips:
            return flips
        return []

    def _all_flips(self, r: int, c: int, seat: int) -> list[tuple[int, int]]:
        if self.board[r][c] is not None:
            return []
        flips = []
        for dr, dc in DIRECTIONS:
            flips.extend(self._flips_in_direction(r, c, dr, dc, seat))
        return flips

    def _get_legal_moves(self, seat: int) -> list[str]:
        moves = []
        for r in range(self.size):
            for c in range(self.size):
                if self._all_flips(r, c, seat):
                    cell = f"{chr(ord('a') + c)}{r + 1}"
                    moves.append(f"place {cell}")
        if not moves:
            moves.append("pass")
        return sorted(moves)

    def _counts(self) -> list[int]:
        c0 = sum(row.count(0) for row in self.board)
        c1 = sum(row.count(1) for row in self.board)
        return [c0, c1]

    def rules(self) -> str:
        return f"""REVERSI / OTHELLO - {self.label} (6x6 board).

GOAL
Finish with more stones of your color than your opponent.
Player 0 plays X (moves first); Player 1 plays O.

PLACEMENT & FLIPPING RULES
On your turn, place a stone on an empty cell so that you TRAP one or more enemy stones in a straight
line (horizontal, vertical, or diagonal) between the new stone and an existing stone of your color.
All trapped enemy stones are flipped to your color.
If you have legal moves, you MUST make one. You may only "pass" if you have NO legal placement moves.

END OF GAME
The game ends when the board is full, or when neither player has a legal move (two consecutive passes).
The player with more stones wins!

ACTION FORMAT
    place <cell>   OR   pass
Examples: "place c4", "place d2", "pass".
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        return self._get_legal_moves(seat)

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        c = self.clean(action)
        legal = self._get_legal_moves(seat)
        if c == "pass" and "pass" in legal:
            return "pass"
        m = _PLACE_RE.match(c)
        if not m:
            return None
        formatted = f"place {m.group(1).lower()}{m.group(2)}"
        if formatted in legal:
            return formatted
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

        if norm == "pass":
            self.consecutive_passes += 1
            rec = {"seat": self.current, "action": "pass", "flips": 0}
            self.history.append(rec)
            self.last = rec
        else:
            self.consecutive_passes = 0
            m = _PLACE_RE.match(norm)
            c = ord(m.group(1).lower()) - ord("a")
            r = int(m.group(2)) - 1
            flips = self._all_flips(r, c, self.current)
            self.board[r][c] = self.current
            for fr, fc in flips:
                self.board[fr][fc] = self.current
            self.moves += 1
            rec = {"seat": self.current, "action": norm, "flips": len(flips)}
            self.history.append(rec)
            self.last = rec

        # Check end condition
        counts = self._counts()
        board_full = sum(counts) == self.size * self.size
        both_passed = self.consecutive_passes >= 2

        if board_full or both_passed or counts[0] == 0 or counts[1] == 0:
            self.over = True
            if counts[0] > counts[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won {counts[0]} to {counts[1]} stones"
            elif counts[1] > counts[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won {counts[1]} to {counts[0]} stones"
            else:
                self.winner = None
                self.end_reason = f"draw {counts[0]} to {counts[1]} stones"
        else:
            self.current = 1 - self.current

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        counts = self._counts()
        sym = "X" if seat == 0 else "O"
        lines = [
            f"REVERSI ({self.label}). You are Player {seat} ('{sym}').",
            f"Turn: Player {self.current} (move {self.moves + 1}). Scores: X (Player 0) = {counts[0]}, O (Player 1) = {counts[1]}.",
            "",
            "   " + " ".join(chr(ord("a") + c) for c in range(self.size)),
        ]
        mark = {0: "X", 1: "O", None: "."}
        for r in range(self.size):
            row_cells = " ".join(mark[self.board[r][c]] for c in range(self.size))
            lines.append(f"{r + 1:>2} {row_cells} {r + 1}")
        lines.append("   " + " ".join(chr(ord("a") + c) for c in range(self.size)))

        if self.last:
            lines.append(f"\nLast move: Player {self.last['seat']} played {self.last['action']} (flipped {self.last.get('flips', 0)} stones).")
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": self._counts(),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "size": self.size,
            "board": [list(row) for row in self.board],
            "counts": self._counts(),
            "moves": self.moves,
            "to_move": self.to_move(),
            "history": list(self.history),
            "last": self.last,
            "over": self.over,
            "result": self.result() if self.over else None,
        }
