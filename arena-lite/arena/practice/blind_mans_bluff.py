"""Blind Man's Bluff (Bluff Family): Indian poker with inverted private information."""
from __future__ import annotations

from ..core import Game


class BlindMansBluff(Game):
    id = "blind_mans_bluff"
    name = "Blind Man's Bluff"
    category = "bluff"
    blurb = "Inverted poker: see your opponent's card on their forehead, guess your own, and wager chips on the unknown."
    howto = "Both players are dealt one card (ranks 1 to 10). You see your opponent's card, but NEVER your own. Players bet chips; highest card at showdown wins the pot."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "10-card deck, 5 hands", "cards": 10, "hands": 5, "ante": 1},
            {"label": "10-card deck, 8 hands", "cards": 10, "hands": 8, "ante": 1},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "10-card deck, 5 hands"))
        self.max_rank = int(self.variant.get("cards", 10))
        self.hands_count = int(self.variant.get("hands", 5))
        self.ante = int(self.variant.get("ante", 1))

        self.bank = [0, 0]  # net chips won/lost
        self.hand_idx = 1
        self.current = 0  # seat to act

        # State within current hand
        self.deck = list(range(1, self.max_rank + 1))
        self.deals: list[int] = []
        self.pot = 0
        self.bets = [0, 0]
        self.betting_phase = "open"  # 'open', 'faced_bet', 'done'
        self.hand_history: list[dict] = []
        self.match_history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

        self._start_hand()

    def _start_hand(self) -> None:
        self.rng.shuffle(self.deck)
        self.deals = [self.deck[0], self.deck[1]]
        self.pot = 2 * self.ante
        self.bets = [self.ante, self.ante]
        self.current = 0
        self.betting_phase = "open"
        self.hand_history = []

    def rules(self) -> str:
        return f"""BLIND MAN'S BLUFF (Bluff Family) - {self.label}. Alternating turns.

GOAL
Accumulate chips across {self.hands_count} hands by reading your opponent's reactions to their card.

INVERTED INFORMATION
Both players are dealt one card from 1 to {self.max_rank}.
You see the OPPONENT'S card on their forehead, but you NEVER see your own card!

BETTING
Each hand starts with a {self.ante}-chip ante from each player (pot = {2 * self.ante}).
Player 0 acts first:
  - "check"  or  "bet 1"
Facing a check, Player 1 may:
  - "check" (proceeds to showdown)  or  "bet 1"
Facing a bet, the answering player may:
  - "call 1" (matches bet, proceeds to showdown)  or  "fold" (concedes the pot)

SHOWDOWN
If neither player folds, both cards are revealed: the higher card wins the pot.

ACTION FORMAT
    check   OR   bet 1   OR   call 1   OR   fold
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        if self.betting_phase == "open":
            return ["check", "bet 1"]
        elif self.betting_phase == "faced_bet":
            return ["call 1", "fold"]
        return []

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        c = self.clean(action)
        if c in ("check", "ch"):
            if self.betting_phase == "open":
                return "check"
        elif c in ("bet", "bet 1", "b"):
            if self.betting_phase == "open":
                return "bet 1"
        elif c in ("call", "call 1", "c"):
            if self.betting_phase == "faced_bet":
                return "call 1"
        elif c in ("fold", "f"):
            if self.betting_phase == "faced_bet":
                return "fold"
        return None

    def _resolve_hand(self, winner_seat: int | None, reason: str) -> None:
        c0, c1 = self.deals
        if winner_seat == 0:
            self.bank[0] += (self.pot - self.bets[0])
            self.bank[1] -= self.bets[1]
        elif winner_seat == 1:
            self.bank[1] += (self.pot - self.bets[1])
            self.bank[0] -= self.bets[0]
        else:
            # Tie: return bets
            pass

        record = {
            "hand": self.hand_idx,
            "cards": [c0, c1],
            "pot": self.pot,
            "winner": winner_seat,
            "reason": reason,
            "bank": list(self.bank),
        }
        self.match_history.append(record)

        if self.hand_idx >= self.hands_count:
            self.over = True
            if self.bank[0] > self.bank[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won after {self.hands_count} hands ({self.bank[0]:+d} vs {self.bank[1]:+d} chips)"
            elif self.bank[1] > self.bank[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won after {self.hands_count} hands ({self.bank[1]:+d} vs {self.bank[0]:+d} chips)"
            else:
                self.winner = None
                self.end_reason = f"draw after {self.hands_count} hands with equal chips ({self.bank[0]:+d})"
        else:
            self.hand_idx += 1
            self._start_hand()

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        rec = {"hand": self.hand_idx, "seat": self.current, "action": norm}
        self.hand_history.append(rec)
        self.last = rec

        if self.betting_phase == "open":
            if norm == "check":
                if self.current == 0:
                    # Seat 0 checked; Seat 1 can check or bet
                    self.current = 1
                else:
                    # Both checked -> showdown!
                    c0, c1 = self.deals
                    w = 0 if c0 > c1 else (1 if c1 > c0 else None)
                    reason = f"showdown: card {c0} vs {c1}"
                    self._resolve_hand(w, reason)
            else:
                # norm == 'bet 1'
                self.pot += 1
                self.bets[self.current] += 1
                self.betting_phase = "faced_bet"
                self.current = 1 - self.current
        elif self.betting_phase == "faced_bet":
            if norm == "fold":
                w = 1 - self.current
                reason = f"player {self.current} folded"
                self._resolve_hand(w, reason)
            else:
                # norm == 'call 1'
                self.pot += 1
                self.bets[self.current] += 1
                c0, c1 = self.deals
                w = 0 if c0 > c1 else (1 if c1 > c0 else None)
                reason = f"showdown after call: card {c0} vs {c1}"
                self._resolve_hand(w, reason)

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        opp_card = self.deals[opp]
        lines = [
            f"BLIND MAN'S BLUFF ({self.label}). You are Player {seat}.",
            f"Hand {self.hand_idx} of {self.hands_count}. Bank: you {self.bank[seat]:+d}, opp {self.bank[opp]:+d} chips.",
            f"OPPONENT'S CARD (on their forehead): {opp_card} (your own card is hidden!).",
            f"Pot size: {self.pot} chips. Your bet: {self.bets[seat]}, opp bet: {self.bets[opp]}.",
            f"Turn: Player {self.current} to act.",
        ]
        if self.hand_history:
            lines.append("\nCurrent hand actions:")
            for h in self.hand_history:
                lines.append(f"  Player {h['seat']}: {h['action']}")
        if self.match_history:
            lines.append("\nPrevious hands summary:")
            for m in self.match_history:
                lines.append(f"  Hand {m['hand']}: your card {m['cards'][seat]}, opp card {m['cards'][opp]} -> winner: Player {m['winner']} ({m['reason']})")
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": list(self.bank),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "hand_idx": self.hand_idx,
            "hands_count": self.hands_count,
            "bank": list(self.bank),
            "deals": list(self.deals),
            "pot": self.pot,
            "bets": list(self.bets),
            "current": self.current,
            "to_move": self.to_move(),
            "history": list(self.match_history),
            "last": self.last,
            "over": self.over,
            "result": self.result() if self.over else None,
        }
