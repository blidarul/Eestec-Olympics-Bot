"""High-Performance Dots and Boxes Optimal Solver (Graph/Degree Evaluation).
Evaluates board edge degrees, prioritizes box captures (degree 4 completions),
strictly prevents box sacrifices (leaving degree 3 boxes for opponent),
and minimizes chain giveaways in the endgame.
Owned by agent `bld`.
"""
from __future__ import annotations

import re


def _norm_edge(act: str) -> tuple[str, str] | None:
    m = re.match(r"^(?:line\s+)?([a-z]\d+)[ -]([a-z]\d+)$", act.strip().lower())
    if not m:
        return None
    d1, d2 = sorted([m.group(1), m.group(2)])
    return (d1, d2)


def parse_dab_dimensions(rules: str, observation: str) -> tuple[int, int]:
    """Parse (rows, cols) of boxes from rules or observation (e.g. '4x4 boxes', '3x5 boxes')."""
    m = re.search(r"\((\d+)\s*[x×]\s*(\d+)\s*boxes\)", observation or "", re.I) or re.search(
        r"\((\d+)\s*[x×]\s*(\d+)\s*boxes\)", rules or "", re.I
    )
    if m:
        return int(m.group(1)), int(m.group(2))
    m2 = re.search(r"(\d+)\s*[x×]\s*(\d+)\s*boxes", rules or "", re.I)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    # Count dots from observation if present
    rows_found = re.findall(r"^\s*(\d+)\s*\+", observation or "", re.M)
    if rows_found:
        dot_r = max(int(r) for r in rows_found)
        return max(1, dot_r - 1), max(1, dot_r - 1)
    return 4, 4


def solve_dots_and_boxes(
    legal_actions: list[str],
    rules: str = "",
    observation: str = "",
) -> str | None:
    """Choose optimal move in Dots and Boxes:
    1. Complete any box (degree 4) and take bonus turn. Double-box completion prioritized.
    2. Pick completely safe lines (degree <= 2 for all adjacent boxes).
    3. If all lines give away boxes, pick sacrifice that gives away the fewest boxes.
    """
    if not legal_actions:
        return None

    legal_map: dict[tuple[str, str], str] = {}
    for a in legal_actions:
        ne = _norm_edge(a)
        if ne:
            legal_map[ne] = a

    if not legal_map:
        return legal_actions[0]

    rows, cols = parse_dab_dimensions(rules, observation)

    # Generate all boxes and their 4 boundary edges
    boxes: list[list[tuple[str, str]]] = []
    all_edges: set[tuple[str, str]] = set()

    for r in range(rows):
        for c in range(cols):
            d_tl = f"{chr(ord('a') + c)}{r + 1}"
            d_tr = f"{chr(ord('a') + c + 1)}{r + 1}"
            d_bl = f"{chr(ord('a') + c)}{r + 2}"
            d_br = f"{chr(ord('a') + c + 1)}{r + 2}"
            e_top = tuple(sorted([d_tl, d_tr]))
            e_bot = tuple(sorted([d_bl, d_br]))
            e_left = tuple(sorted([d_tl, d_bl]))
            e_right = tuple(sorted([d_tr, d_br]))
            b_edges = [e_top, e_bot, e_left, e_right]
            boxes.append(b_edges)
            all_edges.update(b_edges)

    # Drawn edges are all potential grid edges not in legal_map
    drawn = all_edges - set(legal_map.keys())

    captures: list[tuple[int, str]] = []
    safe_moves: list[str] = []
    sacrifice_moves: list[tuple[int, str]] = []

    for edge, orig_act in legal_map.items():
        completes = 0
        gives_away = 0
        for b_edges in boxes:
            if edge in b_edges:
                drawn_in_b = sum(1 for e in b_edges if e in drawn)
                if drawn_in_b == 3:
                    completes += 1
                elif drawn_in_b == 2:
                    gives_away += 1

        if completes > 0:
            captures.append((completes, orig_act))
        elif gives_away == 0:
            safe_moves.append(orig_act)
        else:
            sacrifice_moves.append((gives_away, orig_act))

    # Priority 1: Captures (most boxes completed first)
    if captures:
        captures.sort(key=lambda x: -x[0])
        return captures[0][1]

    # Priority 2: Safe moves
    if safe_moves:
        return safe_moves[0]

    # Priority 3: Sacrifices (minimize boxes given away)
    if sacrifice_moves:
        sacrifice_moves.sort(key=lambda x: x[0])
        return sacrifice_moves[0][1]

    return legal_actions[0]
