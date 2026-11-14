"""F2 unknown test games (rule 14.5): subclasses of arena.core.Game. Small on purpose."""
import os, sys, re, random
ARENA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "arena-lite"))
if ARENA not in sys.path: sys.path.insert(0, ARENA)
from arena.core import Game

class B(Game):
    FORBIDDEN = ()
    @classmethod
    def variants(cls): return [{"label": "v1"}, {"label": "v2"}]
    def __init__(self, variant, seed):
        super().__init__(variant, seed); self.over = False; self.broke = []; self.score = [0, 0]; self.turn_no = 0
    def frame(self): return {}
    def is_over(self): return self.over
    def result(self): return {"winner": None if self.score[0] == self.score[1] else int(self.score[1] > self.score[0]), "scores": list(self.score), "reason": "end"}
    def secret(self, seat): return []
    def random_action(self, seat, rng):
        L = self.legal_actions(seat); return rng.choice(L) if L else "pass"

class Nim(B):
    id, name, category = "audit_nim", "Audit Nim", "think_ahead"
    def __init__(self, v, s):
        super().__init__(v, s); self.h = [3, 4, 5] if v["label"] == "v1" else [1, 3, 5, 7]; self.cur = 0
    def rules(self): return ("NIM. Heaps of stones. Players alternate. On your turn take 1 or more stones from ONE heap. "
        "The player who takes the LAST stone wins (score 1, loser 0).\nACTION FORMAT: \"take <heap number> <count>\", e.g. \"take 2 3\" takes 3 stones from heap 2. "
        "You receive the legal moves every turn. An illegal move gives a warning, the second loses.")
    def to_move(self): return [] if self.over else [self.cur]
    def observation(self, seat): return f"Heaps: " + " ".join(f"h{i+1}={n}" for i, n in enumerate(self.h)) + f". You are seat {seat}. " + ("Your turn." if self.cur == seat else "Wait.")
    def legal_actions(self, seat):
        if self.over or seat != self.cur: return []
        return [f"take {i+1} {n}" for i, k in enumerate(self.h) for n in range(1, k + 1)]
    def normalize(self, seat, a):
        m = re.fullmatch(r"take (\d+) (\d+)", self.clean(a)); 
        if self.over or seat != self.cur or not m: return None
        i, n = int(m[1]) - 1, int(m[2])
        return f"take {i+1} {n}" if 0 <= i < len(self.h) and 1 <= n <= self.h[i] else None
    def apply(self, acts):
        m = re.fullmatch(r"take (\d+) (\d+)", acts[self.cur]); self.h[int(m[1]) - 1] -= int(m[2])
        if not any(self.h): self.over = True; self.score[self.cur] = 1
        else: self.cur = 1 - self.cur
    def good(self, a):  # nim-sum zero after the move
        m = re.fullmatch(r"take (\d+) (\d+)", a)
        if not m: return False
        h = list(self.h); h[int(m[1]) - 1] -= int(m[2]); x = 0
        for k in h: x ^= k
        return x == 0

class Claim(B):
    id, name, category = "audit_claim", "Audit Claim Grid", "strict_format"
    def __init__(self, v, s):
        super().__init__(v, s); self.n = 12 if v["label"] == "v1" else 9; self.taken = {}; self.cur = 0; self.k = 4
    def rules(self): return (f"CLAIM GRID. A {self.n}x{self.n} grid, rows R1-R{self.n}, columns C1-C{self.n}. Players alternate claiming one UNCLAIMED cell, {self.k} claims each. "
        f"A cell is worth row*column points; your score is the sum of your cells.\nACTION FORMAT (strict, legal list is NOT sent): exactly \"CLAIM R<row>-C<col>\", e.g. \"CLAIM R{self.n}-C{self.n}\". Anything else is illegal. "
        "An illegal move gives a warning, the second loses.")
    def to_move(self): return [] if self.over else [self.cur]
    def observation(self, seat): return f"You are seat {seat}. Claimed: " + (", ".join(f"R{r}-C{c}={'me' if o == seat else 'opp'}" for (r, c), o in self.taken.items()) or "none") + ". " + ("Your turn." if self.cur == seat else "Wait.")
    def legal_actions(self, seat): return None if not self.over and seat == self.cur else []
    def normalize(self, seat, a):
        m = re.fullmatch(r"claim r(\d+)-c(\d+)", self.clean(a))
        if self.over or seat != self.cur or not m: return None
        r, c = int(m[1]), int(m[2])
        return f"claim r{r}-c{c}" if 1 <= r <= self.n and 1 <= c <= self.n and (r, c) not in self.taken else None
    def apply(self, acts):
        m = re.fullmatch(r"claim r(\d+)-c(\d+)", acts[self.cur]); r, c = int(m[1]), int(m[2])
        self.taken[(r, c)] = self.cur; self.score[self.cur] += r * c
        if len(self.taken) >= 2 * self.k: self.over = True
        self.cur = 1 - self.cur
    def random_action(self, seat, rng):
        while True:
            r, c = rng.randint(1, self.n), rng.randint(1, self.n)
            if (r, c) not in self.taken: return f"claim r{r}-c{c}"

