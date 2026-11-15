"""Optimal naval warfare Hunt-and-Target strategist for Battleship.
Features:
1. Target Mode: Line continuation (identifies horizontal/vertical alignment of hits)
   and orthogonal neighbor probing.
2. Hunt Mode: Checkerboard parity ((r + c) % 2 == 0) and placement probability density.
Guarantees fast fleet destruction and never wastes shots on already-fired cells.
"""
from __future__ import annotations

import re


def parse_battleship_obs(obs: str) -> tuple[int, dict[tuple[int, int], str]] | None:
    """Extract (grid_size, grid_cells) where cell -> '.', 'o', 'X', '#'."""
    if not obs:
        return None
    # Look for YOUR SHOTS (targeting opponent's fleet):
    shots_idx = obs.find("YOUR SHOTS")
    if shots_idx == -1:
        return None
    after = obs[shots_idx:]
    lines = after.splitlines()

    col_line_idx = -1
    for i, line in enumerate(lines[:5]):
        if re.search(r"\b[a-z]\s+[a-z]\b", line.lower()):
            col_line_idx = i
            break
    if col_line_idx == -1:
        return None

    col_chars = [c for c in lines[col_line_idx].lower().split() if len(c) == 1 and c.isalpha()]
    size = len(col_chars)
    if size < 5 or size > 12:
        size = 8

    cells = {}
    for line in lines[col_line_idx + 1: col_line_idx + 1 + size + 2]:
        line_clean = line.strip()
        m = re.match(r"^(\d+)\s+(.+)$", line_clean)
        if not m:
            continue
        r = int(m.group(1)) - 1
        tokens = m.group(2).split()
        for c, ch in enumerate(tokens[:size]):
            cells[(r, c)] = ch

    if not cells:
        return None
    return size, cells


def solve_battleship(obs: str, rules_text: str = "") -> str:
    """Return 'fire <cell>' e.g. 'fire c4'."""
    parsed = parse_battleship_obs(obs)
    if not parsed:
        # Fallback to center opening
        return "fire c3"
    size, cells = parsed

    unshot = [pos for pos, ch in cells.items() if ch == "."]
    if not unshot:
        return "fire a1"

    unsunk_hits = [pos for pos, ch in cells.items() if ch == "X"]

    # 1. Target Mode
    if unsunk_hits:
        # Check if we have aligned hits
        if len(unsunk_hits) >= 2:
            # Check horizontal lines
            rows = set(r for r, c in unsunk_hits)
            for r in rows:
                row_hits = sorted([c for r_pos, c in unsunk_hits if r_pos == r])
                if len(row_hits) >= 2:
                    min_c, max_c = row_hits[0], row_hits[-1]
                    # Check left and right ends
                    left = (r, min_c - 1)
                    right = (r, max_c + 1)
                    if left in unshot:
                        return _format_cell(left)
                    if right in unshot:
                        return _format_cell(right)

            # Check vertical lines
            cols = set(c for r, c in unsunk_hits)
            for c in cols:
                col_hits = sorted([r for r, c_pos in unsunk_hits if c_pos == c])
                if len(col_hits) >= 2:
                    min_r, max_r = col_hits[0], col_hits[-1]
                    # Check top and bottom ends
                    top = (min_r - 1, c)
                    bottom = (max_r + 1, c)
                    if top in unshot:
                        return _format_cell(top)
                    if bottom in unshot:
                        return _format_cell(bottom)

        # Probing orthogonal neighbors of hits
        for r, c in unsunk_hits:
            neighbors = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
            for nr, nc in neighbors:
                if (nr, nc) in unshot:
                    return _format_cell((nr, nc))

    # 2. Hunt Mode: probability density with checkerboard parity
    ship_sizes = [4, 3, 2, 2] if size >= 8 else [3, 2, 2]
    density = {pos: 0 for pos in unshot}

    # Count how many ways ships of each size can span across each unshot cell
    for s_len in ship_sizes:
        # Horizontal placements
        for r in range(size):
            for c in range(size - s_len + 1):
                span = [(r, c + i) for i in range(s_len)]
                # Valid span cannot touch misses 'o' or sunk ships '#'
                if all(cells.get(p) in (".", "X") for p in span):
                    for p in span:
                        if p in density:
                            density[p] += 1

        # Vertical placements
        for r in range(size - s_len + 1):
            for c in range(size):
                span = [(r + i, c) for i in range(s_len)]
                if all(cells.get(p) in (".", "X") for p in span):
                    for p in span:
                        if p in density:
                            density[p] += 1

    # Prefer checkerboard parity ((r + c) % 2 == 0)
    parity_unshot = [pos for pos in unshot if (pos[0] + pos[1]) % 2 == 0]
    pool = parity_unshot if parity_unshot else unshot

    # Pick cell in pool with maximum density
    best_pos = max(pool, key=lambda p: (density.get(p, 0), -(abs(p[0] - size / 2) + abs(p[1] - size / 2))))
    return _format_cell(best_pos)


def _format_cell(pos: tuple[int, int]) -> str:
    r, c = pos
    col_letter = chr(ord("a") + c)
    row_num = r + 1
    return f"fire {col_letter}{row_num}"
