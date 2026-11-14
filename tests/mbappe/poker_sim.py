"""Kuhn / Leduc simulator with the arena rules, used to measure the poker player (chips per hand, with confidence interval).

Rules (from the T1 games): ante 1; Kuhn bet 1, one betting round, no raise; Leduc bet 2 in round 1 and 4 in round 2, one
bet and one raise at most per round, community card after round 1, a pair with it wins; the player who acts first in a hand
alternates (seat 0 first in odd hands). The observation text is built in a plausible format with or without an action log.
"""
import itertools
import math
import random

import _path  # noqa: F401
from strategies.bluff.poker import cfr as C
from strategies.bluff.poker import player as P

NAME = {"J": "Jack", "Q": "Queen", "K": "King"}
WORD = {"c": "check", "b": "bet", "k": "call", "r": "raise", "f": "fold"}


class Hand:
    """One hand: cards, history, pots. Seats are the real seats; `first` is who acts first."""

    def __init__(self, leduc, first, rng):
        self.game = C.Game(leduc)
        deck = list(self.game.deck)
        rng.shuffle(deck)
        self.cards = {first: deck[0], 1 - first: deck[1]}
        self.comm = deck[2] if leduc else None
        self.first = first
        self.rd, self.rh, self.hist = 0, "", ""
        self.pots = {0: 1, 1: 1}
        self.actor = first
        self.over = False
        self.winner = None
        self.log = []

    def legal(self):
        return self.game.legal(self.rh)

    def act(self, code):
        g = self.game
        bet = g.bets[self.rd]
        me, other = self.actor, 1 - self.actor
        self.log.append((me, code))
        if code == "f":
            self.over, self.winner = True, other
            return
        add = {"c": 0, "b": bet, "r": (self.pots[other] - self.pots[me]) + bet, "k": self.pots[other] - self.pots[me]}[code]
        self.pots[me] += add
        self.rh += code
        self.hist += code
        if code == "k" or self.rh == "cc":
            self.hist += "/"
            if self.rd + 1 < g.rounds:
                self.rd, self.rh, self.actor = self.rd + 1, "", self.first
                return
            self.over = True
            first, second = self.first, 1 - self.first
            s = g.showdown(self.cards[first], self.cards[second], self.comm)
            self.winner = first if s == 1 else (second if s == -1 else None)
            return
        self.actor = other

    def chips(self, seat):
        """Chips won by `seat` (negative = lost)."""
        if self.winner is None:
            return 0
        return self.pots[1 - seat] if self.winner == seat else -self.pots[seat]

    def key(self, seat):
        return C.key_of(self.cards[seat], self.comm if self.rd == 1 else None, self.hist)

    def observation(self, seat, number, total, with_log):
        lines = [f"MINI POKER ({'Leduc' if self.game.leduc else 'Kuhn'}). Hand {number} of {total}. You are seat {seat}.",
                 f"Your card: {self.cards[seat]} ({NAME[self.cards[seat]]})"]
        if self.comm and self.rd == 1:
            lines.append(f"Community card: {self.comm} ({NAME[self.comm]})")
        lines.append(f"Pot: {sum(self.pots.values())}")
        if with_log and self.log:
            lines.append("Betting this hand: " + ", ".join(f"{'you' if s == seat else 'opponent'} {WORD[c]}" for s, c in self.log))
        lines.append(f"It is your turn in betting round {self.rd + 1}.")
        legal = [WORD[a] + (f" (puts in {self.game.bets[self.rd]})" if a in "br" else "") for a in self.legal()]
        lines.append("Legal actions: " + ", ".join(legal))
        lines.append("Previous hands:\n  (none)")
        return "\n".join(lines), [WORD[a] for a in self.legal()], legal


def adversary(kind, table=None):
    """Returns f(hand, seat, rng) -> code for a scripted opponent."""
    def play(h, seat, rng):
        legal = h.legal()
        if kind == "random":
            return rng.choice(legal)
        if kind == "always_call":
            return "k" if "k" in legal else "c"
        if kind == "always_raise":
            return "r" if "r" in legal else ("b" if "b" in legal else "k")
        if kind == "bluffer":      # bets and raises with everything weak, calls with the rest
            weak = C.RANK[h.cards[seat]] == 0
            if weak and "b" in legal:
                return "b"
            if "r" in legal and C.RANK[h.cards[seat]] == 2:
                return "r"
            return "k" if "k" in legal else ("c" if "c" in legal else legal[0])
        if kind == "folder":       # folds to every bet
            return "f" if "f" in legal else ("c" if "c" in legal else "b")
        if kind == "equilibrium":
            probs = table.get(h.key(seat))
            return rng.choices(legal, weights=probs)[0] if probs else rng.choice(legal)
        raise ValueError(kind)
    return play


def play_match(bot_factory, opp, leduc, hands, seed, with_log=True):
    """Chips won per hand by the bot (always seat 0) and the 95 percent half-width. The bot acts first in odd hands.
    `bot_factory()` returns f(observation, legal_strings, seat, hand_no, rng) -> action string."""
    rng = random.Random(seed)
    bot = bot_factory()
    results = []
    total = 8 if leduc else 12
    for n in range(1, hands + 1):
        h = Hand(leduc, 0 if n % 2 == 1 else 1, rng)
        while not h.over:
            if h.actor == 0:
                hand_no = ((n - 1) % total) + 1
                obs, words, legal = h.observation(0, hand_no, total, with_log)
                act = bot(obs, legal, 0, hand_no, rng)
                code = next((c for c, w in WORD.items() if act.lower().startswith(w)), None)
                if code is None or code not in h.legal():
                    raise AssertionError(f"illegal action {act!r} in {legal}")
                h.act(code)
            else:
                h.act(opp(h, 1, rng))
        results.append(h.chips(0))
    mean = sum(results) / len(results)
    var = sum((x - mean) ** 2 for x in results) / max(1, len(results) - 1)
    return mean, 1.96 * math.sqrt(var / len(results))


def player_bot(rules="MINI POKER Kuhn", leduc=False):
    stats = P.OpponentStats()

    def bot(obs, legal, seat, hand_no, rng):
        res = P.decide(rules, obs, legal, seat, stats, rng)
        if res is None:
            return legal[0]
        return res[0]
    return bot
