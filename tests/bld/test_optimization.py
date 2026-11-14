"""Unit tests for optimization modules (budget, structures, profiler).
Owned by agent `bld`.
"""
import time
import unittest

from optimization.budget import (
    TimeBudget,
    check_memory_budget,
    get_memory_rss_mb,
    pause_gc,
)
from optimization.profiler import (
    benchmark_throughput,
    profile_memory_delta,
    time_execution,
)
from optimization.structures import (
    BitBoard,
    FastGrid,
    TT_EXACT,
    TranspositionTable,
)


class TestOptimization(unittest.TestCase):
    def test_memory_budget(self):
        rss = get_memory_rss_mb()
        self.assertGreaterEqual(rss, 0.0)
        self.assertTrue(check_memory_budget(limit_mb=1800.0))

    def test_pause_gc(self):
        with pause_gc():
            x = [i for i in range(1000)]
        self.assertEqual(len(x), 1000)

    def test_bitboard_operations(self):
        bb = BitBoard(size=3)
        self.assertFalse(bb.has_cell(1, 1))

        bb.set_cell_inplace(1, 1)
        self.assertTrue(bb.has_cell(1, 1))

        bb.clear_cell_inplace(1, 1)
        self.assertFalse(bb.has_cell(1, 1))

    def test_bitboard_line_check(self):
        bb = BitBoard(size=3)
        # Horizontal row 0
        for c in range(3):
            bb.set_cell_inplace(0, c)
        self.assertTrue(bb.is_line(k=3))

        # Clear and test diagonal
        bb_diag = BitBoard(size=3)
        for i in range(3):
            bb_diag.set_cell_inplace(i, i)
        self.assertTrue(bb_diag.is_line(k=3))

    def test_fast_grid_undo(self):
        grid = FastGrid(size=3)
        self.assertEqual(len(grid.empty_cells()), 9)

        grid.make_move(1, 1, player=0)
        self.assertEqual(grid.get(1, 1), 0)
        self.assertEqual(len(grid.empty_cells()), 8)

        grid.undo_move()
        self.assertIsNone(grid.get(1, 1))
        self.assertEqual(len(grid.empty_cells()), 9)

    def test_profiler_timing_and_throughput(self):
        def sample_work():
            return sum(i * i for i in range(100))

        res, elapsed = time_execution(sample_work)
        self.assertGreater(res, 0)
        self.assertGreaterEqual(elapsed, 0.0)

        throughput = benchmark_throughput(sample_work, iterations=500)
        self.assertGreater(throughput, 1000.0)  # Should easily exceed 1000 ops/s

        res2, delta = profile_memory_delta(sample_work)
        self.assertEqual(res, res2)
        self.assertGreaterEqual(delta, 0.0)

    def test_time_budget(self):
        budget = TimeBudget(allocated_seconds=1.0, safety_margin=0.2)
        self.assertFalse(budget.is_expired())
        self.assertGreater(budget.remaining_seconds(), 0.0)
        self.assertGreaterEqual(budget.elapsed_seconds(), 0.0)

    def test_bitboard_canonical_mask(self):
        # A1 is (0, 0), C1 is (0, 2), A3 is (2, 0), C3 is (2, 2)
        # All 4 individual corners are symmetric and should produce the identical canonical_mask!
        bb_a1 = BitBoard(size=3)
        bb_a1.set_cell_inplace(0, 0)

        bb_c1 = BitBoard(size=3)
        bb_c1.set_cell_inplace(0, 2)

        bb_c3 = BitBoard(size=3)
        bb_c3.set_cell_inplace(2, 2)

        self.assertEqual(bb_a1.canonical_mask(), bb_c1.canonical_mask())
        self.assertEqual(bb_a1.canonical_mask(), bb_c3.canonical_mask())

    def test_transposition_table(self):
        tt = TranspositionTable(capacity=10)
        tt.store("state_1", depth=4, value=1.0, flag=TT_EXACT, best_action="B2")

        val, move = tt.lookup("state_1", depth=4, alpha=-1.0, beta=2.0)
        self.assertEqual(val, 1.0)
        self.assertEqual(move, "B2")

        # Deeper search cannot use shallower cached value
        val_deep, _ = tt.lookup("state_1", depth=5, alpha=-1.0, beta=2.0)
        self.assertIsNone(val_deep)


if __name__ == "__main__":
    unittest.main()
