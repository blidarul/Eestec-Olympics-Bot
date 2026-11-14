"""Plays Kuhn and Leduc poker from the precomputed equilibrium tables (no model, no search, a table lookup).

From the observation we need: our card, the community card (Leduc), our legal actions, and where we are in the hand
(the history key of cfr.py). The observation format is not fixed by the rules, so the history is found in this order:
  1. an action log of the current hand in the text ("you check, opponent bet ..."), read tolerantly;
  2. otherwise by DEDUCTION: every history of the table whose legal actions, whose acting seat (are we the first actor of
     this hand: seat 0 acts first in odd hands) and whose pot match what we see; if several remain, their strategies
     are averaged (never a guess against the rules: only histories that fit).
Exploitation is limited (see OpponentStats): a small, capped shift of probability between fold and call when the
opponent's opening frequency is clearly extreme and the sample is large enough. Against a balanced opponent nothing moves.
"""
import json
import os
import random
import re

from . import cfr

HERE = os.path.dirname(os.path.abspath(__file__))
WORDS = {"check": "c", "bet": "b", "call": "k", "raise": "r", "fold": "f"}
CARDS = {"j": "J", "jack": "J", "q": "Q", "queen": "Q", "k": "K", "king": "K"}
MAX_STEP = 0.04        # the most probability moved between fold and call (worst case +0.10 chips/hand of exploitability in Leduc)
MIN_SAMPLES = 30       # opening decisions of the opponent needed before any exploitation
DECAY = 0.995          # old observations fade slowly (a window of about 200 openings)

_TABLES = {}


def table(kind):
    """The strategy table of "kuhn" or "leduc" ({key: probabilities}), loaded once. {} when the file is missing."""
    if kind not in _TABLES:
        try:
            with open(os.path.join(HERE, f"table_{kind}.json"), encoding="utf-8") as fh:
                _TABLES[kind] = json.load(fh)["strategy"]
        except (OSError, ValueError, KeyError):
            _TABLES[kind] = {}
    return _TABLES[kind]


def is_poker(rules, observation, legal):
    """Is this Kuhn or Leduc poker? (rules or observation name the game or show the card lines and betting actions)."""
    text = f"{rules or ''}\n{observation or ''}".lower()
    if "kuhn" in text or "leduc" in text:
        return True
    acts = {a.lower().split()[0] for a in legal or []}
    return bool(re.search(r"your card", text)) and bool(acts & {"check", "bet", "call", "fold", "raise"})


def kind_of(rules, observation):
    text = f"{rules or ''}\n{observation or ''}".lower()
    return "leduc" if ("leduc" in text or "community" in text) else "kuhn"


def parse(observation):
    """{"card", "comm", "round", "pot", "hand", "log"} from the observation (None where unknown)."""
    obs = observation if isinstance(observation, str) else ""
    head = re.split(r"previous hands", obs, flags=re.I)[0]
    low = head.lower()
    card = re.search(r"your card:?\s*(jack|queen|king|[jqk])\b", low)
    comm = re.search(r"community card:?\s*(jack|queen|king|[jqk])\b", low)
    rnd = re.search(r"betting round\s*(\d)", low)
    pot = re.search(r"pot:?\s*(\d+)", low)
    hand = re.search(r"hand\s*#?\s*(\d+)", low)
    log = []
    for m in re.finditer(r"\b(you|opponent)\b[^.,;\n]{0,20}?\b(check|bet|call|raise|fold)(?:s|ed|ted)?\b", low):
        log.append((m.group(1), WORDS[m.group(2)]))
    return {"card": CARDS[card.group(1)] if card else None, "comm": CARDS[comm.group(1)] if comm else None,
            "round": int(rnd.group(1)) if rnd else (2 if comm else 1), "pot": int(pot.group(1)) if pot else None,
            "hand": int(hand.group(1)) if hand else None, "log": log}


def legal_codes(legal):
    """{code: the legal string} for our legal actions ("bet (puts in 4)" -> b)."""
    out = {}
    for a in legal or []:
        word = re.match(r"[a-z]+", str(a).lower())
        if word and word.group(0) in WORDS:
            out.setdefault(WORDS[word.group(0)], a)
    return out


def pot_after(game, hist):
    """Pot (both contributions) after the history, or None when the history is not legal."""
    pot0 = pot1 = 1
    rd, rh, player = 0, "", 0
    for a in hist:
        if a == "/":
            rd, rh, player = rd + 1, "", 0
            continue
        if a not in game.legal(rh) or rd >= game.rounds:
            return None
        if a != "f":
            bet = game.bets[rd]
            mine, opp = (pot0, pot1) if player == 0 else (pot1, pot0)
            add = {"c": 0, "b": bet, "r": (opp - mine) + bet, "k": opp - mine}[a]
            if player == 0:
                pot0 += add
            else:
                pot1 += add
        rh += a
        player = 1 - player
    return pot0 + pot1


