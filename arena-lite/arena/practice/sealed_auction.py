"""Sealed-Bid Auction (Deals Family): private-value first-price and second-price (Vickrey) auctions."""
from __future__ import annotations

import re

from ..core import Game

_BID_RE = re.compile(r"^(?:bid\s+)?(\d+(?:\.\d+)?)$", re.IGNORECASE)


class SealedAuction(Game):
    id = "sealed_auction"
    name = "Sealed-Bid Auction"
    category = "deals"
    blurb = "Private-value auctions: evaluate your lot, calculate the optimal bid shading, and out-value your rival."
    howto = "Both players receive private valuations for lots across multiple rounds. Players submit sealed bids simultaneously. The highest bidder wins the lot, paying the bid (first-price) or second bid (second-price)."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "Second-Price (Vickrey), 5 rounds", "pricing": "second_price", "val_min": 10, "val_max": 100, "rounds": 5},
            {"label": "First-Price, 5 rounds", "pricing": "first_price", "val_min": 10, "val_max": 100, "rounds": 5},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "Second-Price (Vickrey), 5 rounds"))
        self.pricing = str(self.variant.get("pricing", "second_price"))
        self.val_min = int(self.variant.get("val_min", 10))
        self.val_max = int(self.variant.get("val_max", 100))
        self.rounds = int(self.variant.get("rounds", 5))

        # Pre-generate values per round for both seats
        self.valuations: list[list[int]] = [
            [self.rng.randint(self.val_min, self.val_max) for _ in range(self.rounds)],
            [self.rng.randint(self.val_min, self.val_max) for _ in range(self.rounds)],
        ]

        self.scores = [0.0, 0.0]
        self.round = 1
        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def rules(self) -> str:
        rule_desc = (
            "SECOND-PRICE (Vickrey): The highest bidder wins the item and pays the SECOND-HIGHEST bid. (Truthful bidding is optimal)."
            if self.pricing == "second_price"
            else "FIRST-PRICE: The highest bidder wins the item and pays their OWN bid. (Bid shading is necessary)."
        )
        return f"""SEALED-BID AUCTION (Deals Family) - {self.label}. 2 players, simultaneous bids.

GOAL
Accumulate the most profit over {self.rounds} independent auction rounds.
Your profit from winning an item = (Your Private Valuation - Price Paid).
If you do not win an item, your profit for that round is 0.

AUCTION FORMAT: {rule_desc}
In each round, both players receive a private valuation between {self.val_min} and {self.val_max}.
You see only YOUR valuation. Both submit sealed bids at the same time.

ACTION FORMAT
    bid <amount>
Examples: "bid 64.5", "bid 50", "75" (a bare number also works).
Bids must be non-negative numbers.

FEEDBACK
After each round, both bids are revealed along with the winner and price paid.
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over:
            return []
        v = self.valuations[seat][self.round - 1]
        step = max(5, (self.val_max - self.val_min) // 10)
        bids = [f"bid {b}" for b in range(self.val_min, self.val_max + 1, step)]
        if f"bid {v}" not in bids:
            bids.append(f"bid {v}")
        return sorted(set(bids))

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over:
            return None
        m = _BID_RE.match(self.clean(action))
        if not m:
            return None
        val = float(m.group(1))
        if val < 0:
            return None
        return f"bid {val:.1f}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        b0 = float(self.normalize(0, actions[0]).split()[-1])
        b1 = float(self.normalize(1, actions[1]).split()[-1])

        v0 = self.valuations[0][self.round - 1]
        v1 = self.valuations[1][self.round - 1]

        # Determine winner
        if b0 > b1:
            win_seat = 0
            price = b1 if self.pricing == "second_price" else b0
            profits = [v0 - price, 0.0]
        elif b1 > b0:
            win_seat = 1
            price = b0 if self.pricing == "second_price" else b1
            profits = [0.0, v1 - price]
        else:
            # Tie: split item value or coin flip
            win_seat = self.rng.choice([0, 1])
            price = b0
            profits = [v0 - price if win_seat == 0 else 0.0, v1 - price if win_seat == 1 else 0.0]

        self.scores[0] += profits[0]
        self.scores[1] += profits[1]

        rec = {
            "round": self.round,
            "valuations": [v0, v1],
            "bids": [b0, b1],
            "winner": win_seat,
            "price": price,
            "profits": profits,
            "scores": list(self.scores),
        }
        self.history.append(rec)
        self.last = rec

        if self.round >= self.rounds:
            self.over = True
            if self.scores[0] > self.scores[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won with higher total profit ({self.scores[0]:.1f} vs {self.scores[1]:.1f})"
            elif self.scores[1] > self.scores[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won with higher total profit ({self.scores[1]:.1f} vs {self.scores[0]:.1f})"
            else:
                self.winner = None
                self.end_reason = f"draw with equal profits ({self.scores[0]:.1f})"
        else:
            self.round += 1

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        v_current = self.valuations[seat][self.round - 1]
        lines = [
            f"SEALED-BID AUCTION ({self.label}). You are Player {seat}.",
            f"Round {self.round} of {self.rounds}. Total profits: you {self.scores[seat]:.1f}, opponent {self.scores[opp]:.1f}.",
            f"YOUR PRIVATE VALUATION for this lot: {v_current}.",
            f"Valuation range: [{self.val_min}, {self.val_max}]. Pricing rule: {self.pricing}.",
            "",
            "Auction history:",
        ]
        if not self.history:
            lines.append("  (first round)")
        for h in self.history:
            lines.append(f"  Round {h['round']}: you bid {h['bids'][seat]} (val {h['valuations'][seat]}), opp bid {h['bids'][opp]} -> winner: Player {h['winner']} (price {h['price']:.1f}, your profit {h['profits'][seat]:+.1f})")
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": [round(s, 1) for s in self.scores],
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "pricing": self.pricing,
            "round": self.round,
            "rounds": self.rounds,
            "scores": list(self.scores),
            "history": list(self.history),
            "last": self.last,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
