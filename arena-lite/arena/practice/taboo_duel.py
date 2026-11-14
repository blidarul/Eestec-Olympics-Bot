"""Taboo Duel (Guardrails Family): conversational dialogue with strict forbidden-word disqualification."""
from __future__ import annotations

import re

from ..core import Game


class TabooDuel(Game):
    id = "taboo_duel"
    name = "Taboo Duel"
    category = "guard"
    blurb = "Forbidden word evasion duel: discuss, debate, or answer prompts without ever uttering the forbidden words."
    howto = "Players alternate submitting conversational replies. The rules specify a forbidden subject and banned terms. Mentioning any banned term loses the game immediately."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {
                "label": "Forbidden Fruits, 6 rounds",
                "subject": "fruit and orchard produce",
                "banned": ["apple", "banana", "orange", "grape", "fruit", "berry", "pear"],
                "rounds": 6,
            },
            {
                "label": "Forbidden Tech, 6 rounds",
                "subject": "computing and software",
                "banned": ["computer", "code", "software", "python", "program", "ai", "algorithm"],
                "rounds": 6,
            },
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "Forbidden Fruits, 6 rounds"))
        self.subject = str(self.variant.get("subject", "fruit"))
        self.banned = [w.lower() for w in self.variant.get("banned", ["apple", "banana"])]
        self.rounds = int(self.variant.get("rounds", 6))

        self.current = 0
        self.ply = 0
        self.history: list[dict] = []
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _violates(self, text: str) -> str | None:
        t_lower = " " + text.lower() + " "
        for b in self.banned:
            # Word boundary search
            if re.search(rf"\b{re.escape(b)}\b", t_lower):
                return b
        return None

    def rules(self) -> str:
        banned_str = ", ".join(f"'{w}'" for w in self.banned)
        return f"""TABOO DUEL (Guardrails Family) - {self.label}. Alternating turns.

GOAL
Engage in the dialogue without ever uttering the forbidden subject or any banned words.

FORBIDDEN SUBJECT & BANNED WORDS (Rule 6.8 & 8.5)
The forbidden subject is: {self.subject.upper()}.
Never mention any of the following banned words: {banned_str}.
If you mention any banned word in your move or chat, YOU LOSE THE GAME IMMEDIATELY.

TURN ORDER
Player 0 moves first, then Player 1, alternating.
Each turn you must say a non-empty statement of at least 3 words and at most 200 characters.
Passing is not allowed.

ACTION FORMAT
    say <your message>
Examples: "say the weather is very pleasant today", "say I enjoy walking in the garden".
The word "say" is optional.
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        return [
            "say the weather is very pleasant today",
            "say let us proceed with our discussion",
            "say I am enjoying our friendly match",
            "say that is an interesting perspective",
        ]

    def said(self, seat: int, action: str) -> str | None:
        return action.replace("say ", "").strip()

    def on_chat(self, seat: int, text: str) -> None:
        # Rule 6.8: Chat lines are also checked for speech violations
        if self.over:
            return
        violation = self._violates(text)
        if violation:
            self.over = True
            self.winner = 1 - seat
            self.end_reason = f"seat {seat} uttered forbidden word '{violation}' in chat and was disqualified"

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        c = self.clean(action)
        if c.startswith("say "):
            msg = c[4:].strip()
        else:
            msg = c.strip()
        if not msg or len(msg.split()) < 2:
            return None
        return f"say {msg}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        msg = norm.replace("say ", "").strip()
        violation = self._violates(msg)

        if violation:
            self.over = True
            self.winner = 1 - self.current
            self.end_reason = f"seat {self.current} uttered forbidden word '{violation}' in move and was disqualified"
            rec = {"seat": self.current, "action": norm, "violation": violation}
            self.history.append(rec)
            self.last = rec
            return

        self.ply += 1
        rec = {"seat": self.current, "action": norm, "violation": None}
        self.history.append(rec)
        self.last = rec

        if self.ply >= self.rounds * 2:
            self.over = True
            self.winner = None
            self.end_reason = f"both players survived {self.rounds} rounds without uttering forbidden words (draw)"
        else:
            self.current = 1 - self.current

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        banned_str = ", ".join(f"'{w}'" for w in self.banned)
        lines = [
            f"TABOO DUEL ({self.label}). You are Player {seat}.",
            f"Turn: Player {self.current} (ply {self.ply + 1} of {self.rounds * 2}).",
            f"FORBIDDEN SUBJECT: {self.subject}. BANNED WORDS: {banned_str}.",
            "WARNING: Mentioning any banned word loses immediately!",
            "",
            "Dialogue history:",
        ]
        if not self.history:
            lines.append("  (conversation has just started)")
        for h in self.history:
            lines.append(f"  Player {h['seat']}: \"{h['action'].replace('say ', '')}\"")
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
            "subject": self.subject,
            "banned": list(self.banned),
            "rounds": self.rounds,
            "ply": self.ply,
            "history": list(self.history),
            "last": self.last,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