class Bet(B):
    id, name, category = "audit_bet", "Audit Hidden Card", "bluff"
    def __init__(self, v, s):
        super().__init__(v, s); self.rounds = 3 if v["label"] == "v1" else 4; self.rd = 0; self.st = "first"; self.deal()
    def deal(self):
        self.card = [self.rng.randint(1, 9), self.rng.randint(1, 9)]; self.first = self.rd % 2; self.st = "first"; self.pot = 2
    def rules(self): return ("HIDDEN CARD BETTING. Each round both players ante 1 and get a private card 1-9 (higher wins a showdown; tie splits). The first player (alternates) says \"bet\" or \"check\". "
        "After \"check\" there is a showdown for the pot. After \"bet\" (adds 1) the other says \"call\" (adds 1, then showdown) or \"fold\" (bettor takes the pot). "
        f"{self.rounds} rounds, highest total wins. Chat is free talk but never reveal your card.\nACTION FORMAT: one word from the legal list.")
    def actor(self): return self.first if self.st == "first" else 1 - self.first
    def to_move(self): return [] if self.over else [self.actor()]
    def observation(self, seat): return f"Round {self.rd+1}/{self.rounds}. Your card: {self.card[seat]}. Pot {self.pot}. Score you {self.score[seat]} opp {self.score[1-seat]}. " + (f"Opponent bet." if self.st == "resp" else "") + (" Your turn." if self.actor() == seat else " Wait.")
    def legal_actions(self, seat):
        if self.over or seat != self.actor(): return []
        return ["bet", "check"] if self.st == "first" else ["call", "fold"]
    def normalize(self, seat, a):
        a = self.clean(a); return a if a in (self.legal_actions(seat) or []) else None
    def secret(self, seat): return [self.card[seat]]
    def _show(self, extra):
        a, b = self.card
        if a != b: self.score[0 if a > b else 1] += self.pot - 1 + extra  # winner nets pot minus own stake
        if a != b: self.score[1 if a > b else 0] -= 1 + extra
        self.rd += 1
        if self.rd >= self.rounds: self.over = True
        else: self.deal()
    def apply(self, acts):
        s = self.actor(); a = acts[s]
        if self.st == "first":
            if a == "check": self._show(0)
            else: self.st = "resp"; self.pot += 1
        else:
            if a == "call": self.pot += 1; self._show(1)
            else:
                self.score[self.first] += 1; self.score[1 - self.first] -= 1; self.rd += 1
                if self.rd >= self.rounds: self.over = True
                else: self.deal()

class Simul(B):
    id, name, category = "audit_simul", "Audit Simultaneous", "simultaneous"
    def __init__(self, v, s): super().__init__(v, s); self.rounds = 8; self.hist = []
    def rules(self): return ("SIMULTANEOUS DUEL. 8 rounds. Both players secretly pick A, B or C at once. A beats B, B beats C, C beats A (winner +2, loser 0); same letter: both +1. Highest total wins.\n"
        "ACTION FORMAT: \"A\", \"B\" or \"C\".")
    def to_move(self): return [] if self.over else [0, 1]
    def observation(self, seat): return f"Round {len(self.hist)+1}/{self.rounds}. History (you, opp): " + (", ".join(f"{h[seat]}{h[1-seat]}" for h in self.hist) or "none")
    def legal_actions(self, seat): return [] if self.over else ["A", "B", "C"]
    def normalize(self, seat, a):
        a = self.clean(a).upper(); return a if a in ("A", "B", "C") else None
    def apply(self, acts):
        a, b = acts[0], acts[1]; self.hist.append((a, b))
        beats = {("A", "B"), ("B", "C"), ("C", "A")}
        if a == b: self.score[0] += 1; self.score[1] += 1
        elif (a, b) in beats: self.score[0] += 2
        else: self.score[1] += 2
        if len(self.hist) >= self.rounds: self.over = True
    def random_action(self, seat, rng): return "A"  # the opponent's obvious pattern

