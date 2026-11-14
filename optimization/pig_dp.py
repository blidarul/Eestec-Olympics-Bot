"""Exact Dynamic Programming Policy Solver for Pig (1 die and 2 dice variants).
Solves Bellman optimality equations via backward induction on turn totals
and value iteration across banked score state space (my_score, opp_score).
Owned by agent `bld`.
"""
from __future__ import annotations

import sys
import time
from typing import Any


def compute_pig_thresholds(
    target_score: int = 50,
    num_dice: int = 1,
    snake_eyes_reset: bool = False,
    max_iterations: int = 25,
    tolerance: float = 5e-4,
) -> list[list[int]]:
    """Compute exact threshold table T[i][j] where i=my_score, j=opp_score.
    T[i][j] is the minimum turn_points k at which holding is optimal over rolling.
    """
    T = target_score
    V = [[float(i) / float(T) for j in range(T)] for i in range(T)]

    # 2 dice distribution precomputation
    # Roll distribution: list of (prob, outcome_type, value)
    # outcome_type: 'bust_turn' (turn lost), 'bust_all' (score reset), 'gain'
    two_dice_rolls = []
    if num_dice == 2:
        for d1 in range(1, 7):
            for d2 in range(1, 7):
                if d1 == 1 and d2 == 1:
                    two_dice_rolls.append((1.0 / 36.0, "bust_all" if snake_eyes_reset else "bust_turn", 0))
                elif d1 == 1 or d2 == 1:
                    two_dice_rolls.append((1.0 / 36.0, "bust_turn", 0))
                else:
                    two_dice_rolls.append((1.0 / 36.0, "gain", d1 + d2))

    t0 = time.monotonic()
    for iteration in range(max_iterations):
        diff = 0.0
        V_next = [[0.0] * T for _ in range(T)]

        for i in range(T):
            for j in range(T):
                max_k = T - i
                P = [1.0] * (max_k + 15)

                if num_dice == 1:
                    opp_bust_val = (1.0 - V[j][i]) / 6.0
                    for k in range(max_k - 1, -1, -1):
                        v_hold = 1.0 - (V[j][i + k] if (i + k) < T else 0.0)
                        v_roll = opp_bust_val + sum(P[k + r] for r in range(2, 7)) / 6.0
                        P[k] = v_hold if v_hold > v_roll else v_roll
                else:
                    for k in range(max_k - 1, -1, -1):
                        v_hold = 1.0 - (V[j][i + k] if (i + k) < T else 0.0)
                        v_roll = 0.0
                        for prob, o_type, val in two_dice_rolls:
                            if o_type == "bust_all":
                                v_roll += prob * (1.0 - V[j][0])
                            elif o_type == "bust_turn":
                                v_roll += prob * (1.0 - V[j][i])
                            else:
                                v_roll += prob * P[k + val]
                        P[k] = v_hold if v_hold > v_roll else v_roll

                v_new = P[0]
                delta = abs(v_new - V[i][j])
                if delta > diff:
                    diff = delta
                V_next[i][j] = v_new

        V = V_next
        if diff < tolerance:
            break

    dt = time.monotonic() - t0
    print(f"[pig_dp] converged in {iteration + 1} iterations ({dt:.2f}s, target={T}, dice={num_dice})", file=sys.stderr)

    # Derive optimal threshold table: smallest k where v_hold >= v_roll
    thresholds = [[0] * T for _ in range(T)]
    for i in range(T):
        for j in range(T):
            max_k = T - i
            P = [1.0] * (max_k + 15)
            # Find backward values
            if num_dice == 1:
                opp_bust_val = (1.0 - V[j][i]) / 6.0
                for k in range(max_k - 1, -1, -1):
                    v_hold = 1.0 - (V[j][i + k] if (i + k) < T else 0.0)
                    v_roll = opp_bust_val + sum(P[k + r] for r in range(2, 7)) / 6.0
                    P[k] = v_hold if v_hold > v_roll else v_roll
            else:
                for k in range(max_k - 1, -1, -1):
                    v_hold = 1.0 - (V[j][i + k] if (i + k) < T else 0.0)
                    v_roll = 0.0
                    for prob, o_type, val in two_dice_rolls:
                        if o_type == "bust_all":
                            v_roll += prob * (1.0 - V[j][0])
                        elif o_type == "bust_turn":
                            v_roll += prob * (1.0 - V[j][i])
                        else:
                            v_roll += prob * P[k + val]
                    P[k] = v_hold if v_hold > v_roll else v_roll

            # Find first k where hold >= roll
            best_thresh = max_k
            if num_dice == 1:
                opp_bust_val = (1.0 - V[j][i]) / 6.0
                for k in range(max_k):
                    v_hold = 1.0 - (V[j][i + k] if (i + k) < T else 0.0)
                    v_roll = opp_bust_val + sum(P[k + r] for r in range(2, 7)) / 6.0
                    if v_hold >= v_roll:
                        best_thresh = k
                        break
            else:
                for k in range(max_k):
                    v_hold = 1.0 - (V[j][i + k] if (i + k) < T else 0.0)
                    v_roll = 0.0
                    for prob, o_type, val in two_dice_rolls:
                        if o_type == "bust_all":
                            v_roll += prob * (1.0 - V[j][0])
                        elif o_type == "bust_turn":
                            v_roll += prob * (1.0 - V[j][i])
                        else:
                            v_roll += prob * P[k + val]
                    if v_hold >= v_roll:
                        best_thresh = k
                        break

            thresholds[i][j] = best_thresh

    return thresholds


def query_pig_action(
    thresholds: list[list[int]],
    my_score: int,
    opp_score: int,
    turn_points: int,
    target_score: int = 50,
) -> str:
    """Decide 'bank' or 'roll' using the DP threshold table."""
    if my_score + turn_points >= target_score:
        return "bank"
    if my_score < 0:
        my_score = 0
    if opp_score < 0:
        opp_score = 0
    T = target_score
    if my_score >= T:
        return "bank"
    if opp_score >= T:
        opp_score = T - 1

    limit = thresholds[my_score][opp_score] if (my_score < len(thresholds) and opp_score < len(thresholds[my_score])) else 20
    if turn_points >= limit:
        return "bank"
    return "roll"
