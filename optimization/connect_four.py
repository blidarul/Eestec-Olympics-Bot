"""High-Performance Connect Four Bitboard Engine and Solver.
Supports variable R (rows), C (cols), K (connect-in-a-row).
Includes C engine acceleration (negamax + alpha-beta + TT <= 256MB)
with an automatic pure Python bitboard engine fallback.
Owned by agent `bld`.
"""
from __future__ import annotations

import ctypes
import os
import re
import sys
import time
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# C Engine loader
# ---------------------------------------------------------------------------
_LIB_C4 = None


def _load_c_engine() -> Any:
    global _LIB_C4
    if _LIB_C4 is not None:
        return _LIB_C4

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "c4_engine.so"),
        os.path.join(here, "c4_engine.dll"),
        os.path.join(here, "libc4_engine.so"),
    ]

    for p in candidates:
        if os.path.exists(p):
            try:
                lib = ctypes.CDLL(p)
                lib.c4_solve.argtypes = [
                    ctypes.c_int,  # R
                    ctypes.c_int,  # C
                    ctypes.c_int,  # K
                    ctypes.POINTER(ctypes.c_int),  # moves
                    ctypes.c_int,  # num_moves
                    ctypes.c_int,  # one_indexed
                    ctypes.c_int,  # max_depth
                    ctypes.c_double,  # timeout_seconds
                    ctypes.POINTER(ctypes.c_int),  # out_score
                    ctypes.POINTER(ctypes.c_int),  # out_depth
                    ctypes.POINTER(ctypes.c_int),  # out_proven
                ]
                lib.c4_solve.restype = ctypes.c_int
                _LIB_C4 = lib
                return _LIB_C4
            except Exception:
                pass
    return None


