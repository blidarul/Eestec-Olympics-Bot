"""Precomputed Heuristics & Opening Books for 10-Minute Prep.
Precomputes lookup tables, optimal thresholds, and opening moves during the prep window.
Owned by agent `bld`.
"""
from __future__ import annotations

from typing import Any

from .action_parser import ActionGrammar
from .classifier import GameClassification


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

    if family == "grid_board":
        # Precompute grid opening moves based on center control
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

    elif family == "dice_push":
        # Pig dynamic programming threshold approximation:
        # Classical 1-die Pig optimal threshold is 20 (or target - current_banked)
        heuristics["opening_moves"] = ["roll"]
        heuristics["strategy_hints"] = {
            "default_hold_threshold": 20,
            "hold_condition": "turn_total >= 20 or (banked + turn_total >= target)",
            "risk_profile": "conservative_ahead_aggressive_behind",
        }

    elif family == "deduction":
        # Guess the number binary search
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
        }

    elif family == "matrix_simultaneous":
        heuristics["opening_moves"] = grammar.discrete_actions[:1] if grammar.discrete_actions else []
        heuristics["strategy_hints"] = {
            "mixed_strategy": "uniform_random_or_counter_freq",
        }

    return heuristics
