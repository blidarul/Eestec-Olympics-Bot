"""High-Performance Search Data Structures.
Fast state representation (bitboards with symmetries, flat grid arrays with __slots__,
and bounded transposition table) to maximize minimax / MCTS node expansion throughput.
Owned by agent `bld`.
"""
from __future__ import annotations

from typing import Any

# Transposition table entry flags for alpha-beta search
TT_EXACT = 0
TT_LOWERBOUND = 1
TT_UPPERBOUND = 2


class BitBoard:
    """64-bit integer bitboard representation for grid boards up to 8x8 with symmetry hashing."""
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

    def rotate90(self) -> BitBoard:
        """Rotate grid 90 degrees clockwise."""
        s = self.size
        new_mask = 0
        for r in range(s):
            for c in range(s):
                if self.mask & (1 << (r * s + c)):
                    # (r, c) -> (c, s - 1 - r)
                    new_mask |= (1 << (c * s + (s - 1 - r)))
        return BitBoard(s, new_mask)

    def flip_h(self) -> BitBoard:
        """Horizontal reflection (flip across vertical axis)."""
        s = self.size
        new_mask = 0
        for r in range(s):
            for c in range(s):
                if self.mask & (1 << (r * s + c)):
                    # (r, c) -> (r, s - 1 - c)
                    new_mask |= (1 << (r * s + (s - 1 - c)))
        return BitBoard(s, new_mask)

    def canonical_mask(self) -> int:
        """Return the minimum integer representation across all 8 D4 dihedral symmetries.
        Allows exact 8x transposition reduction for square board games.
        """
        b0 = self
        b1 = b0.rotate90()
        b2 = b1.rotate90()
        b3 = b2.rotate90()

        f0 = b0.flip_h()
        f1 = b1.flip_h()
        f2 = b2.flip_h()
        f3 = b3.flip_h()

        return min(
            b0.mask, b1.mask, b2.mask, b3.mask,
            f0.mask, f1.mask, f2.mask, f3.mask,
        )

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


class TranspositionTable:
    """Fixed-capacity, bounded memory transposition table for minimax with alpha-beta pruning."""
    __slots__ = ("capacity", "table")

    def __init__(self, capacity: int = 131072):
        self.capacity = capacity
        # Mapping: key -> (depth, value, flag, best_action)
        self.table: dict[Any, tuple[int, float, int, Any]] = {}

    def store(self, key: Any, depth: int, value: float, flag: int, best_action: Any = None) -> None:
        # Bounded replacement to respect container memory limits
        if len(self.table) >= self.capacity and key not in self.table:
            # Drop an arbitrary key if capacity reached
            self.table.pop(next(iter(self.table)))
        self.table[key] = (depth, value, flag, best_action)

    def lookup(
        self,
        key: Any,
        depth: int,
        alpha: float,
        beta: float,
    ) -> tuple[float | None, Any | None]:
        """Look up value from TT. Returns (score, best_action) if usable, else (None, best_action)."""
        entry = self.table.get(key)
        if entry is None:
            return None, None

        tt_depth, tt_value, tt_flag, tt_action = entry
        if tt_depth >= depth:
            if tt_flag == TT_EXACT:
                return tt_value, tt_action
            elif tt_flag == TT_LOWERBOUND and tt_value >= beta:
                return tt_value, tt_action
            elif tt_flag == TT_UPPERBOUND and tt_value <= alpha:
                return tt_value, tt_action

        return None, tt_action

    def clear(self) -> None:
        self.table.clear()
