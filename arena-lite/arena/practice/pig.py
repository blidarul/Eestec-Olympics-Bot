"""Pig (practice): push-your-luck dice race. Roll to grow your turn total, hold to bank it; a 1
wipes the turn. Two-dice variant: any single 1 wipes the turn, double 1s also reset your bank."""
from __future__ import annotations

import copy
import random

from ..core import Game

MAX_DECISIONS = 200


class Pig(Game):
    id = "pig"
    name = "Pig"
    category = "practice"
    blurb = "Push your luck: one more roll could win the race, or wipe out your whole turn."
    howto = "On your turn, roll the dice as often as you dare to build up points, then stop to bank them. Roll a one and you lose that turn's points. First to the target wins."
    duplicate_safe = False  # the dice rolls come from the seed (hidden future randomness) (core.Game.duplicate_safe)
    max_steps = MAX_DECISIONS

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "One die, first to 50", "dice": 1, "target": 50},
            {"label": "Two dice, first to 60 (snake eyes reset)", "dice": 2, "target": 60},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.dice = 2 if int(self.variant.get("dice", 1)) == 2 else 1
        self.target = max(10, int(self.variant.get("target", 50)))
        self.label = str(self.variant.get("label", ""))
        self.banked = [0, 0]
        self.turn_total = 0
        self.current = 0
        self.turn_no = 1
        self.turn_rolls: list[list[int]] = []  # rolls in the current turn
        self.log: list[dict] = []  # finished turns
        self.decisions = 0
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""
        self.last: dict | None = None

    def _end_turn(self, kind: str) -> None:
        self.log.append({"turn": self.turn_no, "seat": self.current, "rolls": self.turn_rolls,
                         "end": kind, "gained": self.turn_total if kind == "hold" else 0,
                         "banked": list(self.banked)})
        self.turn_rolls = []
        self.turn_total = 0
        self.current = 1 - self.current
        self.turn_no += 1

    # --------------------------------------------------------------- interface
    def rules(self) -> str:
        T = self.target
        if self.dice == 1:
            roll = ("ROLL: roll one six-sided die.\n"
                    "  - 2 to 6: the number is added to your TURN TOTAL and you choose again.\n"
                    "  - 1: you lose your turn total (it becomes 0) and your turn ends.")
            ex = ("Example: you roll 4 (turn total 4), roll 6 (turn total 10), then hold: your banked score\n"
                  "goes up by 10. If instead your third roll had been a 1, you would gain nothing this turn.")
        else:
            roll = ("ROLL: roll two six-sided dice.\n"
                    "  - no 1 on either die: the sum is added to your TURN TOTAL and you choose again;\n"
                    "  - exactly one die shows 1: you lose your turn total and your turn ends;\n"
                    "  - both dice show 1 (snake eyes): you lose your turn total AND your banked score is\n"
                    "    reset to 0, and your turn ends.")
            ex = ("Example: you roll 3+5 (turn total 8), roll 6+2 (turn total 16), then hold: +16 banked.\n"
                  "Rolling 1+4 instead would end your turn with nothing; 1+1 would also wipe your bank.")
        return f"""PIG - {self.label}. 2 players, alternating turns, push-your-luck dice.

GOAL
Be the first to reach {T} banked points.

YOUR TURN
Each turn is a sequence of decisions. At every decision you choose:
{roll}
HOLD: add your turn total to your banked score; your turn ends.
(Holding with a turn total of 0 is allowed; it just passes the turn.)
{ex}
Seat 0 takes the first turn. Turns alternate.

END AND SCORING
As soon as a player's banked score reaches {T} or more (when they hold), they win. Score =
banked points. Move cap: after {MAX_DECISIONS} decisions in total the game ends and the higher
banked score wins (equal = draw).

ACTION FORMAT
Reply with one word: roll | hold
Examples: "roll", "hold", "ROLL". Anything else is illegal (first time: a warning and the same
turn again; second time: you lose the game).

WHAT YOU OBSERVE EACH TURN
Both banked scores, your current turn total and the dice rolled this turn, and a log of the last
20 turns (who rolled what and how the turn ended; older turns are only counted)."""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        return ["roll", "hold"]

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        a = self.clean(action).strip(" .!\"'`")
        return a if a in ("roll", "hold") else None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        seat = self.current
        a = self.normalize(seat, actions.get(seat, ""))
        if a is None:
            raise ValueError(f"illegal action {actions.get(seat)!r} for seat {seat}")
        self.decisions += 1
        if a == "hold":
            self.banked[seat] += self.turn_total
            self.last = {"seat": seat, "act": "hold", "gained": self.turn_total, "turn": self.turn_no}
            if self.banked[seat] >= self.target:
                self.log.append({"turn": self.turn_no, "seat": seat, "rolls": self.turn_rolls, "end": "hold",
                                 "gained": self.turn_total, "banked": list(self.banked)})
                self.turn_rolls = []
                self.turn_total = 0
                self.over, self.winner = True, seat
                self.end_reason = f"seat {seat} reached {self.banked[seat]} (target {self.target})"
                return
            self._end_turn("hold")
        else:
            roll = [self.rng.randint(1, 6) for _ in range(self.dice)]
            self.turn_rolls.append(roll)
            ones = roll.count(1)
            if ones == 0:
                self.turn_total += sum(roll)
                self.last = {"seat": seat, "act": "roll", "roll": roll, "result": "add", "turn": self.turn_no}
            elif ones == 2:
                self.banked[seat] = 0
                self.last = {"seat": seat, "act": "roll", "roll": roll, "result": "snake", "turn": self.turn_no}
                self._end_turn("snake")
            else:
                self.last = {"seat": seat, "act": "roll", "roll": roll, "result": "bust", "turn": self.turn_no}
                self._end_turn("bust")
        if not self.over and self.decisions >= MAX_DECISIONS:
            self.over = True
            b0, b1 = self.banked
            self.winner = None if b0 == b1 else (0 if b0 > b1 else 1)
            self.end_reason = f"move cap of {MAX_DECISIONS} decisions reached with banked scores {b0}-{b1}"

    def is_over(self) -> bool:
        return self.over

    def result(self) -> dict:
        return {"winner": self.winner if self.over else None, "scores": list(self.banked),
                "reason": self.end_reason or "in progress"}

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        who = lambda s: "you" if s == seat else "opponent"  # noqa: E731
        L = [f"PIG - {self.label}. You are seat {seat}. Target: {self.target}."]
        L.append(f"Banked: you {self.banked[seat]}, opponent {self.banked[opp]}.")
        if self.over:
            L.append(f"The game is over: {self.end_reason}.")
        else:
            rolls = ", ".join("+".join(map(str, r)) for r in self.turn_rolls) or "none yet"
            L.append(f"Turn {self.turn_no}: it is {'YOUR' if self.current == seat else 'the opponent' + chr(39) + 's'} turn. "
                     f"Turn total: {self.turn_total} (rolls this turn: {rolls}).")
            if self.current == seat:
                L.append(f"If you hold now you will have {self.banked[seat] + self.turn_total}. Choose: roll | hold")
        if self.log:
            L.append("Previous turns (most recent last):")
            for t in self.log[-20:]:
                rolls = ", ".join("+".join(map(str, r)) for r in t["rolls"]) or "no rolls"
                end = {"hold": f"held for +{t['gained']}", "bust": "rolled a 1, turn lost",
                       "snake": "rolled snake eyes, turn lost and bank reset to 0"}[t["end"]]
                L.append(f"  Turn {t['turn']} ({who(t['seat'])}): {rolls} -> {end}. "
                         f"Banked after: you {t['banked'][seat]}, opponent {t['banked'][opp]}.")
            if len(self.log) > 20:
                L.insert(len(L) - 20, f"  ({len(self.log) - 20} earlier turns omitted)")
        return "\n".join(L)

    def frame(self) -> dict:
        return copy.deepcopy(self._frame())  # snapshot: never share live lists

    def _frame(self) -> dict:
        return {
            "label": self.label, "dice": self.dice, "target": self.target,
            "banked": list(self.banked), "turn_total": self.turn_total, "current": self.current,
            "turn": self.turn_no, "turn_rolls": self.turn_rolls, "log": self.log[-12:],
            "decisions": self.decisions, "last": self.last, "over": self.over,
            "result": self.result() if self.over else None,
        }

    def random_action(self, seat: int, rng: random.Random) -> str:
        if self.turn_total == 0:
            return "roll"
        return "hold" if rng.random() < 0.3 else "roll"
