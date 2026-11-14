"""Precomputed Opening Book for Connect Four boards.
Precomputes optimal opening moves for ply 0, ply 1, and ply 2 during prep.
Owned by agent `bld`.
"""
from __future__ import annotations

import sys
import time
from typing import Any
from .connect_four import solve_connect_four


def precompute_connect_four_book(
    rows: int = 6,
    cols: int = 7,
    connect_k: int = 4,
    time_limit_sec: float = 3.0,
) -> dict[str, int]:
    """Compute opening book dictionary mapping move history string -> best response column.
    Keys are space-separated moves e.g. "" (empty board), "4", "4 3".
    """
    t_deadline = time.monotonic() + time_limit_sec
    book: dict[str, int] = {}

    center_col = (cols + 1) // 2

    # Ply 0: Empty board opening move
    try:
        col0, _ = solve_connect_four([], rows=rows, cols=cols, connect_k=connect_k, max_depth=6, deadline=t_deadline)
        book[""] = col0
    except Exception:
        book[""] = center_col

    # Ply 1: Opponent played first move c1
    for c1 in range(1, cols + 1):
        if time.monotonic() >= t_deadline:
            break
        try:
            col1, _ = solve_connect_four([c1], rows=rows, cols=cols, connect_k=connect_k, max_depth=6, deadline=t_deadline)
            book[str(c1)] = col1
        except Exception:
            book[str(c1)] = center_col if c1 != center_col else (center_col - 1 if center_col > 1 else center_col + 1)

    # Ply 2: We played c0, opponent played c1
    c0 = book.get("", center_col)
    for c1 in range(1, cols + 1):
        if time.monotonic() >= t_deadline:
            break
        history_key = f"{c0} {c1}"
        try:
            col2, _ = solve_connect_four([c0, c1], rows=rows, cols=cols, connect_k=connect_k, max_depth=6, deadline=t_deadline)
            book[history_key] = col2
        except Exception:
            pass

    print(f"[c4_book] precomputed {len(book)} opening positions for {rows}x{cols}", file=sys.stderr)
    return book


def query_connect_four_book(book: dict[str, int] | None, moves: list[int]) -> int | None:
    """Check if the move history is in the precomputed opening book."""
    if not book:
        return None
    key = " ".join(str(m) for m in moves).strip()
    return book.get(key)
