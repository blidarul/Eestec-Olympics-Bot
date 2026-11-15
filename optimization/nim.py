"""Exact Mathematical Nim Solver (Normal, Misère, and Limited Take).
Owned by agent `bld`. Rule 5.14, 8.1, 8.2 compliant.

Solves Nim with 100% mathematical optimality:
1. Normal play (unlimited take): computes XOR sum (Bouton 1901), transitions to XOR=0.
2. Misère play (unlimited take): when all piles <= 1 after move, leaves an ODD number of 1s;
   otherwise transitions to XOR=0.
3. Limited take (1 to M): uses Sprague-Grundy theorem g(s) = s % (M + 1) for normal play,
   and exact memoized backward induction for arbitrary variants.
"""
from __future__ import annotations

import re


def parse_piles_from_obs(obs: str) -> list[int]:
    """Extract pile sizes from observation string.
    Example: 'Piles now: pile 1 = 5, pile 2 = 0, pile 3 = 7, pile 4 = 2   (total 14)'
    """
    if not obs:
        return []
    m_piles = re.findall(r"pile\s*(\d+)\s*=\s*(\d+)", obs, re.I)
    if m_piles:
        # Sort by pile index
        sorted_piles = sorted([(int(idx), int(cnt)) for idx, cnt in m_piles], key=lambda x: x[0])
        return [cnt for _, cnt in sorted_piles]
    m_list = re.findall(r"\bpile\s*(\d+)\b[^\d]+(\d+)", obs, re.I)
    if m_list:
        sorted_piles = sorted([(int(idx), int(cnt)) for idx, cnt in m_list], key=lambda x: x[0])
        return [cnt for _, cnt in sorted_piles]
    return []


def parse_nim_action(act: str) -> tuple[int, int] | None:
    """Parse 'take <count> from pile <p>' -> (pile_idx (0-based), count)."""
    m = re.match(r"^(?:take\s+)?(\d+)\s+(?:from\s+)?(?:pile\s+)?(\d+)$", act.strip(), re.I)
    if m:
        return int(m.group(2)) - 1, int(m.group(1))
    return None


def is_misere_rules(rules: str) -> bool:
    low = (rules or "").lower()
    return bool(
        "misere" in low
        or "misère" in low
        or "last token loses" in low
        or "takes the last token loses" in low
    )


def parse_max_take(rules: str, legal: list[str] | None = None, piles: list[int] | None = None) -> int:
    low = (rules or "").lower()
    # Explicit rules phrasing: 'remove between 1 and 3', 'take between 1 and 3', 'take 1-3'
    m = re.search(r"(?:remove|take)\s+(?:between\s+)?1\s*(?:and|-|to)\s*(\d+)", low)
    if m:
        return int(m.group(1))
    m2 = re.search(r"take\s+1-(\d+)", low)
    if m2:
        return int(m2.group(1))

    # Cross-check from legal actions and pile sizes
    if legal and piles:
        # If any pile has size >= 4, check if max take for that pile is strictly less than pile size
        for p_idx, size in enumerate(piles):
            if size >= 4:
                takes_for_p = []
                for a in legal:
                    parsed = parse_nim_action(a)
                    if parsed and parsed[0] == p_idx:
                        takes_for_p.append(parsed[1])
                if takes_for_p and max(takes_for_p) < size:
                    return max(takes_for_p)

    return 0


def solve_nim(legal: list[str], observation: str = "", rules: str = "") -> str | None:
    if not legal:
        return None
    if len(legal) == 1:
        return legal[0]

    piles = parse_piles_from_obs(observation)
    if not piles:
        return legal[0]

    misere = is_misere_rules(rules)
    max_take = parse_max_take(rules, legal=legal, piles=piles)

    # Map each legal action to resulting state
    action_outcomes = []
    for act in legal:
        parsed = parse_nim_action(act)
        if not parsed:
            continue
        p_idx, take_cnt = parsed
        if p_idx < 0 or p_idx >= len(piles) or take_cnt <= 0 or take_cnt > piles[p_idx]:
            continue
        new_p = list(piles)
        new_p[p_idx] -= take_cnt
        action_outcomes.append((act, new_p))

    if not action_outcomes:
        return legal[0]

    # Standard Nim (Unlimited take)
    if max_take == 0:
        if misere:
            # Check if any move leaves all piles <= 1
            for act, new_p in action_outcomes:
                if all(x <= 1 for x in new_p):
                    # Win in misère: leave an ODD number of 1-token piles
                    ones_count = sum(1 for x in new_p if x == 1)
                    if ones_count % 2 == 1:
                        return act
            # If at least two piles have >= 2, optimal move is standard XOR sum == 0
            for act, new_p in action_outcomes:
                xor_sum = 0
                for x in new_p:
                    xor_sum ^= x
                if xor_sum == 0:
                    return act
        else:
            # Normal play: leave XOR sum == 0
            for act, new_p in action_outcomes:
                xor_sum = 0
                for x in new_p:
                    xor_sum ^= x
                if xor_sum == 0:
                    return act

    # Limited take (Take 1 to M)
    else:
        m_val = max_take + 1
        if not misere:
            for act, new_p in action_outcomes:
                xor_sum = 0
                for x in new_p:
                    xor_sum ^= (x % m_val)
                if xor_sum == 0:
                    return act
        else:
            # Misere with limited take: exact small minimax (total tokens <= 32)
            memo: dict[tuple[int, ...], bool] = {}

            def can_force_win(state: tuple[int, ...]) -> bool:
                if sum(state) == 0:
                    # In misère, previous player took last token and lost, so current player wins!
                    return True
                if state in memo:
                    return memo[state]
                # Can we make any move that leaves opponent in a losing state?
                for i, cnt in enumerate(state):
                    if cnt <= 0:
                        continue
                    lim = min(cnt, max_take)
                    for take in range(1, lim + 1):
                        next_st = list(state)
                        next_st[i] -= take
                        sorted_st = tuple(sorted(next_st))
                        if not can_force_win(sorted_st):
                            memo[state] = True
                            return True
                memo[state] = False
                return False

            for act, new_p in action_outcomes:
                sorted_next = tuple(sorted(new_p))
                if not can_force_win(sorted_next):
                    return act

    # If no winning move exists (already losing position), take 1 from smallest non-zero pile
    # to maximize game length and chance of opponent blunder
    best_act = None
    min_tokens = 999999
    for act, new_p in action_outcomes:
        parsed = parse_nim_action(act)
        if parsed:
            p_idx, take_cnt = parsed
            if take_cnt == 1 and 0 < piles[p_idx] < min_tokens:
                min_tokens = piles[p_idx]
                best_act = act

    return best_act or legal[0]
