"""Test game with a SPEECH RESTRICTION (the practice games have none): Count to N, and never say "banana".

Two players add 1, 2 or 3 to a running total; whoever makes it exactly N wins. The rules name a forbidden
subject; a chat line that contains it (even spaced out or in leetspeak) loses the game at once, also the line
sent with `ready`. The check here is written independently of chat/speech_rules.py on purpose.
"""
import re
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "arena-lite")))
from arena.core import Game  # noqa: E402

FORBIDDEN = "banana"


def says_forbidden(text):
    t = text.lower().translate(str.maketrans("0134578@$", "oieastba" + "s"))
    t = re.sub(r"[^a-z]", "", t)
    t = re.sub(r"(.)\1+", r"\1", t)  # b-a-a-n-a-n-a
    return re.sub(r"(.)\1+", r"\1", FORBIDDEN) in t or FORBIDDEN in t


class ForbiddenCount(Game):
    id = "forbidden_count"
    name = "Count to N (banana ban)"
    category = "guard"
    blurb = "A counting race where one word is forbidden in the chat."
    howto = "Add 1, 2 or 3 to the total. Reach N exactly to win. Never mention the forbidden subject in the chat."
    duplicate_safe = True

    @classmethod
    def variants(cls):
        return [{"label": "to 12", "target": 12}, {"label": "to 15", "target": 15}]

    def __init__(self, variant, seed):
        super().__init__(variant, seed)
        self.target = int(self.variant.get("target", 12))
        self.total, self.cur, self.winner, self._over, self.reason = 0, 0, None, False, ""
        self.history = []

    def rules(self):
        return f"""COUNT TO {self.target} - 2 players, alternating turns. Player 0 starts.

GOAL
A running total starts at 0. On your turn add 1, 2 or 3 to it. The player who makes the total exactly
{self.target} wins. You may not go over {self.target}.

ACTION FORMAT
Answer with exactly one of: "add 1", "add 2", "add 3" (only the ones that keep the total at or below {self.target}).

SPEECH RULE (applies to EVERY chat line you send, including the line you send with ready)
FORBIDDEN SUBJECT: the word "{FORBIDDEN}". You must never mention it in any chat line, in any spelling.
If you do, you lose the game on the spot."""

    def to_move(self):
        return [] if self._over else [self.cur]

    def observation(self, seat):
        h = "\n".join(f"  {'you' if s == seat else 'opponent'} added {n} -> total {t}" for s, n, t in self.history) or "  (no moves yet)"
        return (f"COUNT TO {self.target}. You are Player {seat}.\nTotal now: {self.total}\nHistory:\n{h}\n"
                f"It is {'YOUR' if self.cur == seat else 'the opponent'} turn.")

    def legal_actions(self, seat):
        return [f"add {n}" for n in (1, 2, 3) if self.total + n <= self.target]

    def normalize(self, seat, action):
        a = self.clean(action)
        return a if a in self.legal_actions(seat) else None

    def apply(self, actions):
        n = int(actions[self.cur].split()[1])
        self.total += n
        self.history.append((self.cur, n, self.total))
        if self.total == self.target:
            self.winner, self._over, self.reason = self.cur, True, f"Player {self.cur} reached {self.target}"
        else:
            self.cur = 1 - self.cur

    def on_chat(self, seat, text):
        if not self._over and says_forbidden(text):
            self.winner, self._over = 1 - seat, True
            self.reason = f"Player {seat} mentioned the forbidden subject"

    def is_over(self):
        return self._over

    def result(self):
        s = [1, 0] if self.winner == 0 else [0, 1] if self.winner == 1 else [0, 0]
        return {"winner": self.winner, "scores": s, "reason": self.reason or "draw"}

    def frame(self):
        return {"label": self.variant.get("label"), "total": self.total, "target": self.target, "to_move": self.cur,
                "moves": [list(h) for h in self.history]}
