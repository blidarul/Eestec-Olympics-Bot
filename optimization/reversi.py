"""High-Performance 6x6 Reversi / Othello Positional Evaluator.
Leverages classical Othello strategic principles:
- Corners (a1, f1, a6, f6) are permanent anchor squares (+100).
- C-squares and X-squares adjacent to empty corners are strictly penalized (-20 to -40)
  to prevent gifting corners to the opponent.
- Edges provide stability (+15).
Owned by agent `bld`.
"""
from __future__ import annotations

import re

# 6x6 Othello positional weight table
REVERSI_WEIGHTS_6X6 = [
    [100, -20, 15, 15, -20, 100],
    [-20, -40, -5, -5, -40, -20],
    [15, -5, 3, 3, -5, 15],
    [15, -5, 3, 3, -5, 15],
    [-20, -40, -5, -5, -40, -20],
    [100, -20, 15, 15, -20, 100],
]


def parse_reversi_move(move_str: str) -> tuple[int, int] | None:
    """Parse 'place c4' or 'c4' into (row, col) 0-indexed."""
    m = re.search(r"([a-f])([1-6])", move_str.lower())
    if not m:
        return None
    c = ord(m.group(1)) - ord("a")
    r = int(m.group(2)) - 1
    return r, c


def parse_reversi_board(observation: str) -> tuple[list[list[str]], str]:
    """Parse 6x6 board grid and our player symbol from observation text."""
    my_stone = "X"
    if "Player 1 ('O')" in observation or "'O'" in observation:
        if "Player 0 ('X')" not in observation or "You are Player 1" in observation:
            my_stone = "O"

    board = [["."] * 6 for _ in range(6)]
    for line in observation.splitlines():
        m = re.match(r"^\s*(\d)\s+([.XO\s]+)\s+\d\s*$", line)
        if m:
            r = int(m.group(1)) - 1
            if 0 <= r < 6:
                tokens = m.group(2).split()
                if len(tokens) == 6:
                    board[r] = tokens
    return board, my_stone


def solve_reversi(legal_actions: list[str], observation: str = "") -> str | None:
    """Select the strategically dominant Reversi move from legal_actions."""
    if not legal_actions:
        return None
    if len(legal_actions) == 1:
        return legal_actions[0]

    board, my_stone = parse_reversi_board(observation)

    scored: list[tuple[float, str]] = []
    for act in legal_actions:
        rc = parse_reversi_move(act)
        if not rc:
            scored.append((-999.0, act))
            continue
        r, c = rc
        w = float(REVERSI_WEIGHTS_6X6[r][c])

        # If C-square or X-square is negative, check if we already own the corner
        if w < 0:
            corner_r = 0 if r <= 2 else 5
            corner_c = 0 if c <= 2 else 5
            if board[corner_r][corner_c] == my_stone:
                w = abs(w)  # Safe and solid if corner is secured!

        scored.append((w, act))

    scored.sort(key=lambda x: -x[0])
    return scored[0][1]
