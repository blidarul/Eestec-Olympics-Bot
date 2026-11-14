"""Bulls and Cows: simultaneous code-breaking duel with Mastermind feedback."""
from __future__ import annotations

import re

from ..core import Game

_GUESS_RE = re.compile(r"^(?:guess\s+)?([A-Za-z0-9]+)$", re.IGNORECASE)


class BullsAndCows(Game):
    id = "bulls_and_cows"
    name = "Bulls and Cows"
    category = "guess"
    blurb = "Simultaneous code-breaking: crack your opponent's secret combination before they crack yours."
    howto = "Both players guess each other's secret code simultaneously. Bulls are right characters in right places; cows are right characters in wrong places. First to get all bulls wins."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "4 digits, no repeats", "alphabet": "0123456789", "length": 4, "repeats": False, "max_rounds": 10},
            {"label": "5 digits, repeats allowed", "alphabet": "0123456789", "length": 5, "repeats": True, "max_rounds": 10},
            {"label": "4 letters A-F, repeats allowed", "alphabet": "ABCDEF", "length": 4, "repeats": True, "max_rounds": 10},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "4 digits, no repeats"))
        self.alphabet = str(self.variant.get("alphabet", "0123456789")).upper()
        self.length = int(self.variant.get("length", 4))
        self.repeats = bool(self.variant.get("repeats", False))
        self.max_rounds = int(self.variant.get("max_rounds", 10))

        # Generate secrets
        self.codes = [self._generate_code(), self._generate_code()]
        self.guesses: list[list[dict]] = [[], []]
        self.best: list[list[int]] = [[0, 0], [0, 0]]  # [seat] = [best_bulls, best_cows]
        self.round = 1
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""
        self.last: dict | None = None

    def _generate_code(self) -> str:
        if self.repeats:
            return "".join(self.rng.choice(self.alphabet) for _ in range(self.length))
        else:
            return "".join(self.rng.sample(self.alphabet, self.length))

    def _score(self, code: str, guess: str) -> tuple[int, int]:
        bulls = sum(1 for c, g in zip(code, guess) if c == g)
        common = sum(min(code.count(ch), guess.count(ch)) for ch in set(self.alphabet))
        cows = common - bulls
        return bulls, cows

    def rules(self) -> str:
        rep_desc = "All characters are DIFFERENT (no repeats)" if not self.repeats else "Repeated characters are allowed"
        return f"""BULLS AND COWS - {self.label}. 2 players, a simultaneous code-breaking race.

SECRET CODES
The arena gives each player a secret code of {self.length} characters from {self.alphabet}. {rep_desc}, and your guesses must also follow this rule.
Your opponent tries to crack YOUR code and you try to crack THEIRS. You see your own code
(it does not affect your play) but never the opponent's.

EACH ROUND
Both players submit one guess at the opponent's code at the same time. Each guess gets
feedback:
  - BULLS: how many positions hold exactly the right symbol;
  - COWS: how many further symbols are in the code but at a different position.
Counting with repeats works like Mastermind: for every symbol, take the smaller of its count
in the guess and in the code, add these up, and subtract the bulls; the rest are cows.
Example: code 4721, guess 1724 -> 2 bulls, 2 cows.

END AND SCORING
- Crack the code (a guess with {self.length} bulls) to win. If both players crack in the same round, the
  game is a draw.
- Move cap: at most {self.max_rounds} rounds. If nobody has cracked by then, the player whose BEST guess
  had more bulls wins; equal bulls -> more cows in that best guess wins; still equal -> draw.
Your score = bulls of your best guess.

ACTION FORMAT
    guess <code>      exactly {self.length} characters from {self.alphabet}{', all different' if not self.repeats else ''}
The word "guess" is optional. Examples: "guess {''.join(self.alphabet[:self.length])}".
A guess with the wrong length, other symbols, or repeated symbols is illegal
(first time: a warning and the same turn again; second time: you lose the game).
The legal-actions list is null (too many possible codes).

WHAT YOU OBSERVE EACH TURN
The round number, your own secret code, all your previous guesses with their feedback, and all
your opponent's previous guesses at your code with their feedback.
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        return None  # large action space

    def normalize(self, seat: int, action: str) -> str | None:
        m = _GUESS_RE.match(self.clean(action))
        if not m:
            return None
        guess = m.group(1).upper()
        if len(guess) != self.length:
            return None
        if any(ch not in self.alphabet for ch in guess):
            return None
        if not self.repeats and len(set(guess)) != self.length:
            return None
        return f"guess {guess}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        g0 = self.normalize(0, actions[0]).split()[-1]
        g1 = self.normalize(1, actions[1]).split()[-1]

        # Seat 0 guesses code 1, Seat 1 guesses code 0
        b0, c0 = self._score(self.codes[1], g0)
        b1, c1 = self._score(self.codes[0], g1)

        self.guesses[0].append({"round": self.round, "guess": g0, "bulls": b0, "cows": c0})
        self.guesses[1].append({"round": self.round, "guess": g1, "bulls": b1, "cows": c1})

        # Update best
        if (b0, c0) > tuple(self.best[0]):
            self.best[0] = [b0, c0]
        if (b1, c1) > tuple(self.best[1]):
            self.best[1] = [b1, c1]

        self.last = {
            "round": self.round,
            "guesses": [g0, g1],
            "feedback": [[b0, c0], [b1, c1]],
        }

        # Check win condition
        win0 = b0 == self.length
        win1 = b1 == self.length
        if win0 and win1:
            self.over = True
            self.winner = None
            self.end_reason = f"both cracked the code in round {self.round} (draw)"
        elif win0:
            self.over = True
            self.winner = 0
            self.end_reason = f"seat 0 cracked the code in round {self.round}"
        elif win1:
            self.over = True
            self.winner = 1
            self.end_reason = f"seat 1 cracked the code in round {self.round}"
        elif self.round >= self.max_rounds:
            self.over = True
            if self.best[0] > self.best[1]:
                self.winner = 0
                self.end_reason = f"seat 0 had a better best guess ({self.best[0]} vs {self.best[1]}) after {self.max_rounds} rounds"
            elif self.best[1] > self.best[0]:
                self.winner = 1
                self.end_reason = f"seat 1 had a better best guess ({self.best[1]} vs {self.best[0]}) after {self.max_rounds} rounds"
            else:
                self.winner = None
                self.end_reason = f"draw after {self.max_rounds} rounds with equal best guesses ({self.best[0]})"
        else:
            self.round += 1

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        lines = [
            f"BULLS AND COWS ({self.label}). You are Player {seat}.",
            f"Your secret code (the opponent is trying to crack it): {self.codes[seat]}",
            f"Round {self.round} of {self.max_rounds}.",
            "",
            "Your previous guesses at opponent's code:",
        ]
        if not self.guesses[seat]:
            lines.append("  (none yet)")
        for g in self.guesses[seat]:
            lines.append(f"  Round {g['round']}: guess {g['guess']} -> {g['bulls']} bulls, {g['cows']} cows")

        lines.append("")
        lines.append("Opponent's previous guesses at your code:")
        if not self.guesses[opp]:
            lines.append("  (none yet)")
        for g in self.guesses[opp]:
            lines.append(f"  Round {g['round']}: guess {g['guess']} -> {g['bulls']} bulls, {g['cows']} cows")

        return "\n".join(lines)

    def result(self) -> dict:
        scores = [self.best[0][0], self.best[1][0]]
        return {
            "winner": self.winner,
            "scores": scores,
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "label": self.label,
            "alphabet": self.alphabet,
            "length": self.length,
            "repeats": self.repeats,
            "round": self.round,
            "max_rounds": self.max_rounds,
            "codes": list(self.codes),
            "guesses": list(self.guesses),
            "best": list(self.best),
            "last": self.last,
            "over": self.over,
            "result": self.result() if self.over else None,
        }
