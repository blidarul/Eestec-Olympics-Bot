"""High-Performance Search Data Structures.
Fast state representation (bitboards, flat grid arrays with __slots__, in-place undo) to maximize
minimax / MCTS node expansion throughput within the 20s move window.
Owned by agent `bld`.
"""
from __future__ import annotations

from typing import Any


class BitBoard:
    """64-bit integer bitboard representation for grid boards up to 8x8."""
    __slots__ = ("mask", "size")

    def __init__(self, size: int = 3, mask: int = 0):
        self.size = size
        self.mask = mask

    def set_cell(self, r: int, c: int) -> BitBoard:
        bit = 1 << (r * self.size + c)
        return BitBoard(self.size, self.mask | bit)

    def set_cell_inplace(self, r: int, c: int) -> None:
        self.mask |= (1 << (r * self.size + c))

    def clear_cell_inplace(self, r: int, c: int) -> None:
        self.mask &= ~(1 << (r * self.size + c))

    def has_cell(self, r: int, c: int) -> bool:
        return bool(self.mask & (1 << (r * self.size + c)))

    def is_line(self, k: int) -> bool:
        """Check if mask contains k marks in a straight row, column, or diagonal."""
        s = self.size
        # Rows
        for r in range(s):
            consec = 0
            for c in range(s):
                if self.mask & (1 << (r * s + c)):
                    consec += 1
                    if consec >= k:
                        return True
                else:
                    consec = 0

        # Columns
        for c in range(s):
            consec = 0
            for r in range(s):
                if self.mask & (1 << (r * s + c)):
                    consec += 1
                    if consec >= k:
                        return True
                else:
                    consec = 0

        # Diagonals (down-right and down-left)
        for r in range(s):
            for c in range(s):
                # Down-right
                if r + k <= s and c + k <= s:
                    if all(self.mask & (1 << ((r + i) * s + (c + i))) for i in range(k)):
                        return True
                # Down-left
                if r + k <= s and c - k + 1 >= 0:
                    if all(self.mask & (1 << ((r + i) * s + (c - i))) for i in range(k)):
                        return True

        return False


class FastGrid:
    """Zero-allocation grid with in-place move/undo and history stack for minimax search."""
    __slots__ = ("size", "cells", "history")

    def __init__(self, size: int = 3):
        self.size = size
        self.cells: list[int | None] = [None] * (size * size)
        self.history: list[int] = []

    def get(self, r: int, c: int) -> int | None:
        return self.cells[r * self.size + c]

    def set(self, r: int, c: int, val: int | None) -> None:
        self.cells[r * self.size + c] = val

    def make_move(self, r: int, c: int, player: int) -> None:
        idx = r * self.size + c
        self.cells[idx] = player
        self.history.append(idx)

    def undo_move(self) -> int | None:
        if not self.history:
            return None
        idx = self.history.pop()
        self.cells[idx] = None
        return idx

    def empty_cells(self) -> list[tuple[int, int]]:
        s = self.size
        return [(i // s, i % s) for i, val in enumerate(self.cells) if val is None]
