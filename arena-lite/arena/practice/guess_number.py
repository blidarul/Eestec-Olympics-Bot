"""Guess the Number: race to find the opponent's secret number with higher/lower feedback."""
from __future__ import annotations

from ..core import Game


class GuessNumber(Game):
    id = "guess_number"
    name = "Guess the Number"
    category = "practice"
    blurb = "Binary search as a race: each answer halves the haystack, every wasted guess hands the lead away."
    howto = "Each player has a secret number and tries to find the other's. After every guess you hear 'higher' or 'lower'. First to find the number wins."
    duplicate_safe = False  # secret numbers (core.Game.duplicate_safe)

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "1-100", "lo": 1, "hi": 100, "max_guesses": 12},
            {"label": "1-1000", "lo": 1, "hi": 1000, "max_guesses": 15},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.lo = int(self.variant.get("lo", 1))
        self.hi = int(self.variant.get("hi", 100))
        self.max_guesses = int(self.variant.get("max_guesses", 12))
        self.secrets = [self.rng.randint(self.lo, self.hi), self.rng.randint(self.lo, self.hi)]
        # guesses[seat] = guesses made BY seat at the OPPONENT's number: (n, "higher"/"lower"/"correct")
        self.guesses: list[list[tuple[int, str]]] = [[], []]
        self.found: list[int | None] = [None, None]  # round in which seat found the opponent's number
        self.round = 1
        self.current = 0
        self._over = False
        self.max_steps = 2 * self.max_guesses
        self._result: dict | None = None

    def interval(self, seat: int) -> tuple[int, int]:
        """Range still possible for the number `seat` is searching (the opponent's secret)."""
        lo, hi = self.lo, self.hi
        for n, fb in self.guesses[seat]:
            if fb == "higher":
                lo = max(lo, n + 1)
            elif fb == "lower":
                hi = min(hi, n - 1)
            else:
                lo = hi = n
        return lo, hi

    def rules(self) -> str:
        lo, hi, cap = self.lo, self.hi, self.max_guesses
        mid = (lo + hi) // 2
        return f"""GUESS THE NUMBER - range {lo}-{hi}, at most {cap} guesses each.

SETUP
The arena gives each player a secret whole number between {lo} and {hi} (inclusive), chosen at
random. You know your own number; your opponent is trying to find it. You are trying to find
your opponent's number. (The two numbers are independent and may even be equal.)

TURN ORDER
Player 0 guesses first, then Player 1, alternating. One "round" = one guess by each player.

ACTION FORMAT
    guess <n>
where <n> is a whole number from {lo} to {hi} (digits only). Examples:  "guess {mid}"   "guess {lo}"   "{hi}"
(a bare number also works). Numbers outside the range or any other text are illegal
(first time: a warning and the same turn again; second time: you lose the game). Repeating an
earlier guess is legal but wastes a turn.

FEEDBACK
After each guess you are told about the OPPONENT's secret number:
    "higher"  : their number is greater than your guess
    "lower"   : their number is smaller than your guess
    "correct" : you found it
You also see every guess your opponent made at YOUR number and the feedback they got.

WHAT YOU OBSERVE
Your own secret number, the round, all your guesses with feedback and all the opponent's guesses
with feedback. Example line:  "Round 2: you guessed {mid} -> higher (their number is above {mid})".

HOW THE GAME ENDS AND IS SCORED
The game is checked at the END of every round, so both players always get the same number of guesses:
- if only one player has found the opponent's number, that player wins;
- if both found it in the same round, it is a draw.
Guess cap: after round {cap}, if nobody has found it, the player whose feedback narrows the opponent's
number down to FEWER possible values wins (e.g. "between 40 and 44" = 5 values beats "between 10 and
29" = 20 values); equal = draw. Score: winner 1, loser 0, draw 0.5 each.
"""

    def to_move(self) -> list[int]:
        return [] if self._over else [self.current]

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        lines = [f"GUESS THE NUMBER ({self.lo}-{self.hi}). You are Player {seat}.",
                 f"Your secret number (the opponent is looking for it): {self.secrets[seat]}",
                 f"Round {min(self.round, self.max_guesses)} of {self.max_guesses}.", ""]
        lines.append("Your guesses at the opponent's number:")
        if not self.guesses[seat]:
            lines.append("  (none yet)")
        for i, (n, fb) in enumerate(self.guesses[seat], 1):
            extra = {"higher": f"their number is above {n}", "lower": f"their number is below {n}", "correct": "found it"}[fb]
            lines.append(f"  Round {i}: you guessed {n} -> {fb} ({extra})")
        lines.append("Opponent's guesses at your number:")
        if not self.guesses[opp]:
            lines.append("  (none yet)")
        for i, (n, fb) in enumerate(self.guesses[opp], 1):
            lines.append(f"  Round {i}: opponent guessed {n} -> {fb}")
        lines.append("")
        if self._over:
            lines.append(f"Game over: {self._result['reason']}. The opponent's number was {self.secrets[opp]}.")
        elif self.current == seat:
            lines.append(f'It is YOUR turn: "guess <n>" with n from {self.lo} to {self.hi}.')
        else:
            lines.append("It is the opponent's turn.")
        return "\n".join(lines)

    def legal_actions(self, seat: int) -> list[str] | None:
        if self._over or seat != self.current:
            return []
        return self.cap_list([f"guess {n}" for n in range(self.lo, self.hi + 1)])

    def random_action(self, seat: int, rng) -> str:
        """Random legal guess for tests/fixtures: usually inside the still-possible range."""
        lo, hi = self.interval(seat)
        if rng.random() < 0.7 and lo <= hi:
            return f"guess {rng.randint(lo, hi)}"
        return f"guess {rng.randint(self.lo, self.hi)}"

    def normalize(self, seat: int, action: str) -> str | None:
        if self._over or seat != self.current:
            return None
        a = self.clean(action)
        if a.startswith("guess "):
            a = a[6:].strip()
        if not a.isdecimal():
            return None
        n = int(a)
        if not (self.lo <= n <= self.hi):
            return None
        return f"guess {n}"

    def apply(self, actions: dict[int, str]) -> None:
        if self._over:
            return
        seat = self.current
        act = self.normalize(seat, actions.get(seat, "")) if seat in actions else None
        if act is None:
            raise ValueError(f"illegal action for seat {seat}: {actions.get(seat)!r}")
        n = int(act.split()[1])
        target = self.secrets[1 - seat]
        fb = "correct" if n == target else "higher" if target > n else "lower"
        self.guesses[seat].append((n, fb))
        if fb == "correct" and self.found[seat] is None:
            self.found[seat] = self.round
        if seat == 0:
            self.current = 1
            return
        f0, f1 = self.found[0] is not None, self.found[1] is not None
        if f0 and f1:
            self._finish(None, f"both players found the number in round {self.round}")
        elif f0 or f1:
            w = 0 if f0 else 1
            self._finish(w, f"seat {w} found the opponent's number in round {self.round}")
        elif self.round >= self.max_guesses:
            s0 = self.interval(0)[1] - self.interval(0)[0] + 1
            s1 = self.interval(1)[1] - self.interval(1)[0] + 1
            if s0 == s1:
                self._finish(None, f"guess cap reached, both narrowed it to {s0} possible values")
            else:
                w = 0 if s0 < s1 else 1
                self._finish(w, f"guess cap reached; seat {w} narrowed it to fewer values ({min(s0, s1)} vs {max(s0, s1)})")
        else:
            self.round += 1
            self.current = 0

    def _finish(self, winner: int | None, reason: str) -> None:
        self._over = True
        scores = [0.5, 0.5] if winner is None else [1 if winner == 0 else 0, 1 if winner == 1 else 0]
        self._result = {"winner": winner, "scores": scores, "reason": reason}

    def is_over(self) -> bool:
        return self._over

    def result(self) -> dict:
        if self._result is None:
            return {"winner": None, "scores": [0, 0], "reason": "game in progress"}
        return dict(self._result)

    def frame(self) -> dict:
        return {
            "lo": self.lo,
            "hi": self.hi,
            "max_guesses": self.max_guesses,
            "secrets": list(self.secrets),
            # guesses[seat] = guesses made BY seat at the opponent's secret
            "guesses": [[{"n": n, "feedback": fb} for n, fb in self.guesses[s]] for s in (0, 1)],
            "intervals": [list(self.interval(0)), list(self.interval(1))],
            "found": list(self.found),
            "round": self.round,
            "to_move": self.to_move(),
            "over": self._over,
            "result": self._result,
        }