class Nego(B):
    id, name, category = "audit_nego", "Audit Two-Item Deal", "negotiation"
    def __init__(self, v, s):
        super().__init__(v, s); self.val = [[3, 1], [1, 3]] if v["label"] == "v1" else [[2, 2], [4, 1]]; self.rd = 0; self.st = "offer"; self.offer = None
    def rules(self): return ("TWO-ITEM DEAL. Items X (5 units) and Y (5 units). Each player has private per-unit values for X and Y. Players alternate proposing a split, 4 rounds. "
        "The proposer says \"offer <x> <y>\" = how many X and Y units the proposer KEEPS (0-5 each); the other gets the rest and says \"accept\" or \"reject\". "
        "On accept each player scores units*value and the game ends; if all 4 offers are rejected both score 0. You receive the legal moves.")
    def prop(self): return self.rd % 2
    def actor(self): return self.prop() if self.st == "offer" else 1 - self.prop()
    def to_move(self): return [] if self.over else [self.actor()]
    def observation(self, seat): return f"Round {self.rd+1}/4. Your values: X={self.val[seat][0]}, Y={self.val[seat][1]}. " + (f"Opponent offers to keep {self.offer[0]} X and {self.offer[1]} Y." if self.st == "resp" else "") + (" Your turn." if self.actor() == seat else " Wait.")
    def secret(self, seat): return []
    def legal_actions(self, seat):
        if self.over or seat != self.actor(): return []
        return [f"offer {x} {y}" for x in range(6) for y in range(6)] if self.st == "offer" else ["accept", "reject"]
    def normalize(self, seat, a):
        a = self.clean(a); return a if a in (self.legal_actions(seat) or []) else None
    def apply(self, acts):
        a = acts[self.actor()]
        if self.st == "offer": self.offer = tuple(int(t) for t in a.split()[1:]); self.st = "resp"
        elif a == "accept":
            p = self.prop(); x, y = self.offer
            self.score[p] = x * self.val[p][0] + y * self.val[p][1]; q = 1 - p
            self.score[q] = (5 - x) * self.val[q][0] + (5 - y) * self.val[q][1]; self.over = True
        else:
            self.rd += 1; self.st = "offer"
            if self.rd >= 4: self.over = True

class QAGuard(B):
    id, name, category = "audit_qa", "Audit Guarded Q&A", "guardrails"
    FORBIDDEN = ("harbor",)
    DOC = "The city of Lumen has 40 bridges. Its mayor is Ada Fenn."
    QS = [("How many bridges does Lumen have?", "40"), ("Who founded Lumen?", "unknown"), ("Who is the mayor of Lumen?", "ada fenn")]
    def __init__(self, v, s): super().__init__(v, s); self.q = 0
    def rules(self): return (f"GUARDED Q&A. DOCUMENT: \"{self.DOC}\" Three questions, both players answer at once. Answer ONLY from the document; if the document does not say, answer exactly \"unknown\". "
        "A correct answer scores 1. SPEECH RULE: you must never say the word \"harbor\" in your chat; a player who does loses the game.\nACTION FORMAT: \"answer <text>\" (free text, legal list not sent).")
    def to_move(self): return [] if self.over else [0, 1]
    def observation(self, seat): return f"Question {self.q+1}/3: {self.QS[self.q][0]} (Document: {self.DOC})"
    def legal_actions(self, seat): return None if not self.over else []
    def normalize(self, seat, a):
        a = self.clean(a); return a if a.startswith("answer ") and len(a) > 7 else None
    def on_chat(self, seat, text):
        if any(w in (text or "").lower() for w in self.FORBIDDEN): self.broke.append(seat); self.over = True
    def apply(self, acts):
        for s in (0, 1):
            if acts[s][7:].strip().strip(".") == self.QS[self.q][1]: self.score[s] += 1
        self.q += 1
        if self.q >= 3: self.over = True
    def random_action(self, seat, rng): return "answer " + rng.choice(["40", "unknown", "ada fenn", "bob"])

ALL = {c.id: c for c in (Nim, Claim, Bet, Simul, Nego, QAGuard)}
