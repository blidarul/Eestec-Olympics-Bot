"""Exact Probabilistic Solver for Liar's Dice (Bluff Family).

Calculates exact binomial probabilities for claims given hidden dice,
identifies bluffing opportunities, optimal raises, and profitable challenges.
"""
from __future__ import annotations

import math
import re
from typing import Sequence

_DICE_RE = re.compile(r"YOUR HIDDEN DICE:\s*\[([0-9,\s]+)\]", re.IGNORECASE)
_COUNTS_RE = re.compile(r"you have\s+(\d+)\s+dice,\s+opponent has\s+(\d+)\s+dice", re.IGNORECASE)
_BID_RE = re.compile(r"Current bid on table:\s*(\d+)\s+of\s+([1-6])", re.IGNORECASE)
_NO_BID_RE = re.compile(r"Current bid on table:\s*None", re.IGNORECASE)


def binom_survival(n: int, needed: int, p: float) -> float:
    """Calculates P(X >= needed) for X ~ Binomial(n, p)."""
    if needed <= 0:
        return 1.0
    if needed > n:
        return 0.0
    total = 0.0
    for j in range(needed, n + 1):
        c = math.comb(n, j)
        total += c * (p ** j) * ((1.0 - p) ** (n - j))
    return total


def parse_liars_dice_state(observation: str, rules_text: str = "") -> dict:
    """Parses observation and rules to extract game state."""
    # 1. My hidden dice
    my_dice = []
    m_dice = _DICE_RE.search(observation)
    if m_dice:
        my_dice = [int(x.strip()) for x in m_dice.group(1).split(",") if x.strip().isdigit()]

    # 2. Dice counts
    my_count = len(my_dice)
    opp_count = my_count
    m_counts = _COUNTS_RE.search(observation)
    if m_counts:
        my_count = int(m_counts.group(1))
        opp_count = int(m_counts.group(2))

    # 3. Current bid
    current_bid = None
    m_bid = _BID_RE.search(observation)
    if m_bid:
        current_bid = (int(m_bid.group(1)), int(m_bid.group(2)))

    # 4. Ones wild?
    combined = (rules_text + " " + observation).lower()
    ones_wild = (
        "ones wild" in combined
        or "ones (1s) are wild" in combined
        or "1s are wild" in combined
        or "ones are wild" in combined
    )

    return {
        "my_dice": my_dice,
        "my_count": my_count,
        "opp_count": opp_count,
        "current_bid": current_bid,
        "ones_wild": ones_wild,
    }


def solve_liars_dice(
    observation: str,
    rules_text: str = "",
    legal_actions: Sequence[str] | None = None,
) -> str | None:
    """Determines the optimal action (bid or liar) given the state."""
    state = parse_liars_dice_state(observation, rules_text)
    my_dice = state["my_dice"]
    opp_count = state["opp_count"]
    current_bid = state["current_bid"]
    ones_wild = state["ones_wild"]

    if not my_dice and opp_count <= 0:
        return None

    # Count our own dice for each face 1..6
    def count_my_matches(face: int) -> int:
        if ones_wild and face != 1:
            return sum(1 for d in my_dice if d == face or d == 1)
        return sum(1 for d in my_dice if d == face)

    def p_face(face: int) -> float:
        if ones_wild and face != 1:
            return 2.0 / 6.0  # 1 or face
        return 1.0 / 6.0

    def claim_probability(count: int, face: int) -> float:
        my_matches = count_my_matches(face)
        needed = count - my_matches
        p = p_face(face)
        return binom_survival(opp_count, needed, p)

    # 1. Opening bid (no current bid)
    if current_bid is None:
        # Evaluate opening candidates across all faces 1..6
        best_face = 6
        best_count = 1
        best_score = -1.0

        for f in range(1, 7):
            matches = count_my_matches(f)
            # Preference towards faces where we hold multiple matching dice
            exp_opp = opp_count * p_face(f)
            est_total = matches + exp_opp
            # Choose a bid with high probability (>= 0.70)
            target_count = max(1, matches)
            prob = claim_probability(target_count, f)
            # Score: higher probability and higher count
            score = prob * 10.0 + est_total
            if score > best_score:
                best_score = score
                best_face = f
                best_count = target_count

        bid_act = f"bid {best_count} {best_face}"
        if legal_actions and bid_act not in legal_actions:
            # Fall back to any legal bid
            for act in legal_actions:
                if act.startswith("bid "):
                    return act
        return bid_act

    # 2. Existing bid on table: evaluate calling 'liar' vs raising
    curr_count, curr_face = current_bid
    p_curr_true = claim_probability(curr_count, curr_face)

    # Find candidate legal raises
    candidate_raises: list[tuple[float, int, int]] = []
    # Option A: Same count, higher face
    if curr_face < 6:
        for f in range(curr_face + 1, 7):
            p = claim_probability(curr_count, f)
            candidate_raises.append((p, curr_count, f))

    # Option B: Count + 1, any face 1..6
    total_dice = len(my_dice) + opp_count
    if curr_count + 1 <= total_dice:
        for f in range(1, 7):
            p = claim_probability(curr_count + 1, f)
            candidate_raises.append((p, curr_count + 1, f))

    # Sort candidate raises by probability descending, then count ascending
    candidate_raises.sort(key=lambda x: (x[0], -x[1]), reverse=True)

    # Threshold for challenging:
    # If the current bid has probability < 0.35, calling liar is EV positive (> 65% win)
    # BUT if we have NO decent raises (all raises < 0.25), challenge threshold relaxes
    best_raise_p = candidate_raises[0][0] if candidate_raises else 0.0

    # If current bid is guaranteed false or very unlikely:
    if p_curr_true < 0.36 or (p_curr_true < 0.50 and best_raise_p < 0.28):
        return "liar"

    # If we have a viable raise with probability >= 0.30:
    if candidate_raises and best_raise_p >= 0.28:
        _, b_cnt, b_fc = candidate_raises[0]
        act = f"bid {b_cnt} {b_fc}"
        if legal_actions:
            if act in legal_actions:
                return act
            # Check other candidates in legal_actions
            for p, c, f in candidate_raises:
                cand_act = f"bid {c} {f}"
                if cand_act in legal_actions:
                    return cand_act
            # If no candidate raise is in legal_actions, call liar if legal
            if "liar" in legal_actions:
                return "liar"
        return act

    # Default fallback: challenge
    return "liar"
