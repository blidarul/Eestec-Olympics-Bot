"""Liar's Dice (Bluff Family): hidden cup dice bidding, probabilistic bluffing, and challenge duels."""
from __future__ import annotations

import re

from ..core import Game

_BID_RE = re.compile(r"^(?:bid\s+)?(\d+)\s+([1-6])$", re.IGNORECASE)


class LiarsDice(Game):
    id = "liars_dice"
    name = "Liar's Dice"
    category = "bluff"
    blurb = "The pirate's game of hidden dice, escalated bidding, and high-stakes bluff-calling."
    howto = "Both players roll hidden dice under their cups. Players take turns making higher bids on the total number of dice matching a face, or calling 'liar' to reveal all dice."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "3 dice each", "dice": 3, "ones_wild": False},
            {"label": "5 dice each, Ones wild", "dice": 5, "ones_wild": True},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "3 dice each"))
        self.initial_dice = int(self.variant.get("dice", 3))
        self.ones_wild = bool(self.variant.get("ones_wild", False))

        self.dice_counts = [self.initial_dice, self.initial_dice]
        self.current_rolls: list[list[int]] = [[], []]
        self.current_bid: tuple[int, int] | None = None  # (count, face)
        self.last_bidder: int | None = None

        self.current = 0
        self.round = 1
        self.round_history: list[dict] = []
        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

        self._roll_new_round()

    def _roll_new_round(self) -> None:
        self.current_rolls = [
            sorted(self.rng.randint(1, 6) for _ in range(self.dice_counts[0])),
            sorted(self.rng.randint(1, 6) for _ in range(self.dice_counts[1])),
        ]
        self.current_bid = None
        self.last_bidder = None
        self.round_history = []

    def rules(self) -> str:
        wild_desc = "Ones (1s) are WILD and count as the bid face unless ones were explicitly bid." if self.ones_wild else "No wild dice."
        return f"""LIAR'S DICE (Bluff Family) - {self.label}. Alternating turns.

GOAL
Eliminate your opponent's dice by catching their bluffs or making unchallengeable bids.
Each player starts with {self.initial_dice} dice. When a player loses all dice, the other player wins.

TURNS & BIDDING
Both players roll their dice under their cup in secret.
On your turn:
  1. Open or Raise the bid:
     - State how many dice of a given face exist ACROSS BOTH CUPS.
     - A raise must either increase the count (e.g. 2 of 4 -> 3 of anything), or keep the count and raise the face (e.g. 2 of 4 -> 2 of 5).
  2. Call LIAR / CHALLENGE ("liar" or "challenge"):
     - Challenge the previous player's bid. Both cups are lifted and all dice counted.
     - If the total count is LESS than the bid, the bidder was lying and loses 1 die.
     - If the total count is GREATER OR EQUAL to the bid, the challenger was wrong and loses 1 die.

WILD RULES: {wild_desc}

ACTION FORMAT
    bid <count> <face>   OR   liar
Examples: "bid 2 4", "bid 3 6", "liar".
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        moves = []
        if self.current_bid is not None:
            moves.append("liar")
        total_dice = sum(self.dice_counts)
        # Suggest a few valid raises
        if self.current_bid is None:
            moves.extend([f"bid 1 {f}" for f in range(1, 7)])
        else:
            c, f = self.current_bid
            if f < 6:
                moves.append(f"bid {c} {f + 1}")
            if c < total_dice:
                moves.extend([f"bid {c + 1} {face}" for face in range(1, 7)])
        return self.cap_list(moves)

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        c_act = self.clean(action)
        if c_act in ("liar", "dudo", "challenge"):
            if self.current_bid is None:
                return None  # Cannot call liar on move 1 of round
            return "liar"

        m = _BID_RE.match(c_act)
        if not m:
            return None
        count = int(m.group(1))
        face = int(m.group(2))
        total_dice = sum(self.dice_counts)
        if count <= 0 or count > total_dice:
            return None
        if not (1 <= face <= 6):
            return None

        # Check strict raise
        if self.current_bid is not None:
            prev_c, prev_f = self.current_bid
            if count < prev_c:
                return None
            if count == prev_c and face <= prev_f:
                return None

        return f"bid {count} {face}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        if norm == "liar":
            # Showdown!
            b_count, b_face = self.current_bid
            all_dice = self.current_rolls[0] + self.current_rolls[1]
            if self.ones_wild and b_face != 1:
                matching = sum(1 for d in all_dice if d == b_face or d == 1)
            else:
                matching = sum(1 for d in all_dice if d == b_face)

            bidder = self.last_bidder
            challenger = self.current

            if matching < b_count:
                loser = bidder
                reason = f"bid was {b_count}x{b_face}, but only {matching} existed (bidder was lying)"
            else:
                loser = challenger
                reason = f"bid was {b_count}x{b_face}, and {matching} existed (bidder told the truth)"

            self.dice_counts[loser] -= 1
            rec = {
                "seat": challenger,
                "action": "liar",
                "showdown": {
                    "bid": [b_count, b_face],
                    "rolls": [list(self.current_rolls[0]), list(self.current_rolls[1])],
                    "matching": matching,
                    "loser": loser,
                    "reason": reason,
                    "dice_left": list(self.dice_counts),
                },
            }
            self.history.append(rec)
            self.last = rec

            # Check if game over
            if self.dice_counts[0] == 0:
                self.over = True
                self.winner = 1
                self.end_reason = "Player 0 lost all dice"
            elif self.dice_counts[1] == 0:
                self.over = True
                self.winner = 0
                self.end_reason = "Player 1 lost all dice"
            else:
                self.round += 1
                self._roll_new_round()
                # Loser moves first in next round
                self.current = loser
        else:
            m = _BID_RE.match(norm)
            count, face = int(m.group(1)), int(m.group(2))
            self.current_bid = (count, face)
            self.last_bidder = self.current
            rec = {"seat": self.current, "action": norm, "bid": [count, face]}
            self.round_history.append(rec)
            self.history.append(rec)
            self.last = rec
            self.current = 1 - self.current

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        lines = [
            f"LIAR'S DICE ({self.label}). You are Player {seat}.",
            f"Dice counts: you have {self.dice_counts[seat]} dice, opponent has {self.dice_counts[opp]} dice (total {sum(self.dice_counts)}).",
            f"YOUR HIDDEN DICE: {self.current_rolls[seat]}.",
            f"Current bid on table: {f'{self.current_bid[0]} of {self.current_bid[1]}' if self.current_bid else 'None (open the bidding)'}.",
            f"Turn: Player {self.current} to act.",
            "",
            "Current round bidding history:",
        ]
        if not self.round_history:
            lines.append("  (no bids yet this round)")
        for h in self.round_history:
            lines.append(f"  Player {h['seat']}: {h['action']}")

        if self.last and "showdown" in self.last:
            s = self.last["showdown"]
            lines.append(f"\nLast showdown result: {s['reason']}. Player {s['loser']} lost a die.")
        return "\n".join(lines)

    def result(self) -> dict:
        scores = [0, 0]
        if self.winner is not None:
            scores[self.winner] = 1
        return {
            "winner": self.winner,
            "scores": scores,
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "dice_counts": list(self.dice_counts),
            "current_bid": list(self.current_bid) if self.current_bid else None,
            "last_bidder": self.last_bidder,
            "round": self.round,
            "to_move": self.to_move(),
            "history": list(self.history),
            "last": self.last,
            "over": self.over,
            "result": self.result() if self.over else None,
        }
