"""Unit tests for optimization/zobrist.py.
Verifies 64-bit Zobrist hashing, XOR incremental updates, and FastGrid integration.
Owned by agent `bld`.
"""
import unittest

from optimization.structures import FastGrid
from optimization.zobrist import ZobristHasher


class TestZobrist(unittest.TestCase):
    def test_zobrist_hash_consistency(self):
        hasher = ZobristHasher(num_cells=9, num_pieces=2, seed=12345)
        grid = [None] * 9
        grid[0] = 0  # player 0 at cell 0
        grid[4] = 1  # player 1 at cell 4

        full_hash = hasher.hash_grid(grid, current_player=0)
        self.assertIsInstance(full_hash, int)
        self.assertGreater(full_hash, 0)

        # Build incrementally using toggle_cell
        h = hasher.turn_keys[0]
        h = hasher.toggle_cell(h, cell_idx=0, piece=0)
        h = hasher.toggle_cell(h, cell_idx=4, piece=1)

        self.assertEqual(full_hash, h)

    def test_zobrist_xor_reversibility(self):
        hasher = ZobristHasher(num_cells=9, num_pieces=2)
        base = 123456789
        toggled = hasher.toggle_cell(base, cell_idx=3, piece=1)
        self.assertNotEqual(base, toggled)

        # Applying toggle again must return exact original hash
        restored = hasher.toggle_cell(toggled, cell_idx=3, piece=1)
        self.assertEqual(base, restored)

    def test_fast_grid_incremental_zobrist(self):
        hasher = ZobristHasher(num_cells=9, num_pieces=2)
        fg = FastGrid(size=3, hasher=hasher)
        initial_hash = fg.zobrist_hash

        fg.make_move(1, 1, player=0)
        move_hash = fg.zobrist_hash
        self.assertNotEqual(initial_hash, move_hash)

        fg.undo_move()
        self.assertEqual(fg.zobrist_hash, initial_hash)

    def test_collision_resistance(self):
        import random
        hasher = ZobristHasher(num_cells=9, num_pieces=2)
        rng = random.Random(999)
        unique_states = set()
        hashes = set()

        for _ in range(1000):
            grid = tuple(rng.choice([None, 0, 1]) for _ in range(9))
            player = rng.randint(0, 1)
            state_key = (grid, player)
            if state_key not in unique_states:
                unique_states.add(state_key)
                h = hasher.hash_grid(list(grid), current_player=player)
                hashes.add(h)

        self.assertEqual(len(hashes), len(unique_states))


if __name__ == "__main__":
    unittest.main()
