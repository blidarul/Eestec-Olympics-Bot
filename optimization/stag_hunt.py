"""Stag Hunt Game-Theoretic Coordinator & Risk-Dominance Evaluator.
Owned by agent `bld`. Rule 5.14, 8.1, 8.2 compliant.

Mathematical strategy:
1. Expected value threshold:
   Stag expected value: p_opp(Stag) * stag_payoff.
   Hare expected value: 3.0 (guaranteed).
   When p_opp(Stag) < 3.0 / stag_payoff (e.g. 0.60 for payoff=5), Hare strictly dominates in expectation.
2. Invariant Lead Protection:
   When we have a lead (my_score > opp_score) in the final rounds, playing 'hare' guarantees
   opponent net relative gain is <= 0 (if opp plays Hare: diff 0; if opp plays Stag: diff +3 for us).
   Victory is mathematically guaranteed.
3. Probing:
   Opens with 'stag' in round 1 to establish mutual coordination with cooperative bots.
"""
from __future__ import annotations

import re


def parse_stag_hunt_obs(obs: str) -> dict:
    info = {
        "round": 1,
        "max_rounds": 10,
        "my_score": 0,
        "opp_score": 0,
        "opp_stag_count": 0,
        "opp_hare_count": 0,
        "last_opp_move": None,
    }
    if not obs:
        return info

    m_rnd = re.search(r"Round\s*(\d+)/(\d+)", obs, re.I) or re.search(r"Round\s*(\d+)\s*of\s*(\d+)", obs, re.I)
    if m_rnd:
        info["round"] = int(m_rnd.group(1))
        info["max_rounds"] = int(m_rnd.group(2))

    m_sc = re.search(r"Total scores: you (\d+), opponent (\d+)", obs, re.I) or re.search(r"Scores: you (\d+), opponent (\d+)", obs, re.I)
    if m_sc:
        info["my_score"] = int(m_sc.group(1))
        info["opp_score"] = int(m_sc.group(2))

    # Parse round history
    # Example: 'Round 1: you stag (+5), opp stag (+5) -> mutual stag'
    rounds = re.findall(r"Round\s*(\d+):\s*you\s*(\w+)\s*\([^)]*\),\s*(?:opp|opponent)\s*(\w+)\s*\([^)]*\)", obs, re.I)
    for r in rounds:
        opp_m = r[2].lower()
        if "stag" in opp_m:
            info["opp_stag_count"] += 1
        elif "hare" in opp_m:
            info["opp_hare_count"] += 1
        info["last_opp_move"] = opp_m

    return info


def solve_stag_hunt(legal: list[str] | None, observation: str = "", rules: str = "") -> str | None:
    if not legal:
        legal = ["stag", "hare"]

    data = parse_stag_hunt_obs(observation)
    rnd = data["round"]
    max_rnd = data["max_rounds"]
    my_score = data["my_score"]
    opp_score = data["opp_score"]
    opp_stags = data["opp_stag_count"]
    opp_hares = data["opp_hare_count"]
    total_past = opp_stags + opp_hares

    # Payoff parsing
    m_sp = re.search(r"Both hunt STAG:\s*\+(\d+)", rules, re.I) or re.search(r"Stag bonus\s*\(\+(\d+)\)", rules, re.I)
    stag_payoff = int(m_sp.group(1)) if m_sp else 5

    # 1. Round 1: probe with stag
    if rnd == 1 or total_past == 0:
        target = "stag"
    # 2. Invariant Lead Protection:
    # If we have a lead and rounds remaining are few (<= 2), playing hare ensures opponent can never gain points on us
    elif my_score > opp_score and (max_rnd - rnd <= 2):
        target = "hare"
    # If we are far ahead (>= 4 points ahead), always play hare to lock the win
    elif my_score >= opp_score + 4:
        target = "hare"
    # 3. Opponent Bayesian estimation
    else:
        p_opp_stag = opp_stags / total_past
        threshold = 3.0 / stag_payoff  # 0.60 for 5, 0.50 for 6
        if p_opp_stag >= threshold + 0.05:
            # High trust coordination
            target = "stag"
        else:
            # Risk-dominant safe hare
            target = "hare"

    for act in legal:
        if act.lower().strip() == target or act.lower().strip().startswith(target[0]):
            return act

    return legal[0]
