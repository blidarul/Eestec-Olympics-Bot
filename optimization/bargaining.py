"""Rubinstein Bargaining Game-Theoretic Strategist.
Owned by agent `bld`. Rule 5.14, 8.1, 8.2 compliant.

Key strategic imperatives:
1. Winner Determination Invariant:
   In this arena, game winner is determined strictly by coin count:
   payouts[0] > payouts[1] -> seat 0 wins; payouts[1] > payouts[0] -> seat 1 wins.
   Therefore, NEVER accept an offer where offered_to_me < offered_to_proposer (e.g. 40 vs 60),
   as accepting is an IMMEDIATE FORFEIT LOSS!
   Accepting 0-0 at timeout is a draw (0.5 points), strictly better than accepting a losing split (0 points).
2. Acceptance Criterion:
   - Accept IF offered_to_me > offered_to_proposer (WIN!).
   - Accept IF offered_to_me == offered_to_proposer (DRAW!).
   - Otherwise, reject and counter-offer.
3. Proposal Strategy:
   - Early rounds: propose 60-40 split (we get 60, opp gets 40). If opp accepts, we win!
   - Final round: propose 50-50 split to maximize mutual agreement and avoid timeout.
"""
from __future__ import annotations

import re


def parse_bargaining_obs(obs: str) -> dict:
    info = {
        "round": 1,
        "max_rounds": 5,
        "current_pot": 100,
        "pending_offer": None,  # (proposer_share, my_share)
    }
    if not obs:
        return info

    m_rnd = re.search(r"Round\s*(\d+)\s*of\s*(\d+)", obs, re.I)
    if m_rnd:
        info["round"] = int(m_rnd.group(1))
        info["max_rounds"] = int(m_rnd.group(2))

    m_pot = re.search(r"Current pot size:\s*(\d+)", obs, re.I)
    if m_pot:
        info["current_pot"] = int(m_pot.group(1))

    # PENDING OFFER from Player 1: offers you 40 coins (keeps 60 coins).
    m_off = re.search(r"offers you\s*(\d+)\s*coins\s*\(keeps\s*(\d+)\s*coins\)", obs, re.I)
    if m_off:
        my_share = int(m_off.group(1))
        proposer_share = int(m_off.group(2))
        info["pending_offer"] = (proposer_share, my_share)

    return info


def solve_bargaining(legal: list[str] | None, observation: str = "", rules: str = "") -> str | None:
    if not legal:
        return "offer 60 40"
    if len(legal) == 1:
        return legal[0]

    data = parse_bargaining_obs(observation)
    rnd = data["round"]
    max_rnd = data["max_rounds"]
    pot = data["current_pot"]
    pending = data["pending_offer"]

    # 1. Acceptance decision:
    if "accept" in legal and pending is not None:
        proposer_share, my_share = pending
        if my_share >= proposer_share:
            # We either win (my_share > proposer_share) or draw (50-50). Accept!
            return "accept"
        # Otherwise my_share < proposer_share: accepting guarantees a loss!
        # Reject by counter-offering.

    # 2. Proposal / Counter-offer decision:
    # Filter offers from legal actions
    offers = [a for a in legal if a.lower().startswith("offer ")]
    if not offers:
        return legal[0]

    parsed_offers = []
    for act in offers:
        m = re.findall(r"\d+", act)
        if len(m) >= 2:
            my_s = int(m[0])
            opp_s = int(m[1])
            parsed_offers.append((act, my_s, opp_s))

    if not parsed_offers:
        return offers[0]

    # In final round: prefer 50-50 split for maximum acceptance probability
    if rnd >= max_rnd:
        equal_offers = [item for item in parsed_offers if item[1] == item[2]]
        if equal_offers:
            return equal_offers[0][0]

    # In early / mid rounds: prefer 60-40 split (we get 60, opp gets 40)
    advantage_offers = [item for item in parsed_offers if item[1] > item[2]]
    if advantage_offers:
        # Prefer the lowest advantage that still wins (e.g. 60-40 rather than greedy 80-20)
        advantage_offers.sort(key=lambda item: item[1])
        return advantage_offers[0][0]

    # Fallback to equal split if no advantage offer available
    equal_offers = [item for item in parsed_offers if item[1] >= item[2]]
    if equal_offers:
        return equal_offers[0][0]

    return offers[0]
