"""Sealed-Bid Auction Game-Theoretic Optimal Bidder (Vickrey and First-Price Shading).
Owned by agent `bld`. Rule 5.14, 8.1, 8.2 compliant.

Mathematical foundations:
1. Second-Price (Vickrey) Auction (Nobel Prize, Vickrey 1961):
   Truthful bidding b*(v) = v is a strictly dominant strategy. It maximizes profit while
   completely eliminating the Winner's Curse.
2. First-Price Auction (Bayesian Nash Equilibrium):
   For 2 bidders with independent private values distributed uniformly on [val_min, val_max]:
   b*(v) = val_min + (v - val_min) / 2 = (v + val_min) / 2.
   Bid shading guarantees that winning always yields non-negative profit: (v - b*(v)) >= 0.
   Overbidding opponents who bid above their valuations suffer catastrophic negative profits.
"""
from __future__ import annotations

import re


def parse_auction_obs(obs: str) -> dict:
    info = {
        "round": 1,
        "rounds": 5,
        "val_current": 50.0,
        "val_min": 10.0,
        "val_max": 100.0,
        "pricing": "second_price",
    }
    if not obs:
        return info

    m_v = re.search(r"YOUR PRIVATE VALUATION for this lot:\s*(\d+(?:\.\d+)?)", obs, re.I)
    if m_v:
        info["val_current"] = float(m_v.group(1))

    m_rule = re.search(r"Pricing rule:\s*(\w+)", obs, re.I)
    if m_rule:
        info["pricing"] = m_rule.group(1).lower()

    m_range = re.search(r"Valuation range:\s*\[\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\]", obs, re.I)
    if m_range:
        info["val_min"] = float(m_range.group(1))
        info["val_max"] = float(m_range.group(2))

    m_rnd = re.search(r"Round\s*(\d+)\s*of\s*(\d+)", obs, re.I)
    if m_rnd:
        info["round"] = int(m_rnd.group(1))
        info["rounds"] = int(m_rnd.group(2))

    return info


def solve_sealed_auction(legal: list[str] | None, observation: str = "", rules: str = "") -> str | None:
    data = parse_auction_obs(observation)
    v = data["val_current"]
    vmin = data["val_min"]
    pricing = data["pricing"]

    # Also check rules for pricing rule if obs was truncated
    if "first_price" in rules.lower() or "first-price" in rules.lower():
        pricing = "first_price"
    elif "second_price" in rules.lower() or "second-price" in rules.lower() or "vickrey" in rules.lower():
        pricing = "second_price"

    if pricing == "second_price":
        # Truthful bidding (Vickrey weak dominance)
        target_bid = v
    else:
        # First-price Nash equilibrium bid shading
        target_bid = (v + vmin) / 2.0

    if not legal:
        return f"bid {target_bid:.1f}"

    # Parse numerical bid values from legal actions
    parsed_legal = []
    for act in legal:
        m = re.search(r"(\d+(?:\.\d+)?)", act)
        if m:
            b_val = float(m.group(1))
            parsed_legal.append((act, b_val))

    if not parsed_legal:
        return legal[0]

    # In first-price auctions, strictly avoid any bid > v (which guarantees negative profit if won!)
    safe_legal = [item for item in parsed_legal if item[1] <= v]
    candidates = safe_legal if safe_legal else parsed_legal

    # Find the legal bid closest to target_bid
    best_act, _ = min(candidates, key=lambda item: abs(item[1] - target_bid))
    return best_act
