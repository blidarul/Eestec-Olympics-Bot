"""Mini Poker: Kuhn and Leduc poker variants with tiny decks and fixed betting."""
from __future__ import annotations

import copy
import random
import re

from ..core import Game

RANKS = {"J": 1, "Q": 2, "K": 3}


class MiniPoker(Game):
    id = "mini_poker"
    name = "Mini Poker"
    category = "bluff"
    blurb = "Poker with a tiny deck: with only three ranks, every bet is either a bluff or a trap."
    howto = "Poker with a tiny deck. Each hand both players get a hidden card and bet, check, call or fold; the better card takes the pot unless someone folds. Most chips at the end wins."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "Kuhn poker, 12 hands", "style": "kuhn", "hands": 12, "stack": 24},
            {"label": "Leduc poker, 8 hands", "style": "leduc", "hands": 8, "stack": 40},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.style = str(self.variant.get("style", "leduc")).lower()
        self.total_hands = int(self.variant.get("hands", 8 if self.style == "leduc" else 12))
        self.start_stack = int(self.variant.get("stack", 40 if self.style == "leduc" else 24))
        self.label = str(self.variant.get("label", f"{self.style.capitalize()} poker, {self.total_hands} hands"))
        
        self.rng = random.Random(seed)
        self.stacks = [self.start_stack, self.start_stack]
        self.hand_no = 1
        
        # Current hand state
        self.first = 0
        self.cards: list[str] = ["", ""]
        self.community = ""
        self.community_shown = False
        self.pot = 0
        self.contrib = [0, 0]
        self.round = 1
        self.num_rounds = 2 if self.style == "leduc" else 1
        self.bet_sizes = [2, 4] if self.style == "leduc" else [1]
        self.round_actions: list[list[dict]] = [[] for _ in range(self.num_rounds)]
        self.to_act = 0
        self.last_action: dict | None = None
        self.last_hand: dict | None = None
        self.history: list[dict] = []
        
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""
        
        self._start_hand()

    def secret(self, seat: int) -> list[str]:
        return [self.cards[seat]]

    def _start_hand(self) -> None:
        if self.stacks[0] <= 0 or self.stacks[1] <= 0 or self.hand_no > self.total_hands:
            self._finish_game()
            return

        self.first = (self.hand_no - 1) % 2
        self.to_act = self.first
        self.round = 1
        self.round_actions = [[] for _ in range(self.num_rounds)]
        
        # Ante 1 chip each
        ante0 = min(1, self.stacks[0])
        ante1 = min(1, self.stacks[1])
        self.stacks[0] -= ante0
        self.stacks[1] -= ante1
        self.contrib = [ante0, ante1]
        self.pot = ante0 + ante1

        if self.style == "kuhn":
            deck = ["J", "Q", "K"]
            self.rng.shuffle(deck)
            self.cards = [deck[0], deck[1]]
            self.community = ""
            self.community_shown = False
        else:
            deck = ["Jh", "Js", "Qh", "Qs", "Kh", "Ks"]
            self.rng.shuffle(deck)
            self.cards = [deck[0], deck[1]]
            self.community = deck[2]
            self.community_shown = False

    def rules(self) -> str:
        deck_desc = "3 cards: Jack, Queen, King (J < Q < K)" if self.style == "kuhn" else "6 cards: two Jacks, two Queens, two Kings (J < Q < K)"
        rounds_desc = "1 round of betting" if self.style == "kuhn" else "2 rounds of betting (round 1 before community card, round 2 after)"
        return f"""MINI POKER - {self.label}.

GOAL
Finish the match with more chips than your opponent. Both players start with {self.start_stack} chips.
The match lasts {self.total_hands} hands (or ends earlier if a player is busted).

THE CARDS
The deck has {deck_desc}.
{rounds_desc}.
Ante: 1 chip each at start of hand.
Actions: check, bet, call, raise, fold.
At most 2 bets per round (one bet plus one raise).

END AND SCORING
Most chips at the end wins (score 1, loser 0). Equal chips = draw (0.5 each)."""

    def _current_legal(self) -> list[str]:
        if self.over:
            return []
        acts = self.round_actions[self.round - 1]
        bets_in_round = sum(1 for a in acts if a["act"] in ("bet", "raise"))
        
        if not acts:
            return ["check", "bet"]
        last_act = acts[-1]["act"]
        if last_act == "check":
            return ["check", "bet"]
        elif last_act in ("bet", "raise"):
            can_raise = (bets_in_round < 2) and (self.stacks[self.to_act] >= self.bet_sizes[self.round - 1])
            if can_raise:
                return ["call", "raise", "fold"]
            return ["call", "fold"]
        return []

    def to_move(self) -> list[int]:
        if self.over:
            return []
        return [self.to_act]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.to_act:
            return []
        return self._current_legal()

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.to_act:
            return None
        a = self.clean(action).lower().strip()
        legal = self._current_legal()
        if a in legal:
            return a
        # tolerate prefix/words like "i bet", "raise"
        for leg in legal:
            if leg in a.split():
                return leg
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        seat = self.to_act
        raw = actions.get(seat, "")
        act = self.normalize(seat, raw)
        if act is None:
            raise ValueError(f"illegal action {raw!r} for seat {seat}")
        
        cur_bet_size = self.bet_sizes[self.round - 1]
        cost = 0
        other = 1 - seat
        
        if act == "bet":
            cost = min(cur_bet_size, self.stacks[seat])
        elif act == "call":
            cost = min(self.contrib[other] - self.contrib[seat], self.stacks[seat])
        elif act == "raise":
            cost = min(self.contrib[other] - self.contrib[seat] + cur_bet_size, self.stacks[seat])
        
        self.stacks[seat] -= cost
        self.contrib[seat] += cost
        self.pot += cost
        
        act_record = {"seat": seat, "act": act, "amount": cost, "hand": self.hand_no, "round": self.round}
        self.round_actions[self.round - 1].append(act_record)
        self.last_action = act_record

        # Check round and hand resolution
        if act == "fold":
            # Hand ends immediately, other wins pot
            self.stacks[other] += self.pot
            self._record_hand_end(winner=other, showdown=False)
            return

        r_acts = self.round_actions[self.round - 1]
        round_complete = False
        if len(r_acts) >= 2:
            if r_acts[-1]["act"] == "check" and r_acts[-2]["act"] == "check":
                round_complete = True
            elif r_acts[-1]["act"] == "call":
                round_complete = True

        if round_complete:
            if self.round < self.num_rounds:
                # Move to round 2 (reveal community card in Leduc)
                self.round += 1
                self.community_shown = True
                self.to_act = self.first
            else:
                # Showdown!
                self._showdown()
        else:
            self.to_act = other

    def _showdown(self) -> None:
        c0, c1 = self.cards[0], self.cards[1]
        r0 = RANKS[c0[0]]
        r1 = RANKS[c1[0]]
        
        if self.style == "leduc":
            comm_rank = RANKS[self.community[0]]
            pair0 = (r0 == comm_rank)
            pair1 = (r1 == comm_rank)
            if pair0 and not pair1:
                winner = 0
            elif pair1 and not pair0:
                winner = 1
            elif r0 > r1:
                winner = 0
            elif r1 > r0:
                winner = 1
            else:
                winner = None
        else:
            if r0 > r1:
                winner = 0
            elif r1 > r0:
                winner = 1
            else:
                winner = None

        if winner is not None:
            self.stacks[winner] += self.pot
        else:
            # Split pot
            self.stacks[0] += self.pot // 2
            self.stacks[1] += self.pot - (self.pot // 2)

        self._record_hand_end(winner=winner, showdown=True)

    def _record_hand_end(self, winner: int | None, showdown: bool) -> None:
        hand_data = {
            "hand": self.hand_no,
            "cards": list(self.cards) if showdown else [self.cards[0] if winner == 0 else "", self.cards[1] if winner == 1 else ""],
            "community": self.community if (self.community_shown or showdown) else "",
            "pot": self.pot,
            "winner": winner,
            "showdown": showdown,
            "stacks": list(self.stacks),
        }
        self.history.append(hand_data)
        self.last_hand = hand_data

        if self.stacks[0] <= 0 or self.stacks[1] <= 0 or self.hand_no >= self.total_hands:
            self._finish_game()
        else:
            self.hand_no += 1
            self._start_hand()

    def _finish_game(self) -> None:
        self.over = True
        s0, s1 = self.stacks[0], self.stacks[1]
        if s0 > s1:
            self.winner = 0
            self.end_reason = f"seat 0 won chips ({s0} vs {s1})"
        elif s1 > s0:
            self.winner = 1
            self.end_reason = f"seat 1 won chips ({s1} vs {s0})"
        else:
            self.winner = None
            self.end_reason = f"tied chips ({s0} each): draw"

    def is_over(self) -> bool:
        return self.over

    def result(self) -> dict:
        if not self.over:
            return {"winner": None, "scores": [0, 0], "reason": "in progress"}
        scores = [0, 0]
        if self.winner is not None:
            scores[self.winner] = 1
        else:
            scores = [0.5, 0.5]
        return {"winner": self.winner, "scores": scores, "reason": self.end_reason}

    def observation(self, seat: int) -> str:
        lines = [
            f"MINI POKER - {self.label}. Hand {self.hand_no}/{self.total_hands}. You are seat {seat}.",
            f"Stacks: you {self.stacks[seat]}, opponent {self.stacks[1 - seat]}. Pot: {self.pot}.",
            f"Your card: {self.cards[seat]}."
        ]
        if self.community_shown:
            lines.append(f"Community card: {self.community}.")
        
        if self.over:
            lines.append(f"The match is over: {self.end_reason}.")
        elif self.to_act == seat:
            acts = ", ".join(self._current_legal())
            lines.append(f"Your turn. Legal actions: {acts}.")
        else:
            lines.append("Waiting for opponent action.")

        curr_acts = self.round_actions[self.round - 1]
        if curr_acts:
            lines.append("Actions this round: " + ", ".join(f"seat {a['seat']} {a['act']}" for a in curr_acts))

        return "\n".join(lines)

    def frame(self) -> dict:
        return copy.deepcopy(self._frame())

    def _frame(self) -> dict:
        return {
            "style": self.style,
            "label": self.label,
            "hand": self.hand_no,
            "hands": self.total_hands,
            "first": self.first,
            "stacks": list(self.stacks),
            "start_stack": self.start_stack,
            "cards": list(self.cards),
            "community": self.community,
            "community_shown": self.community_shown,
            "pot": self.pot,
            "contrib": list(self.contrib),
            "round": self.round,
            "rounds": self.num_rounds,
            "bet_sizes": self.bet_sizes,
            "actions": self.round_actions,
            "to_act": self.to_act,
            "legal": self._current_legal(),
            "last": self.last_action,
            "last_hand": self.last_hand,
            "history": self.history,
            "over": self.over,
            "result": self.result() if self.over else None,
        }

    def random_action(self, seat: int, rng: random.Random) -> str:
        legal = self._current_legal()
        if not legal:
            return "check"
        return rng.choice(legal)
