"""Mini Chess: simplified chess on small boards (Gardner 5x5, Los Alamos 6x6)."""
from __future__ import annotations

import re

from ..core import Game

_MOVE_RE = re.compile(r"^(?:[kqrbnpKQRBNP])?([a-h])([1-8])[-\s]?([a-h])([1-8])(?:[qQ])?$", re.IGNORECASE)

PIECE_VALUES = {
    "q": 9, "r": 5, "b": 3, "n": 3, "p": 1,
    "Q": 9, "R": 5, "B": 3, "N": 3, "P": 1,
}

SETUPS = {
    "gardner": {
        "size": 5,
        "board": [
            "rnbqk",
            "ppppp",
            ".....",
            "PPPPP",
            "RNBQK",
        ],
    },
    "los_alamos": {
        "size": 6,
        "board": [
            "rnqknr",
            "pppppp",
            "......",
            "......",
            "PPPPPP",
            "RNQKNR",
        ],
    },
}


class MiniChess(Game):
    id = "mini_chess"
    name = "Mini Chess"
    category = "think"
    blurb = "Chess stripped to pure combat: no castles, no waiting, every piece in contact on move one."
    howto = "Play chess on a 5x5 (Gardner) or 6x6 (Los Alamos) board. No double-step pawns, no castling, auto-queen promotions. Checkmate the enemy king to win."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "Gardner 5x5", "setup": "gardner", "max_moves": 40},
            {"label": "Los Alamos 6x6", "setup": "los_alamos", "max_moves": 50},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "Gardner 5x5"))
        self.setup = str(self.variant.get("setup", "gardner"))
        cfg = SETUPS.get(self.setup, SETUPS["gardner"])
        self.size = cfg["size"]
        # Board stored as list of lists of chars [row 0 (top/black) .. row size-1 (bottom/white)]
        self.grid = [list(row) for row in cfg["board"]]
        self.max_moves = int(self.variant.get("max_moves", 40))
        self.max_plies = self.max_moves * 2

        self.side = 0  # 0 = White, 1 = Black
        self.ply = 0
        self.moves: list[dict] = []
        self.last: dict | None = None
        self.captured: list[list[str]] = [[], []]
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _is_white(self, ch: str) -> bool:
        return ch.isupper()

    def _is_black(self, ch: str) -> bool:
        return ch.islower()

    def _side_owns(self, ch: str, side: int) -> bool:
        if ch == ".":
            return False
        return self._is_white(ch) if side == 0 else self._is_black(ch)

    def _find_king(self, grid: list[list[str]], side: int) -> tuple[int, int] | None:
        target = "K" if side == 0 else "k"
        for r in range(self.size):
            for c in range(self.size):
                if grid[r][c] == target:
                    return r, c
        return None

    def _is_attacked(self, grid: list[list[str]], r: int, c: int, by_side: int) -> bool:
        """Is cell (r, c) attacked by by_side?"""
        p_dir = -1 if by_side == 0 else 1  # White moves up (r decreases), Black moves down (r increases)
        # Pawn attacks
        p_char = "P" if by_side == 0 else "p"
        for dc in (-1, 1):
            pr, pc = r - p_dir, c + dc
            if 0 <= pr < self.size and 0 <= pc < self.size and grid[pr][pc] == p_char:
                return True

        # Knight attacks
        n_char = "N" if by_side == 0 else "n"
        for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.size and 0 <= nc < self.size and grid[nr][nc] == n_char:
                return True

        # King attacks
        k_char = "K" if by_side == 0 else "k"
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                kr, kc = r + dr, c + dc
                if 0 <= kr < self.size and 0 <= kc < self.size and grid[kr][kc] == k_char:
                    return True

        # Sliding pieces: R/Q straight
        rq_chars = ("R", "Q") if by_side == 0 else ("r", "q")
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            curr_r, curr_c = r + dr, c + dc
            while 0 <= curr_r < self.size and 0 <= curr_c < self.size:
                ch = grid[curr_r][curr_c]
                if ch != ".":
                    if ch in rq_chars:
                        return True
                    break
                curr_r += dr
                curr_c += dc

        # Sliding pieces: B/Q diagonal
        bq_chars = ("B", "Q") if by_side == 0 else ("b", "q")
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            curr_r, curr_c = r + dr, c + dc
            while 0 <= curr_r < self.size and 0 <= curr_c < self.size:
                ch = grid[curr_r][curr_c]
                if ch != ".":
                    if ch in bq_chars:
                        return True
                    break
                curr_r += dr
                curr_c += dc

        return False

    def _pseudo_legal_moves(self, grid: list[list[str]], side: int) -> list[tuple[int, int, int, int]]:
        moves = []
        p_dir = -1 if side == 0 else 1
        last_row = 0 if side == 0 else self.size - 1

        for r in range(self.size):
            for c in range(self.size):
                piece = grid[r][c]
                if not self._side_owns(piece, side):
                    continue
                p_lower = piece.lower()

                if p_lower == "p":
                    # Forward 1
                    fr = r + p_dir
                    if 0 <= fr < self.size and grid[fr][c] == ".":
                        moves.append((r, c, fr, c))
                    # Diagonal captures
                    for dc in (-1, 1):
                        fc = c + dc
                        if 0 <= fr < self.size and 0 <= fc < self.size:
                            target = grid[fr][fc]
                            if target != "." and not self._side_owns(target, side):
                                moves.append((r, c, fr, fc))

                elif p_lower == "n":
                    for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.size and 0 <= nc < self.size:
                            if not self._side_owns(grid[nr][nc], side):
                                moves.append((r, c, nr, nc))

                elif p_lower == "k":
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            if dr == 0 and dc == 0:
                                continue
                            kr, kc = r + dr, c + dc
                            if 0 <= kr < self.size and 0 <= kc < self.size:
                                if not self._side_owns(grid[kr][kc], side):
                                    moves.append((r, c, kr, kc))

                elif p_lower in ("r", "b", "q"):
                    dirs = []
                    if p_lower in ("r", "q"):
                        dirs.extend([(-1, 0), (1, 0), (0, -1), (0, 1)])
                    if p_lower in ("b", "q"):
                        dirs.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])
                    for dr, dc in dirs:
                        curr_r, curr_c = r + dr, c + dc
                        while 0 <= curr_r < self.size and 0 <= curr_c < self.size:
                            target = grid[curr_r][curr_c]
                            if target == ".":
                                moves.append((r, c, curr_r, curr_c))
                            elif not self._side_owns(target, side):
                                moves.append((r, c, curr_r, curr_c))
                                break
                            else:
                                break
                            curr_r += dr
                            curr_c += dc
        return moves

    def _legal_moves_for_side(self, side: int) -> list[str]:
        pseudo = self._pseudo_legal_moves(self.grid, side)
        legal = []
        last_row = 0 if side == 0 else self.size - 1

        for r1, c1, r2, c2 in pseudo:
            # Simulate move
            saved_from = self.grid[r1][c1]
            saved_to = self.grid[r2][c2]

            # Move
            moving_piece = saved_from
            if moving_piece.lower() == "p" and r2 == last_row:
                moving_piece = "Q" if side == 0 else "q"

            self.grid[r1][c1] = "."
            self.grid[r2][c2] = moving_piece

            # Check if own king is in check
            k_pos = self._find_king(self.grid, side)
            in_check = False
            if k_pos is not None:
                in_check = self._is_attacked(self.grid, k_pos[0], k_pos[1], 1 - side)

            # Undo
            self.grid[r1][c1] = saved_from
            self.grid[r2][c2] = saved_to

            if not in_check:
                sq1 = f"{chr(ord('a') + c1)}{self.size - r1}"
                sq2 = f"{chr(ord('a') + c2)}{self.size - r2}"
                legal.append(f"{sq1}{sq2}")
        return sorted(legal)

    def _in_check(self, side: int) -> bool:
        k_pos = self._find_king(self.grid, side)
        if k_pos is None:
            return False
        return self._is_attacked(self.grid, k_pos[0], k_pos[1], 1 - side)

    def _material(self) -> list[int]:
        m = [0, 0]
        for r in range(self.size):
            for c in range(self.size):
                ch = self.grid[r][c]
                if ch in PIECE_VALUES:
                    m[0 if ch.isupper() else 1] += PIECE_VALUES[ch]
        return m

    def rules(self) -> str:
        last_col = chr(ord("a") + self.size - 1)
        return f"""MINI CHESS - {self.label} ({self.size}x{self.size} board).

OVERVIEW
Chess on a small {self.size}x{self.size} board with simplified rules. Player 0 is WHITE (uppercase letters) and moves
first; Player 1 is BLACK (lowercase letters). Players alternate, one move per turn; passing is not allowed.

BOARD AND COORDINATES
Files (columns) are letters a..{last_col}; ranks (rows) are numbers 1..{self.size}. A square is file + rank, e.g. "c3".
Starting position: rank {self.size} at top (Black), rank 1 at bottom (White).

SIMPLIFICATIONS
No castling, no en passant, NO pawn double step, auto-promotion to QUEEN on the last rank.

CHECK AND CHECKMATE
A move that leaves your own king in check is illegal. Checkmate wins; stalemate is a draw.

ACTION FORMAT
    <from-square><to-square>
Examples:  "b2b3"   "b1c3"   "c3d4"   "a4a5" (or "a4a5q").
Legal actions list is sent when at most 50 moves exist.

HOW THE GAME ENDS AND IS SCORED
- Checkmate: side that delivered mate wins (score 1, loser 0).
- Stalemate: draw (0.5 each).
- MOVE CAP: after {self.max_moves} moves each ({self.max_plies} plies), player with more material wins (Q:9, R:5, B:3, N:3, P:1); equal = draw.
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.side]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.side:
            return []
        moves = self._legal_moves_for_side(self.side)
        return self.cap_list(moves)

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.side:
            return None
        m = _MOVE_RE.match(self.clean(action))
        if not m:
            return None
        sq1 = f"{m.group(1).lower()}{m.group(2)}"
        sq2 = f"{m.group(3).lower()}{m.group(4)}"
        move_str = f"{sq1}{sq2}"
        legal = self._legal_moves_for_side(self.side)
        if move_str in legal:
            return move_str
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.side)
        if not act:
            return
        norm = self.normalize(self.side, act)
        if not norm:
            return

        c1 = ord(norm[0]) - ord("a")
        r1 = self.size - int(norm[1])
        c2 = ord(norm[2]) - ord("a")
        r2 = self.size - int(norm[3])

        piece = self.grid[r1][c1]
        target = self.grid[r2][c2]
        if target != ".":
            self.captured[self.side].append(target)

        # Move piece
        last_row = 0 if self.side == 0 else self.size - 1
        if piece.lower() == "p" and r2 == last_row:
            piece = "Q" if self.side == 0 else "q"

        self.grid[r1][c1] = "."
        self.grid[r2][c2] = piece
        self.ply += 1

        rec = {"side": self.side, "action": norm, "piece": piece, "from": [r1, c1], "to": [r2, c2]}
        self.moves.append(rec)
        self.last = rec

        # Check opponent status
        next_side = 1 - self.side
        next_legal = self._legal_moves_for_side(next_side)
        in_check = self._in_check(next_side)

        if not next_legal:
            self.over = True
            if in_check:
                self.winner = self.side
                self.end_reason = f"seat {self.side} delivered checkmate"
            else:
                self.winner = None
                self.end_reason = "stalemate (draw)"
        elif self.ply >= self.max_plies:
            self.over = True
            mat = self._material()
            if mat[0] > mat[1]:
                self.winner = 0
                self.end_reason = f"move cap reached; seat 0 won on material ({mat[0]} vs {mat[1]})"
            elif mat[1] > mat[0]:
                self.winner = 1
                self.end_reason = f"move cap reached; seat 1 won on material ({mat[1]} vs {mat[0]})"
            else:
                self.winner = None
                self.end_reason = f"move cap reached; material equal ({mat[0]}-{mat[1]}, draw)"
        else:
            self.side = next_side

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        color = "WHITE" if seat == 0 else "BLACK"
        turn_color = "WHITE" if self.side == 0 else "BLACK"
        mat = self._material()
        lines = [
            f"MINI CHESS ({self.label}). You are {color} (Player {seat}).",
            f"Turn: {turn_color} to move (ply {self.ply + 1} of {self.max_plies}). Material: White {mat[0]}, Black {mat[1]}.",
            f"Check status: {'IN CHECK!' if self._in_check(self.side) else 'not in check'}.",
            "",
            "   " + " ".join(chr(ord("a") + c) for c in range(self.size)),
        ]
        for r in range(self.size):
            rank_num = self.size - r
            row_str = " ".join(self.grid[r])
            lines.append(f"{rank_num:>2} {row_str} {rank_num}")
        lines.append("   " + " ".join(chr(ord("a") + c) for c in range(self.size)))

        if self.last:
            lines.append(f"\nLast move: {'White' if self.last['side'] == 0 else 'Black'} played {self.last['action']}.")
        return "\n".join(lines)

    def result(self) -> dict:
        scores = [0, 0]
        if self.winner is not None:
            scores[self.winner] = 1
        elif self.over:
            scores = [0.5, 0.5]
        return {
            "winner": self.winner,
            "scores": scores,
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        k_pos = self._find_king(self.grid, self.side)
        check_sq = f"{chr(ord('a') + k_pos[1])}{self.size - k_pos[0]}" if (self._in_check(self.side) and k_pos) else None
        return {
            "size": self.size,
            "setup": self.setup,
            "board": ["".join(row) for row in self.grid],
            "side": self.side,
            "check": self._in_check(self.side),
            "check_square": check_sq,
            "last": self.last,
            "moves": list(self.moves),
            "captured": [list(c) for c in self.captured],
            "material": self._material(),
            "ply": self.ply,
            "max_plies": self.max_plies,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