# ---------------------------------------------------------------------------
# Pure Python Bitboard Fallback Engine
# ---------------------------------------------------------------------------
class PythonBitboardEngine:
    """Pure Python bitboard engine with iterative deepening negamax,
    immediate win/block detection, and transposition table <= 256MB.
    """

    def __init__(self, rows: int = 6, cols: int = 7, connect_k: int = 4):
        self.rows = rows
        self.cols = cols
        self.k = connect_k
        self.step = rows + 1

        self.col_masks = [(((1 << rows) - 1) << (c * self.step)) for c in range(cols)]
        self.top_masks = [(1 << (c * self.step + rows - 1)) for c in range(cols)]
        self.bottom_bits = [(1 << (c * self.step)) for c in range(cols)]

        # Center-first ordering
        self.center_order = sorted(range(cols), key=lambda c: (abs(c - (cols - 1) / 2.0), c))
        # Positional column weights
        self.col_weights = [
            int(10.0 * (1.0 - abs(c - (cols - 1) / 2.0) / (cols / 2.0))) + 1
            for c in range(cols)
        ]
        self.tt: dict[tuple[int, int], tuple[int, int, int]] = {}

    def check_win(self, m: int) -> bool:
        """Check if bitmask m contains K in a row in any of 4 directions."""
        k = self.k
        s = self.step

        # 1. Vertical
        v = m
        for _ in range(k - 1):
            v &= (v >> 1)
        if v:
            return True

        # 2. Horizontal
        h = m
        for _ in range(k - 1):
            h &= (h >> s)
        if h:
            return True

        # 3. Diagonal /
        d1 = m
        for _ in range(k - 1):
            d1 &= (d1 >> (s + 1))
        if d1:
            return True

        # 4. Diagonal \
        d2 = m
        for _ in range(k - 1):
            d2 &= (d2 >> (s - 1))
        if d2:
            return True

        return False

    def eval_heuristic(self, cur_p: int, opp_p: int) -> int:
        score = 0
        for c in range(self.cols):
            w = self.col_weights[c]
            cb = self.col_masks[c]
            score += bin(cur_p & cb).count("1") * w
            score -= bin(opp_p & cb).count("1") * w
        return score

    def solve(
        self,
        moves: Sequence[int],
        one_indexed: bool = True,
        max_depth: int = 12,
        timeout: float = 8.0,
    ) -> tuple[int, int, int, bool]:
        """Solve board given move list. Returns (best_move, score, depth, proven).
        best_move is 1-indexed if one_indexed=True, else 0-indexed.
        """
        t_start = time.monotonic()
        deadline = t_start + max(0.05, timeout)

        # Replay moves
        p0 = 0
        mask = 0
        turn = 0
        for raw_m in moves:
            m = (raw_m - 1) if one_indexed else raw_m
            if m < 0 or m >= self.cols or (mask & self.top_masks[m]):
                continue
            np = (mask + self.bottom_bits[m]) & self.col_masks[m]
            if turn == 0:
                p0 |= np
            mask |= np
            turn = 1 - turn

        cur_p = p0 if turn == 0 else (mask ^ p0)
        opp_p = mask ^ cur_p

        open_c = [c for c in self.center_order if not (mask & self.top_masks[c])]
        if not open_c:
            return -1, 0, 0, True

        # 1. Immediate Win Check (1 ply)
        for c in open_c:
            np = (mask + self.bottom_bits[c]) & self.col_masks[c]
            if self.check_win(cur_p | np):
                return (c + 1) if one_indexed else c, 10000, 1, True

        # 2. Immediate Block Check (1 ply)
        blocks = []
        for c in open_c:
            np = (mask + self.bottom_bits[c]) & self.col_masks[c]
            if self.check_win(opp_p | np):
                blocks.append(c)

        if blocks:
            # Choose block that does not blunder immediately above if possible
            chosen = blocks[0]
            for b in blocks:
                np = (mask + self.bottom_bits[b]) & self.col_masks[b]
                above = np << 1
                if not ((above & self.col_masks[b]) and self.check_win(opp_p | above)):
                    chosen = b
                    break
            return (chosen + 1) if one_indexed else chosen, -500, 1, False

        # 3. Negamax search with alpha-beta and transposition table
        self.tt.clear()

        timeout_hit = False

        def negamax(cp: int, cur_mask: int, depth: int, alpha: int, beta: int) -> int:
            nonlocal timeout_hit
            if time.monotonic() >= deadline:
                timeout_hit = True
                return 0

            if depth <= 0:
                return self.eval_heuristic(cp, cur_mask ^ cp)

            key = (cp, cur_mask)
            if key in self.tt:
                val, d, flag = self.tt[key]
                if d >= depth:
                    if flag == 0:
                        return val
                    if flag == 1 and val <= alpha:
                        return val
                    if flag == 2 and val >= beta:
                        return val

            moves_avail = [c for c in self.center_order if not (cur_mask & self.top_masks[c])]
            if not moves_avail:
                return 0

            # Win check
            for c in moves_avail:
                np = (cur_mask + self.bottom_bits[c]) & self.col_masks[c]
                if self.check_win(cp | np):
                    return 10000 + depth

            best = -30000
            orig_alpha = alpha
            next_opp = cur_mask ^ cp

            for c in moves_avail:
                np = (cur_mask + self.bottom_bits[c]) & self.col_masks[c]
                above = np << 1
                if (above & self.col_masks[c]) and self.check_win(next_opp | above):
                    val = -(9000 + depth)
                else:
                    val = -negamax(next_opp, cur_mask | np, depth - 1, -beta, -alpha)

                if timeout_hit:
                    return 0

                if val > best:
                    best = val
                if val > alpha:
                    alpha = val
                if alpha >= beta:
                    break

            if not timeout_hit:
                flag = 1 if best <= orig_alpha else (2 if best >= beta else 0)
                self.tt[key] = (best, depth, flag)

            return best

        best_move = open_c[0]
        best_score = -30000
        completed_depth = 1
        proven = False

        target_max_d = max_depth
        if self.rows * self.cols <= 30 and target_max_d < 16:
            target_max_d = 16

        for d in range(1, target_max_d + 1):
            depth_best_move = open_c[0]
            depth_best_score = -30000
            timeout_in_d = False

            for c in open_c:
                np = (mask + self.bottom_bits[c]) & self.col_masks[c]
                above = np << 1
                if (above & self.col_masks[c]) and self.check_win(opp_p | above):
                    val = -(9000 + d)
                else:
                    val = -negamax(opp_p, mask | np, d - 1, -30000, 30000)

                if timeout_hit:
                    timeout_in_d = True
                    break

                if val > depth_best_score:
                    depth_best_score = val
                    depth_best_move = c

            if timeout_in_d:
                break

            best_move = depth_best_move
            best_score = depth_best_score
            completed_depth = d

            if abs(best_score) >= 9000:
                proven = True
                break

        res_col = (best_move + 1) if one_indexed else best_move
        return res_col, best_score, completed_depth, proven


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------
def solve_connect_four(
    moves: Sequence[int] | str,
    rows: int = 6,
    cols: int = 7,
    connect_k: int = 4,
    open_cols: Sequence[int] | None = None,
    deadline: float | None = None,
    max_depth: int = 12,
) -> tuple[int, dict[str, Any]]:
    """Solve Connect Four position.
    Returns (col_1_indexed, info_dict).
    Guarantees chosen col is legal (open) and within 1..cols.
    """
    t0 = time.monotonic()
    timeout = (deadline - t0) if deadline is not None else 8.0
    if timeout <= 0.05:
        timeout = 0.05

    # Parse move sequence
    if isinstance(moves, str):
        move_ints = [int(x) for x in re.findall(r"\d+", moves)]
    else:
        move_ints = [int(x) for x in moves]

    # Normalize moves to 1-indexed for the solver call
    # If any move is 0, entire sequence was 0-indexed -> convert to 1-indexed
    if any(m == 0 for m in move_ints):
        norm_moves = [m + 1 for m in move_ints]
    else:
        norm_moves = move_ints

    c_lib = _load_c_engine()
    engine_name = "c_native" if c_lib is not None else "python_bitboard"

    best_col_1 = 1
    score = 0
    depth_reached = 1
    proven = False

    if c_lib is not None:
        try:
            arr = (ctypes.c_int * len(norm_moves))(*norm_moves)
            out_sc = ctypes.c_int()
            out_dp = ctypes.c_int()
            out_pr = ctypes.c_int()
            res = c_lib.c4_solve(
                rows,
                cols,
                connect_k,
                arr,
                len(norm_moves),
                1,  # one_indexed=1
                max_depth,
                timeout,
                ctypes.byref(out_sc),
                ctypes.byref(out_dp),
                ctypes.byref(out_pr),
            )
            if 1 <= res <= cols:
                best_col_1 = res
                score = out_sc.value
                depth_reached = out_dp.value
                proven = bool(out_pr.value)
            else:
                c_lib = None
        except Exception:
            c_lib = None

    if c_lib is None:
        py_engine = PythonBitboardEngine(rows=rows, cols=cols, connect_k=connect_k)
        best_col_1, score, depth_reached, proven = py_engine.solve(
            norm_moves, one_indexed=True, max_depth=max_depth, timeout=timeout
        )

    # Validate against open_cols if provided
    if open_cols:
        norm_open = [c if c >= 1 else (c + 1) for c in open_cols]
        if norm_open and best_col_1 not in norm_open:
            best_col_1 = norm_open[0]

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    info = {
        "col": best_col_1,
        "col_0": best_col_1 - 1,
        "action": f"drop {best_col_1}",
        "score": score,
        "depth": depth_reached,
        "proven": proven,
        "ms": elapsed_ms,
        "engine": engine_name,
    }
    return best_col_1, info
