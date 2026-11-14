"""Wordle Duel: two players simultaneously race to crack the same hidden word."""
from __future__ import annotations

import copy
import random
import re

from ..core import Game

# Common word bank for 4, 5, 6 letter secrets
WORD_BANK = {
    4: ["game", "word", "play", "race", "plan", "team", "star", "glow", "time", "lead", "path", "zone", "tree", "bird", "gold"],
    5: ["click", "crane", "slate", "pilot", "plant", "water", "sound", "light", "heart", "break", "stone", "flame", "drive", "track", "round"],
    6: ["planet", "silver", "stream", "puzzle", "flight", "orange", "yellow", "spring", "bridge", "castle", "winter", "forest", "shadow"],
}


def compute_wordle_feedback(secret: str, guess: str) -> str:
    """Compute standard Wordle G/Y/X feedback."""
    sec = secret.lower()
    gue = guess.lower()
    n = len(sec)
    res = ["X"] * n
    sec_counts: dict[str, int] = {}
    for c in sec:
        sec_counts[c] = sec_counts.get(c, 0) + 1

    # First pass: Green
    for i in range(n):
        if i < len(gue) and gue[i] == sec[i]:
            res[i] = "G"
            sec_counts[gue[i]] -= 1

    # Second pass: Yellow
    for i in range(n):
        if i < len(gue) and res[i] != "G" and sec_counts.get(gue[i], 0) > 0:
            res[i] = "Y"
            sec_counts[gue[i]] -= 1

    return "".join(res)


