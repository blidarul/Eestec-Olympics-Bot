"""Stag Hunt (Read Opponent Family): simultaneous coordination game balancing high-yield trust against risk aversion."""
from __future__ import annotations

from ..core import Game


class StagHunt(Game):
    id = "stag_hunt"
    name = "Stag Hunt"
    category = "read"
    blurb = "The classic trust-and-safety coordination duel: hunt the Stag together for glory, or take the safe Hare alone."
    howto = "Both players choose simultaneously to hunt Stag or Hare across multiple rounds. Hunting Stag pays 5 points if your partner also hunts Stag, but 0 if they hunt Hare. Hunting Hare guarantees 3 points regardless. Highest total score wins."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "10 rounds", "rounds": 10, "stag_payoff": 5},
            {"label": "15 rounds, Stag bonus (+6)", "rounds": 15, "stag_payoff": 6},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "10 rounds"))
        self.rounds = int(self.variant.get("rounds", 10))
        self.stag_payoff = int(self.variant.get("stag_payoff", 5))

        self.scores = [0, 0]
        self.round = 1
        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def rules(self) -> str:
        sp = self.stag_payoff
        return f"""STAG HUNT (Read Opponent Family) - {self.label}. 2 players, simultaneous moves.

GOAL
Accumulate the most points over {self.rounds} hunting expeditions.

PAYOFF MATRIX
Every round, both players choose simultaneously:
  - Both hunt STAG:  +{sp} points each (mutual coordination and trust!)
  - You hunt STAG, opponent hunts HARE:  you +0, opponent +3 (you were abandoned)
  - You hunt HARE, opponent hunts STAG:  you +3, opponent +0
  - Both hunt HARE:  +3 points each (safe individual fallback)

ACTION FORMAT
    stag   OR   hare   (case does not matter)
Examples: "stag", "hare", "Stag", "HARE".
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        return ["stag", "hare"] if not self.over else []

    def normalize(self, seat: int, action: str) -> str | None:
        c = self.clean(action)
        if c in ("stag", "s"):
            return "stag"
        if c in ("hare", "h"):
            return "hare"
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        m0 = self.normalize(0, actions[0])
        m1 = self.normalize(1, actions[1])

        sp = self.stag_payoff
        if m0 == "stag" and m1 == "stag":
            pts = [sp, sp]
            outcome = "mutual stag"
        elif m0 == "stag" and m1 == "hare":
            pts = [0, 3]
            outcome = "player 1 deserted"
        elif m0 == "hare" and m1 == "stag":
            pts = [3, 0]
            outcome = "player 0 deserted"
        else:
            pts = [3, 3]
            outcome = "mutual hare"

        self.scores[0] += pts[0]
        self.scores[1] += pts[1]

        rec = {
            "round": self.round,
            "moves": [m0, m1],
            "pts": pts,
            "outcome": outcome,
            "scores": list(self.scores),
        }
        self.history.append(rec)
        self.last = rec

        if self.round >= self.rounds:
            self.over = True
            if self.scores[0] > self.scores[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won after {self.rounds} rounds ({self.scores[0]} vs {self.scores[1]} pts)"
            elif self.scores[1] > self.scores[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won after {self.rounds} rounds ({self.scores[1]} vs {self.scores[0]} pts)"
            else:
                self.winner = None
                self.end_reason = f"draw after {self.rounds} rounds with equal points ({self.scores[0]}-{self.scores[1]})"
        else:
            self.round += 1

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        lines = [
            f"STAG HUNT ({self.label}). You are Player {seat}.",
            f"Round {self.round} of {self.rounds}. Scores: you {self.scores[seat]}, opponent {self.scores[opp]}.",
            f"Payoffs: Stag/Stag (+{self.stag_payoff}), Hare (+3 guaranteed), Abandoned Stag (+0).",
            "",
            "Past expeditions history:",
        ]
        if not self.history:
            lines.append("  (first expedition)")
        for h in self.history:
            my_move = h["moves"][seat]
            opp_move = h["moves"][opp]
            lines.append(f"  Round {h['round']}: you {my_move} (+{h['pts'][seat]}), opp {opp_move} (+{h['pts'][opp]}) -> {h['outcome']}")
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": list(self.scores),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "round": self.round,
            "rounds": self.rounds,
            "scores": list(self.scores),
            "history": list(self.history),
            "last": self.last,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
