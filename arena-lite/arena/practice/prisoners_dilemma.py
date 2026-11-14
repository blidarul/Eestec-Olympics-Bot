"""Prisoner's Dilemma: simultaneous choices, trust building, negotiation via chat."""
from __future__ import annotations

from ..core import Game


class PrisonersDilemma(Game):
    id = "prisoners_dilemma"
    name = "Prisoner's Dilemma"
    category = "deals"
    blurb = "The classic trust problem with match chat: cooperate to qualify, defect to steal the lead, and negotiate or bluff your way through."
    howto = "Both players choose cooperate or defect simultaneously. Cooperate scores 3 each; defection scores 5 against 0 or 1 against 1. Reach the quota or finish with fewer defections to win."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "Qualify at 25, at least 8 rounds", "quota": 25, "min_rounds": 8, "end_one_in": 4, "max_rounds": 20},
            {"label": "Long game: qualify at 40, at least 12 rounds", "quota": 40, "min_rounds": 12, "end_one_in": 4, "max_rounds": 25},
            {"label": "Short fuse: qualify at 16, at least 5 rounds", "quota": 16, "min_rounds": 5, "end_one_in": 4, "max_rounds": 15},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "Qualify at 25, at least 8 rounds"))
        self.quota = int(self.variant.get("quota", 25))
        self.min_rounds = int(self.variant.get("min_rounds", 8))
        self.end_one_in = int(self.variant.get("end_one_in", 4))
        self.max_rounds = int(self.variant.get("max_rounds", 20))

        # Roll hidden horizon
        r = self.min_rounds
        while r < self.max_rounds:
            if self.rng.randint(1, self.end_one_in) == 1:
                break
            r += 1
        self.horizon = r

        self.round = 0
        self.points = [0, 0]
        self.defections = [0, 0]
        self.rounds: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _standing(self) -> dict:
        q = self.quota
        p0, p1 = self.points
        d0, d1 = self.defections
        if p0 >= q and p1 < q:
            return {"winner": 0, "reason": f"seat 0 reached quota {q} ({p0} vs {p1})"}
        if p1 >= q and p0 < q:
            return {"winner": 1, "reason": f"seat 1 reached quota {q} ({p1} vs {p0})"}
        if p0 >= q and p1 >= q:
            if p0 > p1:
                return {"winner": 0, "reason": f"both reached quota {q}, seat 0 leads {p0}-{p1}"}
            elif p1 > p0:
                return {"winner": 1, "reason": f"both reached quota {q}, seat 1 leads {p1}-{p0}"}
            else:
                return {"winner": None, "reason": f"both reached quota {q} with equal points {p0}-{p1}"}
        # Neither reached quota
        if d0 < d1:
            return {"winner": 0, "reason": f"nobody reached {q}; seat 0 has fewer defections ({d0} vs {d1})"}
        elif d1 < d0:
            return {"winner": 1, "reason": f"nobody reached {q}; seat 1 has fewer defections ({d1} vs {d0})"}
        else:
            return {"winner": None, "reason": f"nobody reached {q} (seat 0 has {p0}, seat 1 has {p1}) and both defected {d0} times"}

    def rules(self) -> str:
        return f"""PRISONER'S DILEMMA (with talk) - {self.label}. 2 players, simultaneous moves.

EACH ROUND
Both players secretly choose COOPERATE or DEFECT; then both choices are revealed and scored:
  both cooperate             -> +3 each
  you defect, they cooperate -> you +5, they +0   (a betrayal)
  you cooperate, they defect -> you +0, they +5
  both defect                -> +1 each
Points add up over the whole game. Every "defect" you play also counts as one DEFECTION on your
record (a betrayal and a mutual defection both count).

HOW LONG
The game lasts at least {self.min_rounds} rounds. After round {self.min_rounds} and after every later round it ends with a 1 in {self.end_one_in} chance (it never goes beyond round {self.max_rounds}). Nobody knows the real length in advance.
So any round from round {self.min_rounds} on may be the last one. The arena tells you after each round whether
the game goes on.

WINNING (at the end of the game)
The qualifying score is {self.quota} points.
  1. Only one player has at least {self.quota} points: that player wins.
  2. Both have at least {self.quota}: the player with more points wins (equal points = draw).
  3. Nobody has {self.quota}: the player with FEWER DEFECTIONS wins (equal defections = draw).
You cannot reach {self.quota} without the opponent's cooperation: defecting every round against a player who
answers defection with defection gives you about 1 point a round, and then you lose on rule 3.
Mutual cooperation gives 3 a round. A betrayal gives you 5 and puts you 5 points ahead, but it
usually ends the trust: if the game stops before you reach {self.quota}, you lose on rule 3.

TALK (the match chat)
This game has no message field of its own: talking happens in the match chat (the "chat" field
of your answers, max 200 characters; you read the whole conversation in every message). Use it
for promises, threats, deals and apologies.

ACTION FORMAT
Reply with exactly one word: cooperate | defect   (case does not matter; "c" and "d" are also
accepted). Examples: "cooperate", "defect". Anything else is illegal (first time: a warning and
the same turn again; second time: you lose the game). Both players answer every round.

WHAT YOU OBSERVE EACH ROUND
The round number, both scores and defection counts, every previous round (both moves and points),
whether each player has qualified, who would win if the game ended right now, and the length rule.

MOVE CAP
At most {self.max_rounds} rounds (the length rule above already guarantees this).
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        return ["cooperate", "defect"] if not self.over else []

    def normalize(self, seat: int, action: str) -> str | None:
        c = self.clean(action)
        if c in ("cooperate", "c"):
            return "cooperate"
        if c in ("defect", "d"):
            return "defect"
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        m0 = actions[0]
        m1 = actions[1]
        self.round += 1

        if m0 == "cooperate" and m1 == "cooperate":
            pts = [3, 3]
            kind = "cooperate"
            betrayer = None
        elif m0 == "defect" and m1 == "cooperate":
            pts = [5, 0]
            kind = "betrayal"
            betrayer = 0
            self.defections[0] += 1
        elif m0 == "cooperate" and m1 == "defect":
            pts = [0, 5]
            kind = "betrayal"
            betrayer = 1
            self.defections[1] += 1
        else:
            pts = [1, 1]
            kind = "mutual_defect"
            betrayer = None
            self.defections[0] += 1
            self.defections[1] += 1

        self.points[0] += pts[0]
        self.points[1] += pts[1]

        rec = {
            "n": self.round,
            "moves": [m0, m1],
            "pts": pts,
            "kind": kind,
            "betrayer": betrayer,
            "points": list(self.points),
            "defections": list(self.defections),
        }
        self.rounds.append(rec)
        self.last = rec

        # Check if match ends
        if self.round >= self.horizon or self.round >= self.max_rounds:
            self.over = True
            st = self._standing()
            self.winner = st["winner"]
            self.end_reason = f"game ended at round {self.round}; {st['reason']}"

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        st = self._standing()
        lines = [
            f"PRISONER'S DILEMMA ({self.label}). You are Player {seat}.",
            f"Round {self.round + 1} (min {self.min_rounds}, max {self.max_rounds}).",
            f"Scores: you {self.points[seat]} (defections: {self.defections[seat]}), opponent {self.points[opp]} (defections: {self.defections[opp]}). Quota: {self.quota}.",
            f"Current standing if game ended now: {st['reason']}.",
            "",
            "Round history:",
        ]
        if not self.rounds:
            lines.append("  (none yet)")
        for r in self.rounds:
            lines.append(f"  Round {r['n']}: you {r['moves'][seat]} (+{r['pts'][seat]}), opponent {r['moves'][opp]} (+{r['pts'][opp]})")
        return "\n".join(lines)

    def result(self) -> dict:
        scores = [0, 0]
        if self.winner is not None:
            scores[self.winner] = 1
        elif self.over:
            scores = [0.5, 0.5]
        return {
            "winner": self.winner,
            "scores": scores,
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "quota": self.quota,
            "min_rounds": self.min_rounds,
            "end_one_in": self.end_one_in,
            "max_rounds": self.max_rounds,
            "horizon": self.horizon,
            "points": list(self.points),
            "defections": list(self.defections),
            "rounds": list(self.rounds),
            "round": self.round,
            "standing": self._standing(),
            "to_move": self.to_move(),
            "last": self.last,
            "over": self.over,
            "result": self.result() if self.over else None,
        }
