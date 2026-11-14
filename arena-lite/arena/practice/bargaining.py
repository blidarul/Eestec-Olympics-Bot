"""Rubinstein Bargaining (Deals Family): alternating-offer shrinking-pie division game."""
from __future__ import annotations

import re

from ..core import Game

_OFFER_RE = re.compile(r"^(?:offer\s+)?(\d+)\s+(\d+)$", re.IGNORECASE)


class Bargaining(Game):
    id = "bargaining"
    name = "Rubinstein Bargaining"
    category = "deals"
    blurb = "Shrinking-pie negotiation: make an offer, counter your rival's terms, or reach an agreement before time erodes the value."
    howto = "Players alternate offering how to divide a pot of 100 gold coins. Each round the pot shrinks by a discount rate. A player can accept the pending offer or make a counter-offer. If the round limit is reached with no deal, both get zero."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "100 coins, 10% decay per round, max 5 rounds", "initial_pot": 100, "decay": 0.10, "max_rounds": 5},
            {"label": "100 coins, 20% decay per round, max 4 rounds", "initial_pot": 100, "decay": 0.20, "max_rounds": 4},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "100 coins, 10% decay, max 5 rounds"))
        self.initial_pot = int(self.variant.get("initial_pot", 100))
        self.decay = float(self.variant.get("decay", 0.10))
        self.max_rounds = int(self.variant.get("max_rounds", 5))

        self.round = 1
        self.current = 0  # seat to act
        self.pending_offer: tuple[int, int] | None = None  # (offered_to_proposer, offered_to_responder)
        self.proposer: int | None = None

        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""
        self.final_payouts = [0, 0]

    @property
    def current_pot(self) -> int:
        decay_factor = (1.0 - self.decay) ** (self.round - 1)
        return max(0, int(round(self.initial_pot * decay_factor)))

    def rules(self) -> str:
        decay_pct = int(self.decay * 100)
        return f"""RUBINSTEIN BARGAINING (Deals Family) - {self.label}. Alternating turns.

GOAL
Negotiate a division of a shared pot of gold coins.
The pot starts at {self.initial_pot} coins, but shrinks by {decay_pct}% after every round!

TURN ORDER
Player 0 proposes an opening split in Round 1:
    offer <for_me> <for_opponent>
The sum must equal the current pot ({self.initial_pot} in Round 1).

On each subsequent turn, the answering player may:
  1. Accept the pending offer:
     "accept" -> The game ends immediately with the agreed payout.
  2. Make a counter-offer with the new (shrunk) pot:
     "offer <for_me> <for_opponent>"
     Sum must equal the new pot size.

If Round {self.max_rounds} ends with no agreement, BOTH PLAYERS GET ZERO.

ACTION FORMAT
    offer <my_share> <their_share>   OR   accept
Examples: "offer 50 50", "offer 60 40", "accept".
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        pot = self.current_pot
        actions = []
        if self.pending_offer is not None:
            actions.append("accept")
        # Candidate splits: 50-50, 60-40, 70-30, 80-20
        half = pot // 2
        actions.append(f"offer {half} {pot - half}")
        s60 = int(pot * 0.6)
        actions.append(f"offer {s60} {pot - s60}")
        s70 = int(pot * 0.7)
        actions.append(f"offer {s70} {pot - s70}")
        return sorted(set(actions))

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        c = self.clean(action)
        if c == "accept":
            if self.pending_offer is None:
                return None  # Cannot accept on move 1
            return "accept"

        m = _OFFER_RE.match(c)
        if not m:
            return None
        my_share = int(m.group(1))
        opp_share = int(m.group(2))
        pot = self.current_pot
        if my_share < 0 or opp_share < 0:
            return None
        if my_share + opp_share != pot:
            return None
        return f"offer {my_share} {opp_share}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        if norm == "accept":
            # Agreement reached!
            proposer_share, responder_share = self.pending_offer
            payouts = [0, 0]
            payouts[self.proposer] = proposer_share
            payouts[self.current] = responder_share
            self.final_payouts = payouts
            self.over = True
            if payouts[0] > payouts[1]:
                self.winner = 0
                self.end_reason = f"deal accepted in round {self.round}; seat 0 won ({payouts[0]} vs {payouts[1]} coins)"
            elif payouts[1] > payouts[0]:
                self.winner = 1
                self.end_reason = f"deal accepted in round {self.round}; seat 1 won ({payouts[1]} vs {payouts[0]} coins)"
            else:
                self.winner = None
                self.end_reason = f"equal deal accepted in round {self.round} ({payouts[0]}-{payouts[1]} coins)"
            rec = {"seat": self.current, "action": "accept", "payouts": list(payouts)}
            self.history.append(rec)
            self.last = rec
            return

        m = _OFFER_RE.match(norm)
        my_share = int(m.group(1))
        opp_share = int(m.group(2))
        self.pending_offer = (my_share, opp_share)
        self.proposer = self.current

        rec = {"seat": self.current, "action": norm, "offer": [my_share, opp_share], "round": self.round, "pot": self.current_pot}
        self.history.append(rec)
        self.last = rec

        # Check turn advancement / round progression
        if self.current == 1:
            self.round += 1
            if self.round > self.max_rounds:
                # Time out: no deal!
                self.over = True
                self.winner = None
                self.final_payouts = [0, 0]
                self.end_reason = f"deadline passed without an agreement; both players receive 0"
                return
            self.current = 0
        else:
            self.current = 1

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        lines = [
            f"BARGAINING ({self.label}). You are Player {seat}.",
            f"Round {self.round} of {self.max_rounds}. Current pot size: {self.current_pot} coins (shrinks by {int(self.decay * 100)}%/round).",
            f"Turn: Player {self.current} to act.",
        ]
        if self.pending_offer is not None:
            if self.current == seat:
                lines.append(f"PENDING OFFER from Player {self.proposer}: offers you {self.pending_offer[1]} coins (keeps {self.pending_offer[0]} coins).")
                lines.append("You may 'accept' or reply with a counter 'offer <me> <opp>'.")
            else:
                lines.append(f"Waiting for Player {self.current} to respond to your offer of {self.pending_offer[1]} coins.")
        else:
            lines.append("Open the negotiation with 'offer <my_share> <their_share>'.")

        if self.history:
            lines.append("\nOffer history:")
            for h in self.history:
                if h["action"] == "accept":
                    lines.append(f"  Player {h['seat']}: accepted the deal!")
                else:
                    lines.append(f"  Player {h['seat']} (Round {h['round']}): offered {h['offer'][0]} for self, {h['offer'][1]} for rival (pot: {h['pot']})")
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": list(self.final_payouts),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "round": self.round,
            "max_rounds": self.max_rounds,
            "pot": self.current_pot,
            "pending_offer": list(self.pending_offer) if self.pending_offer else None,
            "proposer": self.proposer,
            "final_payouts": list(self.final_payouts),
            "to_move": self.to_move(),
            "history": list(self.history),
            "last": self.last,
            "over": self.over,
            "result": self.result() if self.over else None,
        }