class WordleDuel(Game):
    id = "wordle_duel"
    name = "Wordle Duel"
    category = "guess"
    blurb = "Two players race to crack the same hidden word, each seeing only the colours of the rival's tries."
    howto = "Both players race to guess the same secret word. After each guess, colours show which letters are right; you only see the colours of your rival's tries. First to find it wins."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "5 letters, 6 guesses", "length": 5, "max_guesses": 6},
            {"label": "6 letters, 7 guesses", "length": 6, "max_guesses": 7},
            {"label": "4-letter blitz, 5 guesses", "length": 4, "max_guesses": 5},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.length = max(3, min(8, int(self.variant.get("length", 5))))
        self.max_guesses = max(3, min(10, int(self.variant.get("max_guesses", 6))))
        self.label = str(self.variant.get("label", f"{self.length} letters, {self.max_guesses} guesses"))
        
        # Pick secret from word bank based on seed
        pool = WORD_BANK.get(self.length, WORD_BANK[5])
        rng = random.Random(seed)
        self.secret_word = rng.choice(pool)
        
        self.round_no = 1
        self.guesses: list[list[dict]] = [[], []]  # per player: list of {"word": str, "marks": str}
        self.solved: list[int | None] = [None, None]  # round when solved
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def secret(self, seat: int) -> list[str]:
        return [self.secret_word]

    def rules(self) -> str:
        return f"""WORDLE DUEL - {self.length}-letter word, at most {self.max_guesses} guesses each.

GOAL
Both players try to find the SAME secret English word of exactly {self.length} letters, chosen at random by
the arena from a list of common words (no proper nouns). The first player to guess it wins.

TURN ORDER
The game is played in rounds. In every round BOTH players submit one guess at the same time
(simultaneously); neither sees the other's guess for that round before choosing.

ACTION FORMAT
    guess <word>
<word> must be exactly {self.length} letters a-z (case does not matter). It does NOT have to be a real word:
any {self.length}-letter alphabetic string is legal. Anything else (wrong length, digits, spaces inside the
word, punctuation) is illegal (first time: a warning and the same turn again; second time: you
lose the game).

FEEDBACK (after every round)
Each letter of your guess gets a colour:
    G = green  : this letter is in the secret word at exactly this position.
    Y = yellow : this letter is in the secret word, but at a different position.
    X = gray   : this letter is not in the secret word (or the word has no more copies of it).

WHAT YOU OBSERVE
Your observation lists every guess you made with its colours, and for your opponent ONLY the colour
pattern of each of their guesses (never their letters).

HOW THE GAME ENDS AND IS SCORED
- After a round, if exactly one player's guess equals the secret word, that player wins (score 1, loser 0).
- If both players find it in the same round, the game is a draw (0.5 each).
- If nobody finds it after round {self.max_guesses} (the guess cap), the game ends: the player whose best single
  guess had more green letters wins; if equal, the one whose best guess had more yellow letters wins; still equal = draw."""

    def to_move(self) -> list[int]:
        if self.over:
            return []
        return [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over:
            return []
        return None  # Null legal actions for open word guessing

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over:
            return None
        a = self.clean(action).strip()
        m = re.match(r"^(?:guess\s+)?([a-zA-Z]+)$", a)
        if not m:
            return None
        word = m.group(1).lower()
        if len(word) == self.length and word.isalpha():
            return f"guess {word}"
        return None

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        w0 = self.normalize(0, actions.get(0, ""))
        w1 = self.normalize(1, actions.get(1, ""))
        if w0 is None:
            raise ValueError(f"illegal action {actions.get(0)!r} for seat 0")
        if w1 is None:
            raise ValueError(f"illegal action {actions.get(1)!r} for seat 1")
        
        g0 = w0.split()[1]
        g1 = w1.split()[1]
        m0 = compute_wordle_feedback(self.secret_word, g0)
        m1 = compute_wordle_feedback(self.secret_word, g1)
        
        self.guesses[0].append({"word": g0, "marks": m0})
        self.guesses[1].append({"word": g1, "marks": m1})

        s0 = (m0 == "G" * self.length)
        s1 = (m1 == "G" * self.length)

        if s0 and self.solved[0] is None:
            self.solved[0] = self.round_no
        if s1 and self.solved[1] is None:
            self.solved[1] = self.round_no

        if s0 or s1:
            self.over = True
            if s0 and s1:
                self.winner = None
                self.end_reason = f"both players guessed {self.secret_word!r} in round {self.round_no}: draw"
            elif s0:
                self.winner = 0
                self.end_reason = f"seat 0 guessed {self.secret_word!r} in round {self.round_no}"
            else:
                self.winner = 1
                self.end_reason = f"seat 1 guessed {self.secret_word!r} in round {self.round_no}"
        elif self.round_no >= self.max_guesses:
            self.over = True
            # Tie-break by best guess (max G, then max Y)
            def score_guess(item: dict) -> tuple[int, int]:
                marks = item.get("marks", "")
                return (marks.count("G"), marks.count("Y"))
            best0 = max((score_guess(x) for x in self.guesses[0]), default=(0, 0))
            best1 = max((score_guess(x) for x in self.guesses[1]), default=(0, 0))
            if best0 > best1:
                self.winner = 0
                self.end_reason = f"guess cap reached: seat 0 had better best guess ({best0[0]}G {best0[1]}Y vs {best1[0]}G {best1[1]}Y)"
            elif best1 > best0:
                self.winner = 1
                self.end_reason = f"guess cap reached: seat 1 had better best guess ({best1[0]}G {best1[1]}Y vs {best0[0]}G {best0[1]}Y)"
            else:
                self.winner = None
                self.end_reason = "guess cap reached: equal best guesses: draw"
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
        lines = [
            f"WORDLE DUEL - {self.label}. Round {self.round_no}/{self.max_guesses}. You are seat {seat}."
        ]
        if self.over:
            lines.append(f"The game is over: {self.end_reason}. Secret was {self.secret_word!r}.")
        else:
            lines.append(f"Your turn. Enter your {self.length}-letter guess.")

        lines.append("Your guesses so far:")
        if self.guesses[seat]:
            for i, item in enumerate(self.guesses[seat]):
                lines.append(f"  {i + 1}. {item['word']} -> {item['marks']}")
        else:
            lines.append("  (none)")

        opp_seat = 1 - seat
        lines.append("Opponent tries:")
        if self.guesses[opp_seat]:
            for i, item in enumerate(self.guesses[opp_seat]):
                lines.append(f"  {i + 1}. [hidden] -> {item['marks']}")
        else:
            lines.append("  (none)")

        return "\n".join(lines)

    def frame(self) -> dict:
        return copy.deepcopy(self._frame())

    def _frame(self) -> dict:
        def best_of(seat: int) -> list[int]:
            best = (0, 0)
            for x in self.guesses[seat]:
                m = x.get("marks", "")
                best = max(best, (m.count("G"), m.count("Y")))
            return list(best)

        return {
            "length": self.length,
            "max_guesses": self.max_guesses,
            "secret": self.secret_word,
            "round": self.round_no,
            "players": [
                {"guesses": self.guesses[0], "solved_round": self.solved[0], "best": best_of(0)},
                {"guesses": self.guesses[1], "solved_round": self.solved[1], "best": best_of(1)},
            ],
            "to_move": [] if self.over else [0, 1],
            "over": self.over,
            "result": self.result() if self.over else None,
        }

    def random_action(self, seat: int, rng: random.Random) -> str:
        pool = WORD_BANK.get(self.length, WORD_BANK[5])
        return f"guess {rng.choice(pool)}"
