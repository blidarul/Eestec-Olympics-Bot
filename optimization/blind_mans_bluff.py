"""Blind Man's Bluff Bayesian Odds & Pot Equity Engine.
Owned by agent `bld`. Rule 5.14, 8.1, 8.2 compliant.

Mathematical foundations:
Deck of N cards (1 to 10). Player sees opponent's card C_opp, but not their own.
Our card is drawn uniformly from {1..10} \\ {C_opp} (9 cards).
Number of cards beating C_opp: 10 - C_opp.
Exact showdown winning probability:
    P(win) = (10 - C_opp) / 9.

Pot Odds & Decision Thresholds:
1. Facing a Bet ('faced_bet': legal = ['call 1', 'fold']):
   Risk 1 chip to call into a pot of 3.
   Breakeven equity: P(win) * (+2) + (1 - P(win)) * (-2) > -1
       <=> 4 * P(win) > 1 <=> P(win) > 25.0%.
   P(win) > 25.0% holds whenever C_opp <= 7!
   - C_opp in {1, 2, 3, 4, 5, 6, 7}: CALL (P(win) >= 33.3%).
   - C_opp in {8, 9, 10}: FOLD (P(win) <= 22.2%).

2. Opening / Checking ('open': legal = ['check', 'bet 1']):
   - C_opp <= 5 (P(win) >= 55.6%): BET for value!
   - C_opp >= 6 (P(win) <= 44.4%): CHECK for pot control and free showdown.
"""
from __future__ import annotations

import re


def parse_bmb_obs(obs: str) -> dict:
    info = {
        "opp_card": 5,
        "max_rank": 10,
    }
    if not obs:
        return info

    m_card = re.search(r"OPPONENT'S CARD\s*(?:\([^)]*\))?:\s*(\d+)", obs, re.I)
    if m_card:
        info["opp_card"] = int(m_card.group(1))

    m_deck = re.search(r"(\d+)-card deck", obs, re.I)
    if m_deck:
        info["max_rank"] = int(m_deck.group(1))

    return info


def solve_blind_mans_bluff(legal: list[str] | None, observation: str = "", rules: str = "") -> str | None:
    if not legal:
        return "check"
    if len(legal) == 1:
        return legal[0]

    data = parse_bmb_obs(observation)
    opp_card = data["opp_card"]
    max_rank = data["max_rank"]

    # Showdown win probability: fraction of remaining cards strictly greater than opp_card
    cards_remaining = max(1, max_rank - 1)
    cards_higher = max(0, max_rank - opp_card)
    p_win = cards_higher / cards_remaining

    # Facing a bet: call 1 or fold
    if "call 1" in legal or "fold" in legal:
        # Breakeven pot odds: risk 1 to win pot of 3 -> need > 25% equity
        if p_win > 0.25:
            return "call 1"
        else:
            return "fold"

    # Open betting: check or bet 1
    if "bet 1" in legal or "check" in legal:
        # Value bet when equity > 50%
        if p_win > 0.50:
            return "bet 1"
        else:
            return "check"

    return legal[0]
