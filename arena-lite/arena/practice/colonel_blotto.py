"""Colonel Blotto: resource allocation duel across multiple battlefields."""
from __future__ import annotations

import copy
import random
import re

from ..core import Game


class ColonelBlotto(Game):
    id = "colonel_blotto"
    name = "Colonel Blotto"
    category = "read"
    blurb = "Split your army across battlefields in secret: outguess where your rival goes heavy and where they gamble."
    howto = "Each round both players secretly split their soldiers across several battlefields. The bigger army takes each battlefield; take the most valuable share to win the round, and win the most rounds."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "100 soldiers, 5 equal fields", "soldiers": 100, "fields": 5, "rounds": 5, "values": [1, 1, 1, 1, 1], "reserves": False},
            {"label": "60 soldiers, 6 fields worth 1-6", "soldiers": 60, "fields": 6, "rounds": 5, "values": [1, 2, 3, 4, 5, 6], "reserves": False},
            {"label": "Reserves: +30 per round, 3 fields", "soldiers": 30, "fields": 3, "rounds": 5, "values": [1, 1, 1], "reserves": True, "income": 30},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.k = int(self.variant.get("fields", 5))
        self.rounds = int(self.variant.get("rounds", 5))
        raw_vals = self.variant.get("values", [1] * self.k)
        if isinstance(raw_vals, list):
            self.values = [int(x) for x in raw_vals]
        elif raw_vals == "equal":
            self.values = [1] * self.k
        else:
            self.values = list(range(1, self.k + 1))
        
        self.base_soldiers = int(self.variant.get("soldiers", 100))
        self.reserves = bool(self.variant.get("reserves", False))
        self.income = int(self.variant.get("income", 30))
        self.label = str(self.variant.get("label", f"{self.base_soldiers} soldiers, {self.k} fields"))

        self.round_no = 1
        self.reserve = [0, 0]
        self.rounds_won = [0, 0]
        self.value_won = [0, 0]
        self.history: list[dict] = []
        self.last_round: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _soldiers_for(self, seat: int) -> int:
        if self.reserves:
            return self.income + self.reserve[seat]
        return self.base_soldiers

    def rules(self) -> str:
        f_names = " ".join(f"F{i+1}" for i in range(self.k))
        val_str = ", ".join(f"F{i+1}={self.values[i]}" for i in range(self.k))
        res_info = f"Reserves: +{self.income} per round; send at most your reserve, unspent soldiers are kept." if self.reserves else "A fresh army each round."
        action_fmt = f"Your action is exactly {self.k} whole numbers >= 0 that add up to at most your reserve" if self.reserves else f"Your action is exactly {self.k} whole numbers >= 0 that add up to EXACTLY {self.base_soldiers}"
        ex_share = self.base_soldiers // self.k
        rem = self.base_soldiers - ex_share * (self.k - 1)
        ex_nums = [ex_share] * (self.k - 1) + [rem]
        ex_str = " ".join(str(x) for x in ex_nums)
        return f"""COLONEL BLOTTO - {self.label}. 2 players, simultaneous moves, {self.rounds} rounds.

GOAL
Win more rounds than your opponent.

EACH ROUND
There are {self.k} battlefields, called {f_names} (in this order, left to right).
Values: {val_str}.
{res_info}
Both players secretly choose how many soldiers to put on each battlefield, at the same time.
Then both allocations are revealed. On each battlefield the player with MORE soldiers captures
it; equal soldiers = nobody captures it.
A round is won by the player who captures MORE battlefield points. Equal points = the round is drawn.

END AND SCORING
After {self.rounds} rounds, the player who won more rounds wins the game. If rounds won are equal, the
player who captured more battlefield points over the whole game wins; if that is equal too,
the game is a draw. Your score = rounds won. The game always lasts exactly {self.rounds} rounds.

ACTION FORMAT
{action_fmt}, listed in battlefield order F1 to F{self.k}, separated by spaces (commas are also accepted).
Examples: "{ex_str}". The legal-actions list is null."""

    def to_move(self) -> list[int]:
        if self.over:
            return []
        return [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over:
            return []
        return None

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over:
            return None
        a = self.clean(action).replace(",", " ")
        tokens = a.split()
        if len(tokens) != self.k:
            return None
        nums = []
        for t in tokens:
            try:
                val = int(t)
                if val < 0:
                    return None
                nums.append(val)
            except ValueError:
                return None
        total = self._soldiers_for(seat)
        if self.reserves:
            if sum(nums) > total:
                return None
        else:
            if sum(nums) != total:
                return None
        return " ".join(str(n) for n in nums)

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        a0 = self.normalize(0, actions.get(0, ""))
        a1 = self.normalize(1, actions.get(1, ""))
        if a0 is None:
            raise ValueError(f"illegal action {actions.get(0)!r} for seat 0")
        if a1 is None:
            raise ValueError(f"illegal action {actions.get(1)!r} for seat 1")
        
        alloc0 = [int(x) for x in a0.split()]
        alloc1 = [int(x) for x in a1.split()]

        captured = []
        pts = [0, 0]
        for f in range(self.k):
            v = self.values[f]
            if alloc0[f] > alloc1[f]:
                captured.append(0)
                pts[0] += v
            elif alloc1[f] > alloc0[f]:
                captured.append(1)
                pts[1] += v
            else:
                captured.append(None)

        self.value_won[0] += pts[0]
        self.value_won[1] += pts[1]

        r_winner = None
        if pts[0] > pts[1]:
            r_winner = 0
            self.rounds_won[0] += 1
        elif pts[1] > pts[0]:
            r_winner = 1
            self.rounds_won[1] += 1

        round_data = {
            "round": self.round_no,
            "values": list(self.values),
            "alloc": [alloc0, alloc1],
            "captured": captured,
            "points": pts,
            "winner": r_winner,
            "rounds_won": list(self.rounds_won),
        }
        self.history.append(round_data)
        self.last_round = round_data

        if self.reserves:
            self.reserve[0] = self._soldiers_for(0) - sum(alloc0)
            self.reserve[1] = self._soldiers_for(1) - sum(alloc1)

        if self.round_no >= self.rounds:
            self.over = True
            if self.rounds_won[0] > self.rounds_won[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won {self.rounds_won[0]} rounds vs {self.rounds_won[1]}"
            elif self.rounds_won[1] > self.rounds_won[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won {self.rounds_won[1]} rounds vs {self.rounds_won[0]}"
            else:
                # Tie break by total points won
                if self.value_won[0] > self.value_won[1]:
                    self.winner = 0
                    self.end_reason = f"rounds tied ({self.rounds_won[0]}-{self.rounds_won[1]}): seat 0 won more points ({self.value_won[0]} vs {self.value_won[1]})"
                elif self.value_won[1] > self.value_won[0]:
                    self.winner = 1
                    self.end_reason = f"rounds tied ({self.rounds_won[0]}-{self.rounds_won[1]}): seat 1 won more points ({self.value_won[1]} vs {self.value_won[0]})"
                else:
                    self.winner = None
                    self.end_reason = "rounds and points tied: draw"
        else:
            self.round_no += 1

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
        tot = self._soldiers_for(seat)
        opp_tot = self._soldiers_for(1 - seat)
        lines = [
            f"COLONEL BLOTTO - {self.label}. Round {self.round_no}/{self.rounds}. You are seat {seat}.",
            f"Your soldiers this round: {tot}.",
            f"Battlefield values: " + ", ".join(f"F{i+1}={self.values[i]}" for i in range(self.k)),
            f"Score: rounds won you {self.rounds_won[seat]} opp {self.rounds_won[1 - seat]}; battlefield points you {self.value_won[seat]} opp {self.value_won[1 - seat]}."
        ]
        if self.reserves:
            lines.append(f"Reserves: you {tot}, opponent {opp_tot}.")
        if self.over:
            lines.append(f"The game is over: {self.end_reason}.")
        else:
            lines.append(f"Enter your allocation of {tot} soldiers across {self.k} fields.")

        if self.history:
            lines.append("Previous rounds history:")
            for h in self.history:
                r = h["round"]
                my_a = h["alloc"][seat]
                opp_a = h["alloc"][1 - seat]
                w = h["winner"]
                w_str = f"seat {w} won" if w is not None else "draw"
                lines.append(f"Round {r}: you {' '.join(str(x) for x in my_a)} | opponent {' '.join(str(x) for x in opp_a)} ({w_str})")

        return "\n".join(lines)

    def frame(self) -> dict:
        return copy.deepcopy(self._frame())

    def _frame(self) -> dict:
        return {
            "label": self.label,
            "k": self.k,
            "round": self.round_no,
            "rounds": self.rounds,
            "values": list(self.values),
            "reserves": self.reserves,
            "reserve": list(self.reserve),
            "soldiers": self.base_soldiers,
            "income": self.income,
            "rounds_won": list(self.rounds_won),
            "value_won": list(self.value_won),
            "last": self.last_round,
            "history": self.history,
            "over": self.over,
            "result": self.result() if self.over else None,
        }

    def random_action(self, seat: int, rng: random.Random) -> str:
        tot = self._soldiers_for(seat)
        cuts = sorted(rng.randint(0, tot) for _ in range(self.k - 1))
        alloc = []
        prev = 0
        for c in cuts:
            alloc.append(c - prev)
            prev = c
        alloc.append(tot - prev)
        return " ".join(str(x) for x in alloc)
