"""Games written INSIDE the tests only (no game-specific code in the bot, rule 10.7).

Simulator sources follow the contract of solvers/adapter.py (State + module-level parse).
"""

TTT_SIM = '''
LINES = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
NAMES = [chr(65 + c) + str(r + 1) for r in range(3) for c in range(3)]

class State:
    def __init__(self, board=None, current=0):
        self.board = list(board) if board else [None] * 9
        self.current = current

    def winner(self):
        for a, b, c in LINES:
            if self.board[a] is not None and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        return None

    def legal_actions(self):
        if self.winner() is not None:
            return []
        return [NAMES[i] for i in range(9) if self.board[i] is None]

    def step(self, action):
        i = NAMES.index(action)
        b = list(self.board)
        b[i] = self.current
        return State(b, 1 - self.current)

    def is_terminal(self):
        return self.winner() is not None or all(c is not None for c in self.board)

    def evaluate(self, seat):
        w = self.winner()
        return 0.0 if w is None else (1.0 if w == seat else -1.0)


def parse(obs, seat):
    rows = [l for l in obs.split("\\n") if l[:2].strip().isdigit()]
    cells = []
    for l in rows:
        cells += l.split()[1:]
    if len(cells) != 9:
        raise ValueError("no 3x3 board")
    board = [None if c == "." else (0 if c == "X" else 1) for c in cells]
    cur = 0 if board.count(0) == board.count(1) else 1
    return State(board, cur)
'''

# a pig-like dice game with real chance: roll (1 = lose turn total, else add), hold (bank), first to 20
PIG_SIM = '''
import random

class State:
    def __init__(self, banked=(0, 0), total=0, current=0):
        self.banked = tuple(banked)
        self.total = total
        self.current = current

    def legal_actions(self):
        return [] if self.is_terminal() else (["roll", "hold"] if self.total else ["roll"])

    def step(self, action):
        b = list(self.banked)
        if action == "roll":
            d = random.randint(1, 6)
            if d == 1:
                return State(b, 0, 1 - self.current)
            return State(b, self.total + d, self.current)
        b[self.current] += self.total
        return State(b, 0, 1 - self.current)

    def is_terminal(self):
        return max(self.banked) >= 20

    def evaluate(self, seat):
        if self.banked[seat] >= 20:
            return 1.0
        if self.banked[1 - seat] >= 20:
            return -1.0
        return (self.banked[seat] - self.banked[1 - seat]) / 40.0


def parse(obs, seat):
    import re
    m = re.search(r"you (\\d+), opponent (\\d+)", obs)
    t = re.search(r"Turn total: (\\d+)", obs)
    if not m or not t:
        raise ValueError("bad observation")
    mine, theirs = int(m.group(1)), int(m.group(2))
    b = (mine, theirs) if seat == 0 else (theirs, mine)
    return State(b, int(t.group(1)), seat)
'''

TTT_OBS_TMPL = """TIC-TAC-TOE - 3x3 classic. You are seat 0 and play X; the opponent plays O.
Your turn (move {n}). Need 3 in a row.
   A B C
{rows}
"""


def ttt_obs(cells):
    """cells: 9 chars of 'X', 'O', '.'. Seat 0 to move when counts are equal."""
    rows = "\n".join(f" {r + 1} " + " ".join(cells[3 * r:3 * r + 3]) for r in range(3))
    return TTT_OBS_TMPL.format(n=cells.count("X") + cells.count("O") + 1, rows=rows)


def ttt_sample(cells):
    legal = [chr(65 + i % 3) + str(i // 3 + 1) for i, c in enumerate(cells) if c == "."]
    return {"type": "turn", "turn": 3, "observation": ttt_obs(cells), "legal_actions": legal, "seconds": 20, "chat": []}


PIG_OBS = """PIG - first to 20. You are seat 0.
Banked: you {a}, opponent {b}.
Turn 5: it is YOUR turn. Turn total: {t} (rolls this turn: 2).
Choose: roll | hold
"""


def pig_sample(a=5, b=7, t=4):
    return {"type": "turn", "turn": 5, "observation": PIG_OBS.format(a=a, b=b, t=t),
            "legal_actions": ["roll", "hold"], "seconds": 20, "chat": []}


# --- number guessing (guess the opponent's secret, higher/lower feedback), observation like arena's guess_number
def guess_rules(lo=1, hi=100, cap=12):
    return (f"GUESS THE NUMBER - range {lo}-{hi}, at most {cap} guesses each.\n"
            f"Each player has a secret whole number between {lo} and {hi}. Action: guess <n>.\n"
            "Feedback after each guess: higher / lower / correct about the opponent's number.\n")


def guess_obs(history, lo=1, hi=100, cap=12):
    lines = [f"GUESS THE NUMBER ({lo}-{hi}). You are Player 0.", "Your secret number: 17",
             f"Round {len(history) + 1} of {cap}.", "", "Your guesses at the opponent's number:"]
    if not history:
        lines.append("  (none yet)")
    for i, (n, fb) in enumerate(history, 1):
        lines.append(f"  Round {i}: you guessed {n} -> {fb} (their number is {'above' if fb == 'higher' else 'below'} {n})")
    lines += ["Opponent's guesses at your number:", "  (none yet)", "", f'It is YOUR turn: "guess <n>" with n from {lo} to {hi}.']
    return "\n".join(lines)


# the code a good prepare() answer contains for the guessing family (what Haiku is asked to write)
GUESS_MODEL_CODE = '''
import re

def candidate_space(variant):
    rules = variant.get("rules", "")
    m = re.search(r"range (\\d+)-(\\d+)", rules)
    lo, hi = int(m.group(1)), int(m.group(2))
    return range(lo, hi + 1)

def extract_history(observation):
    out = []
    for m in re.finditer(r"you guessed (\\d+) -> (higher|lower|correct)", observation):
        out.append((int(m.group(1)), m.group(2)))
    return out

def feedback(secret, guess):
    return "correct" if guess == secret else ("higher" if secret > guess else "lower")

def format_guess(guess):
    return "guess %d" % guess
'''
