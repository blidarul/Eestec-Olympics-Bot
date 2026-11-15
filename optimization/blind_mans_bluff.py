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
        "hand_idx": 1,
        "hands_count": 5,
        "my_bank": 0,
        "opp_bank": 0,
    }
    if not obs:
        return info

    m_card = re.search(r"OPPONENT'S CARD\s*(?:\([^)]*\))?:\s*(\d+)", obs, re.I)
    if m_card:
        info["opp_card"] = int(m_card.group(1))

    m_deck = re.search(r"(\d+)-card deck", obs, re.I)
    if m_deck:
        info["max_rank"] = int(m_deck.group(1))

    m_hand = re.search(r"Hand\s*(\d+)\s*of\s*(\d+)", obs, re.I)
    if m_hand:
        info["hand_idx"] = int(m_hand.group(1))
        info["hands_count"] = int(m_hand.group(2))

    m_bank = re.search(r"Bank:\s*you\s*([+-]?\d+),\s*opp\s*([+-]?\d+)", obs, re.I)
    if m_bank:
        info["my_bank"] = int(m_bank.group(1))
        info["opp_bank"] = int(m_bank.group(2))

    return info


def solve_blind_mans_bluff(legal: list[str] | None, observation: str = "", rules: str = "") -> str | None:
    if not legal:
        return "check"
    if len(legal) == 1:
        return legal[0]

    data = parse_bmb_obs(observation)
    opp_card = data["opp_card"]
    max_rank = data["max_rank"]
    hand_idx = data["hand_idx"]
    hands_count = data["hands_count"]
    my_bank = data["my_bank"]
    opp_bank = data["opp_bank"]

    # Showdown win probability: fraction of remaining cards strictly greater than opp_card
    cards_remaining = max(1, max_rank - 1)
    cards_higher = max(0, max_rank - opp_card)
    p_win = cards_higher / cards_remaining

    # Facing a bet: call 1 or fold
    if "call 1" in legal or "fold" in legal:
        # Breakeven pot odds: risk 1 to win pot of 3 -> need > 25% equity (c_opp <= 7)
        # Protect lead on the final hand: if we are ahead by >= 3 chips, fold is completely safe
        if hand_idx == hands_count and my_bank - opp_bank >= 3:
            return "fold"

        if p_win > 0.25:
            return "call 1"
        else:
            return "fold"

    # Open betting (or facing a check): check or bet 1
    if "bet 1" in legal or "check" in legal:
        # Aggressive value and bluff betting:
        # Betting dominates checking whenever c_opp <= 7 (positive EV),
        # and bluffs out opponents who fold to bets.
        if p_win >= 0.30 or opp_card <= 7:
            return "bet 1"
        else:
            return "check"

    return legal[0]
