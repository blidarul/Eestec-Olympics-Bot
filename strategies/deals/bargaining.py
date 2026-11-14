"""Reading and deciding bargaining games from text (no I/O, no randomness).

Alternating offers over a pot ("split 100 coins"), a deadline in rounds. Our plan: ask for a firm share first and
concede slowly towards a baseline that we never go below (the reservation value):
    demand(r) = total * (START_SHARE - (START_SHARE - RESERVATION_SHARE) * (r - 1) / (R - 1))
a non-increasing schedule from START_SHARE (60 percent) to RESERVATION_SHARE (40 percent) at the last round.
An offer is accepted when it is at least our current demand; an offer below the reservation is ALWAYS rejected.
The numbers stay inside this module and the strategy: nothing here ever reaches the chat.
"""
import re

START_SHARE = 0.60
RESERVATION_SHARE = 0.40

_TOTAL = re.compile(r"(?:split|divide|share|pot\s+of|total\s+of|between\s+you\s+and\s+the\s+opponent)\D{0,25}?(\d+)", re.I)
_TOTAL2 = re.compile(r"(\d+)\s*(?:coins?|points?|chips?|dollars?|units?|items?|tokens?|euros?)", re.I)
_ROUND_OF = re.compile(r"round\s+(\d+)\s*(?:of|/)\s*(\d+)", re.I)
_ROUND = re.compile(r"round\s+(\d+)", re.I)
_ROUNDS = re.compile(r"(\d+)\s+rounds", re.I)
_OFFER = re.compile(r"(?:offers?\s+you|offered\s+you|proposes?\s+(?:to\s+give\s+)?you|gives?\s+you|you\s+(?:would\s+)?(?:get|receive)|your\s+share(?:\s+(?:is|would\s+be))?)"
                    r"\D{0,14}(\d+)", re.I)


def parse_total(rules, observation):
    """The amount to share, or None."""
    for text in (rules or "", observation or ""):
        m = _TOTAL.search(text) or _TOTAL2.search(text)
        if m:
            return int(m.group(1))
    return None


def parse_round(observation, rules=""):
    """(current round, number of rounds) or (None, None) when unknown."""
    obs = observation or ""
    m = _ROUND_OF.search(obs)
    if m:
        return int(m.group(1)), max(int(m.group(2)), 1)
    cur = _ROUND.findall(obs)
    total = _ROUNDS.search(rules or "") or _ROUNDS.search(obs)
    if cur:
        return int(cur[-1]), int(total.group(1)) if total else None
    return None, int(total.group(1)) if total else None


def parse_offer_to_us(observation):
    """The amount the opponent's last proposal gives US, or None."""
    found = _OFFER.findall(observation or "")
    return int(found[-1]) if found else None


def demand(total, r, rounds):
    """What we ask for in round r of `rounds` (non-increasing, never below the reservation)."""
    if not total:
        return None
    reservation = total * RESERVATION_SHARE
    if not rounds or rounds <= 1 or not r:
        return round(total * START_SHARE)
    frac = min(max((r - 1) / (rounds - 1), 0.0), 1.0)
    return round(max(reservation, total * (START_SHARE - (START_SHARE - RESERVATION_SHARE) * frac)))


def reservation(total):
    return round(total * RESERVATION_SHARE) if total else None


def pick_action(legal, rules, total, r, rounds, offer):
    """(action, why) for a bargaining turn, or (None, "") when the legal actions are not bargaining actions."""
    by = {}
    for a in legal:
        low = a.lower()
        for key in ("accept", "reject", "offer", "propose", "counter"):
            if low.startswith(key):
                by.setdefault("offer" if key in ("offer", "propose", "counter") else key, []).append(a)
    if not by:
        return None, ""
    ask = demand(total, r, rounds)
    if offer is not None and ask is not None and "accept" in by:
        if offer >= ask:
            return by["accept"][0], "offer-meets-demand"
        if offer >= reservation(total) and r and rounds and r >= rounds:
            return by["accept"][0], "last-round-above-reservation"
    if offer is None and "accept" in by and r and rounds and r >= rounds:
        return by["accept"][0], "deadline-unknown-offer"
    counter = _closest_offer(by.get("offer", []), rules, total, ask)
    if counter:
        return counter, "counter"
    if "reject" in by:
        return by["reject"][0], "reject-below-demand"
    return None, ""


def _closest_offer(offers, rules, total, ask):
    """The legal "offer N" whose share for us is closest to our demand. N is our share unless the rules say N is what we give."""
    if not offers or ask is None or not total:
        return None
    gives = re.search(r"offer\s+(?:n|<n>|\d+)[^.]{0,50}(?:give|opponent'?s?\s+share|to\s+the\s+opponent)", rules or "", re.I)
    best, gap = None, None
    for a in offers:
        m = re.search(r"(\d+)", a)
        if not m:
            continue
        mine = total - int(m.group(1)) if gives else int(m.group(1))
        d = abs(mine - ask)
        if gap is None or d < gap:
            best, gap = a, d
    return best
