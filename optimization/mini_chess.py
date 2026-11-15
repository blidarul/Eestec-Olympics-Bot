"""High-Performance Tactical Mini-Chess Evaluator (MVV-LVA, Defense, and Promotion).
Calculates piece exchanges, detects hanging pieces, prioritizes promotions and captures,
and guards against blunders.
Owned by agent `bld`.
"""
from __future__ import annotations

import re

PIECE_VALS = {"p": 100, "n": 320, "b": 330, "r": 500, "q": 900, "k": 20000}


def is_square_attacked(
    grid: list[list[str]],
    r: int,
    c: int,
    by_side: int,
    size: int,
) -> bool:
    """Check if square (r, c) is attacked by `by_side` (0 = White, 1 = Black)."""
    p_dir = -1 if by_side == 0 else 1
    p_char = "P" if by_side == 0 else "p"
    # Pawn attacks
    for dc in (-1, 1):
        pr, pc = r - p_dir, c + dc
        if 0 <= pr < size and 0 <= pc < size and grid[pr][pc] == p_char:
            return True

    # Knight attacks
    n_char = "N" if by_side == 0 else "n"
    for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
        nr, nc = r + dr, c + dc
        if 0 <= nr < size and 0 <= nc < size and grid[nr][nc] == n_char:
            return True

    # King attacks
    k_char = "K" if by_side == 0 else "k"
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            kr, kc = r + dr, c + dc
            if 0 <= kr < size and 0 <= kc < size and grid[kr][kc] == k_char:
                return True

    # Sliding pieces: R/Q straight
    rq_chars = ("R", "Q") if by_side == 0 else ("r", "q")
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        curr_r, curr_c = r + dr, c + dc
        while 0 <= curr_r < size and 0 <= curr_c < size:
            ch = grid[curr_r][curr_c]
            if ch != ".":
                if ch in rq_chars:
                    return True
                break
            curr_r += dr
            curr_c += dc

    # Sliding pieces: B/Q diagonal
    bq_chars = ("B", "Q") if by_side == 0 else ("b", "q")
    for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        curr_r, curr_c = r + dr, c + dc
        while 0 <= curr_r < size and 0 <= curr_c < size:
            ch = grid[curr_r][curr_c]
            if ch != ".":
                if ch in bq_chars:
                    return True
                break
            curr_r += dr
            curr_c += dc

    return False


def parse_chess_grid(observation: str) -> tuple[list[list[str]], int, int]:
    """Extract grid matrix, current side to move, and board size from observation text."""
    lines = observation.splitlines()
    size = 5
    m_sz = re.search(r"(\d+)\s*[x×]\s*(\d+)", observation)
    if m_sz:
        size = int(m_sz.group(1))

    side = 0
    if "BLACK" in observation and ("BLACK to move" in observation or "You are BLACK" in observation):
        if "You are WHITE" not in observation:
            side = 1

    grid = [["."] * size for _ in range(size)]
    for line in lines:
        m = re.search(r"^\s*(\d)\s+([a-zA-Z\.\s]+)\s+\d\s*$", line)
        if m:
            rank = int(m.group(1))
            r = size - rank
            if 0 <= r < size:
                tokens = [t for t in m.group(2).split() if len(t) == 1]
                if len(tokens) == size:
                    grid[r] = tokens

    return grid, side, size


def evaluate_chess_move(act: str, grid: list[list[str]], side: int, size: int) -> float:
    """Evaluate candidate move score based on material, attack/defense, and tactics."""
    m = re.match(r"^([a-h])([1-8])([a-h])([1-8])", act.lower())
    if not m:
        return 0.0

    c1 = ord(m.group(1)) - ord("a")
    r1 = size - int(m.group(2))
    c2 = ord(m.group(3)) - ord("a")
    r2 = size - int(m.group(4))

    if not (0 <= r1 < size and 0 <= c1 < size and 0 <= r2 < size and 0 <= c2 < size):
        return -999.0

    piece = grid[r1][c1]
    target = grid[r2][c2]
    p_val = PIECE_VALS.get(piece.lower(), 100)
    opp = 1 - side

    score = 0.0

    # 1. Capture value (MVV-LVA: Most Valuable Victim - Least Valuable Attacker)
    if target != ".":
        t_val = PIECE_VALS.get(target.lower(), 100)
        score += t_val * 10.0 - p_val * 0.1

    # 2. Rescue hanging piece
    was_hanging = is_square_attacked(grid, r1, c1, opp, size) and not is_square_attacked(grid, r1, c1, side, size)

    # Simulate move
    grid[r1][c1] = "."
    promoted = False
    if piece.lower() == "p" and (r2 == 0 or r2 == size - 1):
        grid[r2][c2] = "Q" if side == 0 else "q"
        promoted = True
        score += 800.0
    else:
        grid[r2][c2] = piece

    dest_attacked = is_square_attacked(grid, r2, c2, opp, size)
    dest_defended = is_square_attacked(grid, r2, c2, side, size)
    eff_val = 900 if promoted else p_val
    t_val = PIECE_VALS.get(target.lower(), 0) if target != "." else 0

    if was_hanging and not dest_attacked:
        score += eff_val * 2.0  # Successfully evacuated hanging piece!

    if dest_attacked:
        if not dest_defended:
            score -= eff_val * 3.0  # Move blunders piece for free!
        elif eff_val > t_val:
            score -= (eff_val - t_val) * 2.0  # Unfavorable exchange!

    # 3. Center control
    center = (size - 1) / 2.0
    dist = abs(c2 - center) + abs(r2 - center)
    score -= dist * 2.0

    # Revert move
    grid[r1][c1] = piece
    grid[r2][c2] = target

    return score


def solve_mini_chess(legal_actions: list[str], observation: str = "") -> str | None:
    """Select the strategically dominant Mini Chess move from legal_actions."""
    if not legal_actions:
        return None
    if len(legal_actions) == 1:
        return legal_actions[0]

    grid, side, size = parse_chess_grid(observation)
    scored = [(evaluate_chess_move(a, grid, side, size), a) for a in legal_actions]
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]