def first_actor(seat, hand):
    """True if we act first in this hand (seat 0 acts first in odd hands), None if the hand number is unknown."""
    if hand is None or seat not in (0, 1):
        return None
    return (seat == 0) == (hand % 2 == 1)


def candidates(kind, info, codes, seat):
    """Keys of the table that fit what we see: our card, the community card, the round, the legal actions, the
    acting seat and the pot. Returns [(key, strategy over the node's legal actions in Game.legal order)]."""
    tab, game = table(kind), cfr.Game(kind == "leduc")
    first = first_actor(seat, info["hand"])
    out = []
    for key, probs in tab.items():
        card, comm, hist = key.split("|", 2)
        if card != info["card"] or comm != (info["comm"] or "-"):
            continue
        rounds_done = hist.count("/")
        if rounds_done + 1 != info["round"]:
            continue
        rh = hist.rsplit("/", 1)[-1]
        if set(game.legal(rh)) != set(codes):
            continue
        if first is not None and (len(rh) % 2 == 0) != first:
            continue
        pot = pot_after(game, hist)
        if pot is None or (info["pot"] is not None and pot != info["pot"]):
            continue
        out.append((key, probs))
    return out


def from_log(kind, info, codes):
    """The exact key when the observation has an action log that fits one table key, else None."""
    log = info["log"]
    if not log or not info["card"]:
        return None
    game, tab = cfr.Game(kind == "leduc"), table(kind)
    hist, rh = "", ""
    for _who, code in log:
        if code not in game.legal(rh):
            return None
        hist += code
        rh += code
        if code == "k" or rh == "cc":
            hist += "/"
            rh = ""
    key = cfr.key_of(info["card"], info["comm"], hist)
    probs = tab.get(key)
    return (key, probs) if probs and set(game.legal(rh)) == set(codes) else None


class OpponentStats:
    """Counts how often the opponent opens with a bet (seen from our own legal sets), with decay. Limited exploitation."""

    def __init__(self):
        self.bets = 0.0
        self.opens = 0.0

    def see_open(self, bet):
        self.bets = self.bets * DECAY + (1.0 if bet else 0.0)
        self.opens = self.opens * DECAY + 1.0

    @property
    def rate(self):
        return self.bets / self.opens if self.opens else 0.5

    def shift(self):
        """How much probability to move from fold to call (positive) or call to fold (negative), capped at MAX_STEP."""
        if self.opens < MIN_SAMPLES:
            return 0.0
        step = min(MAX_STEP, 0.0004 * (self.opens - MIN_SAMPLES + 1))
        if self.rate >= 0.6:
            return step           # opens with a bet very often: many bluffs, call more
        if self.rate <= 0.15:
            return -step          # almost never opens with a bet: it means a strong hand, fold marginal calls more
        return 0.0


def apply_shift(order, probs, shift):
    """Move `shift` of the probability between fold and call (never touches raise); a no-op without both actions."""
    if not shift or "f" not in order or "k" not in order:
        return list(probs)
    p = list(probs)
    i, j = order.index("f"), order.index("k")
    if p[i] < 0.02 or p[j] < 0.02:
        return p       # only MIXED spots move: a King still always calls and a Jack still always folds
    if shift > 0:
        moved = min(shift, p[i])
        p[i] -= moved
        p[j] += moved
    else:
        moved = min(-shift, p[j])
        p[j] -= moved
        p[i] += moved
    return p


def decide(rules, observation, legal, seat, stats, rng):
    """(action string from `legal`, "log"/"deduced"/"averaged") or None when the table cannot answer."""
    codes = legal_codes(legal)
    if not codes:
        return None
    kind = kind_of(rules, observation)
    info = parse(observation)
    if not info["card"] or not table(kind):
        return None
    game = cfr.Game(kind == "leduc")
    exact = from_log(kind, info, codes)
    found = [exact] if exact else candidates(kind, info, codes, seat)
    if not found:
        return None
    order = game.legal(next(iter(found))[0].split("|", 2)[2].rsplit("/", 1)[-1])
    avg = [sum(p[i] for _k, p in found) / len(found) for i in range(len(order))]
    first = first_actor(seat, info["hand"])
    if first is False and set(codes) == {"c", "b"} and info["round"] == 1:   # second actor facing an open: a free observation
        stats.see_open(False)
    if set(codes) == {"f", "k"} or set(codes) == {"f", "k", "r"}:
        if info["round"] == 1 and (first is False or first is None):
            stats.see_open(True)
        avg = apply_shift(order, avg, stats.shift())
    pick = rng.random()
    acc = 0.0
    for code, pr in zip(order, avg):
        acc += pr
        if pick <= acc and code in codes:
            return codes[code], "log" if exact else ("deduced" if len(found) == 1 else "averaged")
    return codes[next(c for c in order if c in codes)], "log" if exact else "averaged"
