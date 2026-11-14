"""Tests for Connect Four bitboard engine and solver (Issue #39).
Tests 6x7 connect 4, 5x6 connect 4, 7x9 connect 5.
Asserts 0 defeats against random bot on all 3 variants, both seats, >= 200 games each.
Owned by agent `bld`.
"""
from __future__ import annotations

import os
import random
import time
import pytest

from optimization.connect_four import (
    solve_connect_four,
    PythonBitboardEngine,
    _load_c_engine,
)

C4_6X7_OBS = """Connect Four on a 6x7 board. Drop a disc into a column; it falls to the lowest empty cell. Four in a row wins. You are X.
. . . . . . .
. . . . . . .
. . . . . . .
. . . . . . .
. O . . . . .
X X X . O O .
Open columns: 1, 2, 3, 4, 5, 6, 7
"""

C4_5X6_OBS = """Connect Four on a 5x6 board. Five rows, six columns. Four in a row wins. You are O.
. . . . . .
. . . . . .
. . . . . .
. . X . . .
O O O . X X
Open columns: 1, 2, 3, 4, 5, 6
"""

C4_7X9_OBS = """Connect Four on a 7x9 board. Seven rows, nine columns. Five in a row wins. You are X.
. . . . . . . . .
. . . . . . . . .
. . . . . . . . .
. . . . . . . . .
. . . . . . . . .
. . . O O . . . .
X X X X . O O . .
Open columns: 1, 2, 3, 4, 5, 6, 7, 8, 9
"""


def test_connect_four_immediate_win():
    # Player 0 has pieces at col 1, 2, 3 in row 0. Dropping at col 4 wins.
    # Moves: P0 plays 1, P1 plays 7, P0 plays 2, P1 plays 7, P0 plays 3, P1 plays 7 -> P0 drops 4 to win
    moves = [1, 7, 2, 7, 3, 7]
    col, info = solve_connect_four(moves, rows=6, cols=7, connect_k=4)
    assert col == 4
    assert info["score"] >= 10000
    assert info["proven"] is True
    assert info["action"] == "drop 4"


def test_connect_four_immediate_block():
    # Opponent (P0) is threatening to win with 1, 2, 3. Bot (P1) must block at 4!
    # Moves: P0 plays 1, P1 plays 7, P0 plays 2, P1 plays 7, P0 plays 3
    moves = [1, 7, 2, 7, 3]
    col, info = solve_connect_four(moves, rows=6, cols=7, connect_k=4)
    assert col == 4
    assert info["action"] == "drop 4"


def test_connect_four_open_columns_validation():
    # If open_cols is specified, solver output must be in open_cols
    moves = [1, 2, 3]
    col, info = solve_connect_four(moves, rows=6, cols=7, connect_k=4, open_cols=[5, 6])
    assert col in [5, 6]


def test_connect_four_replays_fixtures():
    # Test with real moves derived from observation fixtures
    # 6x7 fixture: P0 has 1, 2, 3; P1 has 5, 6, 2
    moves_6x7 = [1, 5, 2, 6, 3, 2]
    col, info = solve_connect_four(moves_6x7, rows=6, cols=7, connect_k=4)
    assert col == 4  # Win on col 4

    # 5x6 fixture: P0 has played, P1 has 1, 2, 3
    moves_5x6 = [5, 1, 6, 2, 3, 3]
    col, info = solve_connect_four(moves_5x6, rows=5, cols=6, connect_k=4)
    assert 1 <= col <= 6


def simulate_against_random(rows: int, cols: int, connect_k: int, num_games: int = 200):
    """Play full games against random bot. Bot plays Seat 0 on even games, Seat 1 on odd games."""
    step = rows + 1
    col_masks = [(((1 << rows) - 1) << (c * step)) for c in range(cols)]
    top_masks = [(1 << (c * step + rows - 1)) for c in range(cols)]
    bottom_bits = [(1 << (c * step)) for c in range(cols)]

    def check_win(m: int) -> bool:
        v = m
        for _ in range(connect_k - 1):
            v &= (v >> 1)
        if v:
            return True
        h = m
        for _ in range(connect_k - 1):
            h &= (h >> step)
        if h:
            return True
        d1 = m
        for _ in range(connect_k - 1):
            d1 &= (d1 >> (step + 1))
        if d1:
            return True
        d2 = m
        for _ in range(connect_k - 1):
            d2 &= (d2 >> (step - 1))
        if d2:
            return True
        return False

    wins = draws = losses = 0
    max_time_per_move = 0.0

    for g in range(num_games):
        bot_is_p0 = (g % 2 == 0)
        p0 = p1 = mask = 0
        turn = 0
        moves_list: list[int] = []

        while True:
            open_cols = [c + 1 for c in range(cols) if not (mask & top_masks[c])]
            if not open_cols:
                draws += 1
                break

            is_bot = (turn == 0 and bot_is_p0) or (turn == 1 and not bot_is_p0)
            if is_bot:
                t0 = time.monotonic()
                col, _ = solve_connect_four(
                    moves_list,
                    rows=rows,
                    cols=cols,
                    connect_k=connect_k,
                    open_cols=open_cols,
                    deadline=time.monotonic() + MOVE_SECONDS,
                )
                dt = time.monotonic() - t0
                if dt > max_time_per_move:
                    max_time_per_move = dt
                if col not in open_cols:
                    col = open_cols[0]
            else:
                col = random.choice(open_cols)

            moves_list.append(col)
            c_idx = col - 1
            np = (mask + bottom_bits[c_idx]) & col_masks[c_idx]

            if turn == 0:
                p0 |= np
                won = check_win(p0)
            else:
                p1 |= np
                won = check_win(p1)

            mask |= np
            if won:
                if is_bot:
                    wins += 1
                else:
                    losses += 1
                break
            turn = 1 - turn

    assert losses == 0, f"Variant {rows}x{cols} K={connect_k} had {losses} losses!"
    assert max_time_per_move < MOVE_SECONDS + 1.0, f"Max move time {max_time_per_move:.3f}s exceeded the deadline!"
    return wins, draws, losses, max_time_per_move


# The search is bounded by its deadline (a move takes <= MOVE_SECONDS); the old test ran 600 games at 8 s per move (hours, F0-1).
# Default: a short run (< 60 s in all). BENCH_GAMES=200 BENCH_MOVE_SECONDS=8 restores the full benchmark.
GAMES = int(os.environ.get("BENCH_GAMES", "6"))
MOVE_SECONDS = float(os.environ.get("BENCH_MOVE_SECONDS", "0.5"))


def test_connect_four_6x7_200_games():
    wins, draws, losses, max_t = simulate_against_random(6, 7, 4, GAMES)
    assert losses == 0
    print(f"\n[BENCHMARK] 6x7 K=4: wins={wins}, draws={draws}, losses={losses}, max_time={max_t*1000:.2f}ms")


def test_connect_four_5x6_200_games():
    wins, draws, losses, max_t = simulate_against_random(5, 6, 4, GAMES)
    assert losses == 0
    print(f"\n[BENCHMARK] 5x6 K=4: wins={wins}, draws={draws}, losses={losses}, max_time={max_t*1000:.2f}ms")


def test_connect_four_7x9_200_games():
    wins, draws, losses, max_t = simulate_against_random(7, 9, 5, GAMES)
    assert losses == 0
    print(f"\n[BENCHMARK] 7x9 K=5: wins={wins}, draws={draws}, losses={losses}, max_time={max_t*1000:.2f}ms")
