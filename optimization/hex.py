"""High-Performance Hex Connection Solver (Dijkstra Shortest Path Dual-Potential).
Computes topological shortest connection distance for both players using Dijkstra on hex graph.
Selects moves that maximize our bridge completion while disrupting the opponent's connection.
Owned by agent `bld`.
"""
from __future__ import annotations

import heapq
import re


def _neighbours(r: int, c: int, size: int) -> list[tuple[int, int]]:
    cands = [
        (r, c - 1),
        (r, c + 1),
        (r - 1, c),
        (r - 1, c + 1),
        (r + 1, c - 1),
        (r + 1, c),
    ]
    return [(nr, nc) for nr, nc in cands if 0 <= nr < size and 0 <= nc < size]


def shortest_path_dist(board: list[list[int | None]], seat: int, size: int) -> float:
    """Dijkstra shortest path distance to connect the player's target edges:
    Seat 0: row 0 to row size-1
    Seat 1: col 0 to col size-1
    Cost: 0 for own stone, 1 for empty, inf for opponent stone.
    """
    dist: dict[tuple[int, int], int] = {}
    pq: list[tuple[int, int, int]] = []
    opp = 1 - seat

    if seat == 0:
        for c in range(size):
            if board[0][c] != opp:
                w = 0 if board[0][c] == 0 else 1
                dist[(0, c)] = w
                heapq.heappush(pq, (w, 0, c))
    else:
        for r in range(size):
            if board[r][0] != opp:
                w = 0 if board[r][0] == 1 else 1
                dist[(r, 0)] = w
                heapq.heappush(pq, (w, r, 0))

    while pq:
        d, r, c = heapq.heappop(pq)
        if (seat == 0 and r == size - 1) or (seat == 1 and c == size - 1):
            return float(d)
        if d > dist.get((r, c), float("inf")):
            continue
        for nr, nc in _neighbours(r, c, size):
            if board[nr][nc] == opp:
                continue
            cost = 0 if board[nr][nc] == seat else 1
            if d + cost < dist.get((nr, nc), float("inf")):
                dist[(nr, nc)] = d + cost
                heapq.heappush(pq, (d + cost, nr, nc))
    return float("inf")


def parse_hex_move(move_str: str) -> tuple[int, int] | None:
    """Parse 'place d4' or 'd4' into (row, col) 0-indexed."""
    m = re.search(r"([a-z])(\d+)", move_str.lower())
    if not m:
        return None
    c = ord(m.group(1)) - ord("a")
    r = int(m.group(2)) - 1
    return r, c


def parse_hex_observation(obs: str) -> tuple[list[list[int | None]], int, int]:
    """Parse board grid, player seat, and size from Hex observation text."""
    seat = 0
    if "Player 1" in obs and ("You are Player 1" in obs or "('O')" in obs):
        if "You are Player 0" not in obs:
            seat = 1

    m_sz = re.search(r"HEX\s*\((\d+)\s*[x×]\s*(\d+)\)", obs, re.I)
    size = int(m_sz.group(1)) if m_sz else 7

    board: list[list[int | None]] = [[None] * size for _ in range(size)]
    for line in obs.splitlines():
        m_row = re.search(r"^\s*(\d+)\s+([.XO\s]+)\s+\d+\s*$", line)
        if m_row:
            r = int(m_row.group(1)) - 1
            if 0 <= r < size:
                tokens = [t for t in m_row.group(2).split() if t in (".", "X", "O")]
                if len(tokens) == size:
                    for c, tok in enumerate(tokens):
                        if tok == "X":
                            board[r][c] = 0
                        elif tok == "O":
                            board[r][c] = 1
                        else:
                            board[r][c] = None

    return board, seat, size


def solve_hex(legal_actions: list[str], observation: str = "") -> str | None:
    """Select the strategically dominant Hex move using dual shortest path potential."""
    if not legal_actions:
        return None
    if len(legal_actions) == 1:
        return legal_actions[0]

    board, seat, size = parse_hex_observation(observation)
    opp = 1 - seat

    base_my = shortest_path_dist(board, seat, size)
    base_opp = shortest_path_dist(board, opp, size)

    center = (size - 1) / 2.0
    scored: list[tuple[float, str]] = []

    for act in legal_actions:
        rc = parse_hex_move(act)
        if not rc:
            scored.append((-999.0, act))
            continue
        r, c = rc
        if not (0 <= r < size and 0 <= c < size):
            scored.append((-999.0, act))
            continue

        board[r][c] = seat
        new_my = shortest_path_dist(board, seat, size)
        new_opp = shortest_path_dist(board, opp, size)
        board[r][c] = None

        my_gain = base_my - new_my
        opp_disrupt = new_opp - base_opp
        center_dist = abs(r - center) + abs(c - center)

        score = my_gain * 2.5 + opp_disrupt * 2.0 - center_dist * 0.1
        if new_my == 0:
            score += 1000.0  # Winning move!
        if base_opp == 1 and new_opp > 1:
            score += 500.0  # Critical block against immediate opponent win

        scored.append((score, act))

    scored.sort(key=lambda x: -x[0])
    return scored[0][1]
