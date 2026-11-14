"""Nim: mathematical subtraction game with normal and misere goals."""
from __future__ import annotations

import re

from ..core import Game

_TAKE_RE = re.compile(r"^(?:take\s+)?(\d+)\s+(?:from\s+)?(?:pile\s+)?(\d+)$", re.IGNORECASE)


class Nim(Game):
    id = "nim"
    name = "Nim"
    category = "think"
    blurb = "The fundamental subtraction game: take tokens from piles, control the parity, and leave your opponent with no way out."
    howto = "Players alternate removing tokens from one pile. In normal play, whoever takes the last token wins; in misere play, whoever takes the last token loses."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "Normal play, 4 piles", "piles": 4, "lo": 1, "hi": 8, "misere": False, "max_take": 0, "max_piles": 1},
            {"label": "Misere, 3 piles", "piles": 3, "lo": 1, "hi": 6, "misere": True, "max_take": 0, "max_piles": 1},
            {"label": "Take 1-3, 4 piles", "piles": 4, "lo": 1, "hi": 8, "misere": False, "max_take": 3, "max_piles": 1},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "Normal play, 4 piles"))
        self.pile_count = max(1, int(self.variant.get("piles", 4)))
        self.lo = int(self.variant.get("lo", 1))
        self.hi = int(self.variant.get("hi", 8))
        self.misere = bool(self.variant.get("misere", False))
        self.max_take = int(self.variant.get("max_take", 0))
        self.max_piles = int(self.variant.get("max_piles", 1))

        self.initial = [self.rng.randint(self.lo, self.hi) for _ in range(self.pile_count)]
        self.piles = list(self.initial)
        self.current = 0
        self.moves = 0
        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def rules(self) -> str:
        goal = (
            "MISERE PLAY: the player who takes the LAST token LOSES."
            if self.misere
            else "NORMAL PLAY: the player who takes the LAST token WINS (equivalently: if you cannot move, you lose)."
        )
        take_limit = f"between 1 and {self.max_take}" if self.max_take > 0 else "at least 1 token (any number, up to the whole pile)"

        return f"""NIM - {self.label}

SETUP
There are {self.pile_count} piles of tokens, numbered 1 to {self.pile_count}. Each pile starts with a random number of tokens
between {self.lo} and {self.hi} (the arena picks them). Both players see all piles at all times.

TURN ORDER
Player 0 moves first, then the players alternate. Passing is not allowed.
On your turn you remove {take_limit} from exactly ONE pile.

GOAL
{goal}

ACTION FORMAT
    take <count> from pile <p>
Examples:  "take 3 from pile 2"   "take 1 from pile 1"   "take 2 from pile 4"
<count> and <p> are whole numbers written with digits; piles are numbered from 1. The word "pile"
is optional ("take 3 from 2" also works). Taking 0 tokens, taking more tokens than a pile has,
naming a pile that does not exist or any other text is illegal
(first time: a warning and the same turn again; second time: you lose the game). When there are at
most 50 possible moves the arena also sends you the complete list of legal moves.

WHAT YOU OBSERVE
The current size of every pile, the total, whose turn it is, and the full move history.
Example observation fragment:
    Piles now: pile 1 = 5, pile 2 = 0, pile 3 = 7, pile 4 = 2   (total 14)

HOW THE GAME ENDS AND IS SCORED
The game ends when all piles are empty. The player who took the last token {'loses' if self.misere else 'wins'}.
There are no draws. Winner scores 1, loser 0.
Move cap: every move removes at least one token, so the game lasts at most {sum(self.initial)} moves
(the starting total), and it always ends with a winner.
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def _legal_actions_all(self) -> list[str]:
        actions = []
        for p_idx, count in enumerate(self.piles):
            if count <= 0:
                continue
            limit = count if self.max_take <= 0 else min(count, self.max_take)
            for c in range(1, limit + 1):
                actions.append(f"take {c} from pile {p_idx + 1}")
        return actions

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        actions = self._legal_actions_all()
        return self.cap_list(actions)

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        m = _TAKE_RE.match(self.clean(action))
        if not m:
            return None
        count, pile_num = int(m.group(1)), int(m.group(2))
        p_idx = pile_num - 1
        if p_idx < 0 or p_idx >= len(self.piles):
            return None
        if count <= 0 or count > self.piles[p_idx]:
            return None
        if self.max_take > 0 and count > self.max_take:
            return None
        return f"take {count} from pile {pile_num}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        m = _TAKE_RE.match(norm)
        count, pile_num = int(m.group(1)), int(m.group(2))
        p_idx = pile_num - 1
        self.piles[p_idx] -= count
        self.moves += 1

        record = {
            "seat": self.current,
            "action": norm,
            "take": [[p_idx, count]],
            "piles": list(self.piles),
        }
        self.history.append(record)
        self.last = record

        # Check if game over (all piles 0)
        if sum(self.piles) == 0:
            self.over = True
            if self.misere:
                self.winner = 1 - self.current
                self.end_reason = f"seat {self.current} took the last token and loses in misere play"
            else:
                self.winner = self.current
                self.end_reason = f"seat {self.current} took the last token and wins"
        else:
            self.current = 1 - self.current

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        lines = [
            f"NIM ({self.label}). You are Player {seat}.",
            f"Current turn: Player {self.current} (move {self.moves + 1}).",
            "",
            "Piles now: " + ", ".join(f"pile {i + 1} = {cnt}" for i, cnt in enumerate(self.piles)) + f"   (total {sum(self.piles)})",
            "",
            "Move history:",
        ]
        if not self.history:
            lines.append("  (no moves yet)")
        for h in self.history:
            lines.append(f"  Player {h['seat']}: {h['action']} -> left piles {h['piles']}")
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
            "piles": list(self.piles),
            "initial": list(self.initial),
            "misere": self.misere,
            "max_take": self.max_take,
            "max_piles": self.max_piles,
            "history": list(self.history),
            "last": self.last,
            "moves": self.moves,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
