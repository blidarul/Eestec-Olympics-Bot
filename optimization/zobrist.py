"""64-bit Zobrist Hashing for O(1) State Lookups and Incremental Search Updates.
Provides high-speed bitwise XOR hashing to replace string-based keys in transposition tables,
drastically reducing garbage collection pauses and boosting minimax / MCTS expansions per second.
Owned by agent `bld`.
"""
from __future__ import annotations

import random
from typing import Any


class ZobristHasher:
    """64-bit Zobrist hash table for grid and discrete state representations."""
    __slots__ = ("num_cells", "num_pieces", "table", "turn_keys", "var_table")

    def __init__(self, num_cells: int = 64, num_pieces: int = 4, seed: int = 0x88888888):
        self.num_cells = num_cells
        self.num_pieces = num_pieces
        rng = random.Random(seed)

        # 64-bit unsigned integers: 0 to 2^64 - 1
        mask64 = (1 << 64) - 1
        self.table = [
            [rng.getrandbits(64) & mask64 for _ in range(num_pieces)]
            for _ in range(num_cells)
        ]
        # Hash keys for seat / turn (player 0 vs player 1)
        self.turn_keys = [rng.getrandbits(64) & mask64, rng.getrandbits(64) & mask64]
        # Hash keys for common integer state variables (e.g. scores, rounds up to 256)
        self.var_table = [rng.getrandbits(64) & mask64 for _ in range(512)]

    def hash_cell(self, cell_idx: int, piece: int) -> int:
        """Get the random 64-bit key for a cell and piece."""
        if 0 <= cell_idx < self.num_cells and 0 <= piece < self.num_pieces:
            return self.table[cell_idx][piece]
        return 0

    def toggle_cell(self, current_hash: int, cell_idx: int, piece: int) -> int:
        """XOR toggle a piece on a cell. Applying twice cancels out (O(1) in-place undo)."""
        key = self.hash_cell(cell_idx, piece)
        return current_hash ^ key

    def toggle_turn(self, current_hash: int) -> int:
        """Toggle player to move in the hash."""
        return current_hash ^ self.turn_keys[0] ^ self.turn_keys[1]

    def hash_scalar(self, val: int) -> int:
        """Hash a discrete integer scalar (e.g. banked points, round number)."""
        idx = max(0, min(len(self.var_table) - 1, int(val)))
        return self.var_table[idx]

    def hash_grid(self, grid: list[int | None], current_player: int = 0) -> int:
        """Compute full 64-bit Zobrist hash of an entire grid state."""
        h = self.turn_keys[current_player % 2]
        for idx, piece in enumerate(grid):
            if piece is not None and idx < self.num_cells:
                h ^= self.table[idx][piece % self.num_pieces]
        return h
