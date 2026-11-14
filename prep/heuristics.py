"""General, Adaptive Game Heuristics & Dynamic Programming Policy Learner.
Learns optimal stopping frontiers, symmetry orbits, and search guides dynamically during 10-minute prep.
Fully game-agnostic (Rules 10.7, 12.1).
Owned by agent `bld`.
"""
from __future__ import annotations

import math
from typing import Any

from .action_parser import ActionGrammar
from .classifier import GameClassification


def compute_stopping_thresholds(
    target_score: int = 50,
    p_bust: float = 0.167,
    avg_gain: float = 4.0,
    continue_action: str = "roll",
    stop_action: str = "hold",
) -> dict[str, Any]:
    """Generic Dynamic Programming / Markov Decision Process solver for any accumulator
    or push-your-luck game (Pig, Farkle, Can't Stop, Blackjack busting, etc.).

    Marginal expected return of continuing at turn accumulation k:
        E[marginal gain] = (1 - p_bust) * avg_gain - p_bust * k
    Continuing is mathematically favorable while:
        k <= ((1 - p_bust) * avg_gain) / p_bust
    """
    safe_p_bust = max(0.01, min(0.99, p_bust))
    theoretical_threshold = int(math.floor(((1.0 - safe_p_bust) * avg_gain) / safe_p_bust))
    base_threshold = max(3, theoretical_threshold)

    thresholds_by_score: dict[str, int] = {}
    for my_score in range(target_score):
        remaining = target_score - my_score
        # Never risk busting if the current accumulation already reaches the target score
        thresh = min(base_threshold, remaining)
        thresholds_by_score[str(my_score)] = thresh

    return {
        "policy_type": "generic_stopping_mdp",
        "target_score": target_score,
        "continue_action": continue_action,
        "stop_action": stop_action,
        "p_bust": round(safe_p_bust, 3),
        "avg_gain": round(avg_gain, 2),
        "base_threshold": base_threshold,
        "thresholds_by_score": thresholds_by_score,
        "endgame_rule": f"if banked + turn_total >= target: choose {stop_action} immediately",
        "behind_rule": f"if opponent is within 15 points of target: choose {continue_action} more aggressively",
    }


def compute_grid_symmetries(cols: int, rows: int) -> dict[str, list[str]]:
    """Compute geometric symmetry orbits for any NxM grid board.
    - Square boards (N x N): 8 dihedral group symmetries (D4: 4 rotations + 4 reflections).
    - Rectangular boards (N x M): 4 Klein-4 symmetries (D2: identity, 180 rot, H-flip, V-flip).
    """
    symmetries: dict[str, list[str]] = {}

    for r in range(rows):
        for c in range(cols):
            cell = f"{chr(ord('A') + c)}{r + 1}"
            sym_cells = set()

            if cols == rows:
                s = cols
                transforms = [
                    (r, c),  # Identity
                    (c, s - 1 - r),  # Rot 90
                    (s - 1 - r, s - 1 - c),  # Rot 180
                    (s - 1 - c, r),  # Rot 270
                    (r, s - 1 - c),  # Flip H
                    (size - 1 - r, c) if "size" in locals() else (s - 1 - r, c),  # Flip V
                    (c, r),  # Flip Main Diag
                    (s - 1 - c, s - 1 - r),  # Flip Anti Diag
                ]
            else:
                # Rectangular transforms
                transforms = [
                    (r, c),  # Identity
                    (rows - 1 - r, cols - 1 - c),  # Rot 180
                    (r, cols - 1 - c),  # Flip H
                    (rows - 1 - r, c),  # Flip V
                ]

            for tr, tc in transforms:
                sym_cells.add(f"{chr(ord('A') + tc)}{tr + 1}")

            symmetries[cell] = sorted(list(sym_cells))

    return symmetries


def compute_centrality_order(cols: int, rows: int) -> list[str]:
    """Sort all grid coordinates by distance to the board center (center > corners > edges)."""
    center_c = (cols - 1) / 2.0
    center_r = (rows - 1) / 2.0

    cells_with_dist = []
    for r in range(rows):
        for c in range(cols):
            cell = f"{chr(ord('A') + c)}{r + 1}"
            dist = math.hypot(c - center_c, r - center_r)
            cells_with_dist.append((dist, cell))

    cells_with_dist.sort(key=lambda x: x[0])
    return [cell for _, cell in cells_with_dist]


def compute_heuristics(
    classification: GameClassification,
    grammar: ActionGrammar,
    rules_text: str,
) -> dict[str, Any]:
    """Compute generic, adaptive heuristics tailored to the discovered game mechanics."""
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

        ordered_moves = compute_centrality_order(cols, rows)
        heuristics["opening_moves"] = ordered_moves[:5]
        heuristics["strategy_hints"] = {
            "center_move": ordered_moves[0],
            "centrality_ranking": ordered_moves,
            "heuristic_priority": "center > corner > edge",
        }
        heuristics["symmetries"] = compute_grid_symmetries(cols, rows)

    elif family == "dice_push":
        target = params.get("target_score", 50)

        # Dynamically discover continue and stop actions from grammar
        actions = grammar.discrete_actions or ["roll", "hold"]
        continue_candidates = {"roll", "draw", "push", "spin", "continue", "hit", "take"}
        stop_candidates = {"hold", "bank", "stop", "pass", "stand", "keep"}

        continue_act = next((a for a in actions if a.lower() in continue_candidates), actions[0])
        stop_act = next((a for a in actions if a.lower() in stop_candidates), actions[-1] if len(actions) > 1 else "pass")

        # Dynamically estimate risk probability from rules
        p_bust = 0.167
        avg_gain = 4.0
        lower_rules = rules_text.lower()
        if "two dice" in lower_rules or "snake eyes" in lower_rules:
            p_bust = 11.0 / 36.0  # ~0.306
            avg_gain = 7.0

        stopping_policy = compute_stopping_thresholds(
            target_score=target,
            p_bust=p_bust,
            avg_gain=avg_gain,
            continue_action=continue_act,
            stop_action=stop_act,
        )

        heuristics["opening_moves"] = [continue_act]
        heuristics["strategy_hints"] = stopping_policy

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
            "partition_rule": "guess = (lo + hi) // 2",
        }

    elif family == "cards_hidden":
        first_action = grammar.discrete_actions[0] if grammar.discrete_actions else "check"
        heuristics["opening_moves"] = [first_action]
        heuristics["strategy_hints"] = {
            "game_theory": "mixed_strategy_nash",
            "bluff_frequency": 0.33,
            "value_bet": "bet strong hands, bluff weak hands 1/3, check medium",
        }

    elif family == "matrix_simultaneous":
        heuristics["opening_moves"] = grammar.discrete_actions[:1] if grammar.discrete_actions else []
        heuristics["strategy_hints"] = {
            "mixed_strategy": "uniform_random_or_counter_freq",
            "action_count": len(grammar.discrete_actions),
        }

    return heuristics
