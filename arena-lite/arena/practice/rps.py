"""Rock Paper Scissors: simultaneous throws, reading opponent patterns and chat mind games."""
from __future__ import annotations

from ..core import Game

SIGNS = ("rock", "paper", "scissors")
BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
VERBS = {("rock", "scissors"): "crushes", ("scissors", "paper"): "cut", ("paper", "rock"): "covers"}


class RockPaperScissors(Game):
    id = "rps"
    name = "Rock Paper Scissors"
    category = "read"
    blurb = "The oldest mind game: three signs, no luck, just spotting your rival's habits before they spot yours."
    howto = "Both players throw rock, paper or scissors at the same time: rock crushes scissors, scissors cut paper, paper covers rock. Win throws to score; the higher score wins."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "First to 5", "target": 5, "max_throws": 25, "double": [], "no_triple": False},
            {"label": "15 throws, Rock wins count double", "target": 0, "max_throws": 15, "double": ["rock"], "no_triple": False},
            {"label": "First to 4, no sign three times in a row", "target": 4, "max_throws": 25, "double": [], "no_triple": True},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "First to 5"))
        self.target = int(self.variant.get("target", 5))
        self.max_throws = int(self.variant.get("max_throws", 25))
        self.double = list(self.variant.get("double", []))
        self.no_triple = bool(self.variant.get("no_triple", False))

        self.points = [0, 0]
        self.throws: list[dict] = []
        self.n = 0
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""
        self.last: dict | None = None

    def _banned(self, seat: int) -> list[str]:
        if not self.no_triple or len(self.throws) < 2:
            return []
        s1 = self.throws[-1]["signs"][seat]
        s2 = self.throws[-2]["signs"][seat]
        if s1 == s2:
            return [s1]
        return []

    def rules(self) -> str:
        goal_text = (
            f"Be the first to reach {self.target} points. Each throw you win scores 1 point."
            if self.target > 0
            else f"Play exactly {self.max_throws} throws. The player with more points wins."
        )
        if self.double:
            goal_text += f" Winning with {', '.join(self.double).capitalize()} scores 2 points."
        if self.no_triple:
            goal_text += " No player may throw the same sign three times in a row."

        return f"""ROCK PAPER SCISSORS - {self.label}. 2 players, simultaneous throws.

GOAL
{goal_text} If {self.max_throws} throws are played without anyone reaching the target (move cap),
the player with more points wins; equal points = draw.

EACH THROW
Both players choose one of three signs at the same time: rock, paper, scissors.
Then both signs are revealed:
  Rock crushes Scissors   (rock beats scissors)
  Scissors cut Paper      (scissors beats paper)
  Paper covers Rock       (paper beats rock)
Same sign = tie, nobody scores.

STRATEGY NOTE
Any single throw is a guess; the game is won by noticing patterns in your opponent's past
throws (and hiding your own). The full throw history is in every observation. You may talk to
your opponent in the match chat ("chat" field of your answer): announce, bluff, provoke.
Nothing said in the chat is binding.

ACTION FORMAT
Reply with one sign name: rock | paper | scissors   (case does not matter)
Examples: "rock", "Paper", "scissors". Anything else is illegal (first time: a warning and
the same turn again; second time: you lose the game). You also receive the list of legal
actions every turn.

WHAT YOU OBSERVE EACH TURN
The throw number, both scores, the target, and every previous throw (your sign, the opponent's
sign, who won it and how many points it scored).
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        banned = self._banned(seat)
        return [s for s in SIGNS if s not in banned]

    def normalize(self, seat: int, action: str) -> str | None:
        cleaned = self.clean(action)
        if cleaned in (self.legal_actions(seat) or []):
            return cleaned
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        s0 = actions[0]
        s1 = actions[1]
        self.n += 1

        if s0 == s1:
            winner = None
            verb = ""
            pts = 0
        elif BEATS[s0] == s1:
            winner = 0
            verb = VERBS[(s0, s1)]
            pts = 2 if s0 in self.double else 1
            self.points[0] += pts
        else:
            winner = 1
            verb = VERBS[(s1, s0)]
            pts = 2 if s1 in self.double else 1
            self.points[1] += pts

        record = {
            "n": self.n,
            "signs": [s0, s1],
            "winner": winner,
            "verb": verb,
            "pts": pts,
            "points": list(self.points),
        }
        self.throws.append(record)
        self.last = record

        # Check game over conditions
        if self.target > 0 and (self.points[0] >= self.target or self.points[1] >= self.target):
            self.over = True
            if self.points[0] > self.points[1]:
                self.winner = 0
                self.end_reason = f"seat 0 reached {self.target} points first ({self.points[0]}-{self.points[1]} after {self.n} throws)"
            elif self.points[1] > self.points[0]:
                self.winner = 1
                self.end_reason = f"seat 1 reached {self.target} points first ({self.points[1]}-{self.points[0]} after {self.n} throws)"
            else:
                self.winner = None
                self.end_reason = f"both players reached {self.target} points ({self.points[0]}-{self.points[1]} draw)"
        elif self.n >= self.max_throws:
            self.over = True
            if self.points[0] > self.points[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won after {self.max_throws} throws ({self.points[0]}-{self.points[1]})"
            elif self.points[1] > self.points[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won after {self.max_throws} throws ({self.points[1]}-{self.points[0]})"
            else:
                self.winner = None
                self.end_reason = f"draw after {self.max_throws} throws ({self.points[0]}-{self.points[1]})"

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        target_info = f"First to {self.target} points" if self.target > 0 else f"{self.max_throws} throws total"
        lines = [
            f"ROCK PAPER SCISSORS. You are Player {seat}.",
            f"Throw {self.n + 1} of at most {self.max_throws}. Target: {target_info}.",
            f"Current score: you {self.points[seat]} - opponent {self.points[opp]}.",
            "",
            "Past throws history:",
        ]
        if not self.throws:
            lines.append("  (none yet)")
        for t in self.throws:
            my_sign = t["signs"][seat]
            opp_sign = t["signs"][opp]
            if t["winner"] is None:
                res = "tie"
            elif t["winner"] == seat:
                res = f"you won (+{t['pts']})"
            else:
                res = f"opponent won (+{t['pts']})"
            lines.append(f"  Throw {t['n']}: you {my_sign} vs opponent {opp_sign} -> {res}")

        banned = self._banned(seat)
        if banned:
            lines.append(f"\nNOTE: You threw {banned[0]} twice in a row; {banned[0]} is BANNED this throw.")
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": list(self.points),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "target": self.target,
            "max_throws": self.max_throws,
            "double": list(self.double),
            "no_triple": self.no_triple,
            "points": list(self.points),
            "throws": list(self.throws),
            "n": self.n,
            "banned": [self._banned(0), self._banned(1)],
            "to_move": self.to_move(),
            "last": self.last,
            "over": self.over,
            "result": self.result() if self.over else None,
        }
