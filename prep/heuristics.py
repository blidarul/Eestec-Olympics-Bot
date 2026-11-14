"""Precomputed Heuristics & Opening Books for 10-Minute Prep.
Precomputes lookup tables, optimal thresholds, and opening moves during the prep window.
Owned by agent `bld`.
"""
from __future__ import annotations

from typing import Any

from .action_parser import ActionGrammar
from .classifier import GameClassification


def compute_pig_thresholds(target: int = 50, dice: int = 1) -> dict[str, Any]:
    """Compute optimal hold thresholds for Pig dice race.
    Based on standard dynamic programming for Pig:
    - Baseline threshold for 1 die is ~20 points (or target - current_score).
    - For 2 dice (with snake eyes penalty), threshold is ~19 points.
    - If opponent is within 15 points of target, threshold expands aggressively.
    """
    base_threshold = 20 if dice == 1 else 19
    thresholds_by_score: dict[str, int] = {}

    for my_score in range(target):
        remaining = target - my_score
        thresh = min(base_threshold, remaining)
        thresholds_by_score[str(my_score)] = thresh

    return {
        "target": target,
        "dice": dice,
        "base_threshold": base_threshold,
        "thresholds_by_score": thresholds_by_score,
        "endgame_rule": "if banked + turn_total >= target: hold immediately",
        "behind_rule": "if opp_score >= target - 15: increase threshold by 5 (push luck)",
    }


def compute_grid_symmetries(size: int) -> dict[str, list[str]]:
    """Compute the 8 dihedral symmetries (D4 group) for each cell on an NxN grid.
    Reduces minimax and MCTS state evaluations by pruning symmetric branches.
    """
    symmetries: dict[str, list[str]] = {}

    for r in range(size):
        for c in range(size):
            cell = f"{chr(ord('A') + c)}{r + 1}"
            sym_cells = set()

            # 4 rotations + horizontal/vertical reflections
            transforms = [
                (r, c),  # Identity
                (c, size - 1 - r),  # Rot 90
                (size - 1 - r, size - 1 - c),  # Rot 180
                (size - 1 - c, r),  # Rot 270
                (r, size - 1 - c),  # Flip H
                (size - 1 - r, c),  # Flip V
                (c, r),  # Flip Main Diag
                (size - 1 - c, size - 1 - r),  # Flip Anti Diag
            ]

            for tr, tc in transforms:
                sym_cells.add(f"{chr(ord('A') + tc)}{tr + 1}")

            symmetries[cell] = sorted(list(sym_cells))

    return symmetries


def compute_heuristics(
    classification: GameClassification,
    grammar: ActionGrammar,
    rules_text: str,
) -> dict[str, Any]:
    """Compute opening books, dynamic programming tables, or heuristics for the game."""
    heuristics: dict[str, Any] = {
        "family": classification.family,
        "opening_moves": [],
        "strategy_hints": {},
    }

    family = classification.family
    params = grammar.parameters or {}

    if family == "grid_board":
        cols = grammar.grid_cols or 3
        rows = grammar.grid_rows or 3
        center_c = cols // 2
        center_r = rows // 2
        center_move = f"{chr(ord('A') + center_c)}{center_r + 1}"
        corners = ["A1", f"{chr(ord('A') + cols - 1)}1", f"A{rows}", f"{chr(ord('A') + cols - 1)}{rows}"]

        heuristics["opening_moves"] = [center_move] + corners
        heuristics["strategy_hints"] = {
            "center_move": center_move,
            "corners": corners,
            "priority": "center > corner > edge",
        }

        # Precompute symmetry equivalence classes if board is square
        if cols == rows:
            heuristics["symmetries"] = compute_grid_symmetries(cols)

    elif family == "dice_push":
        target = params.get("target_score", 50)
        dice = 2 if "two dice" in rules_text.lower() or "snake eyes" in rules_text.lower() else 1
        pig_tables = compute_pig_thresholds(target=target, dice=dice)

        heuristics["opening_moves"] = ["roll"]
        heuristics["strategy_hints"] = pig_tables

    elif family == "deduction":
        lo = grammar.numeric_min if grammar.numeric_min is not None else 1
        hi = grammar.numeric_max if grammar.numeric_max is not None else 100
        mid = (lo + hi) // 2
        opening = f"{grammar.numeric_prefix}{mid}".strip()

        heuristics["opening_moves"] = [opening]
        heuristics["strategy_hints"] = {
            "initial_guess": opening,
            "search_algorithm": "binary_search",
            "interval_min": lo,
            "interval_max": hi,
            "feedback_rules": {
                "higher": "lo = guess + 1",
                "lower": "hi = guess - 1",
                "correct": "found",
            },
        }

    elif family == "cards_hidden":
        heuristics["opening_moves"] = grammar.discrete_actions[:1] if grammar.discrete_actions else ["check"]
        heuristics["strategy_hints"] = {
            "game_theory": "kuhn_poker_nash",
            "bluff_frequency": 0.33,
            "value_bet": "bet strong hands, bluff weak hands 1/3, check medium",
        }

    elif family == "matrix_simultaneous":
        heuristics["opening_moves"] = grammar.discrete_actions[:1] if grammar.discrete_actions else []
        heuristics["strategy_hints"] = {
            "mixed_strategy": "uniform_random_or_counter_freq",
        }

    return heuristics
