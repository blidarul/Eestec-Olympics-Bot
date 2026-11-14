"""Colonel Blotto simulator (three variants of the T1 games) and scripted opponents, to measure strategies/read_opponent/blotto.

Variants: "equal" (100 soldiers, 5 equal fields), "values" (60 soldiers, 6 fields worth 1-6, shuffled every round),
"reserve" (3 fields, +30 per round, send at most the reserve, the rest is kept). Five rounds; a round goes to the side that
wins more fields (equal), more points (values), more fields (reserve); the game to the side with more rounds.
"""
import random

import _path  # noqa: F401
from strategies.read_opponent import blotto as B

CONFIG = {
    "equal": {"n": 5, "total": 100, "rules": "COLONEL BLOTTO. 5 rounds. Each round both players secretly split 100 soldiers over 5 equal fields. "
                                              "The player with more soldiers in a field wins it. Action format: allocate 20 20 20 20 20 (5 whole numbers, sum exactly 100)."},
    "values": {"n": 6, "total": 60, "rules": "COLONEL BLOTTO. 5 rounds. Each round you split 60 soldiers over 6 fields worth 1-6 points, shuffled every round. "
                                              "The side with more points wins the round. Action format: allocate 10 10 10 10 10 10 (sum exactly 60)."},
    "reserve": {"n": 3, "total": 30, "rules": "COLONEL BLOTTO. 5 rounds. 3 fields. Reserves: +30 per round; send at most your reserve, unspent soldiers are kept. "
                                              "Action format: allocate 10 10 10 (sum at most your reserve)."},
}


def split_even(n, total):
    base = [total // n] * n
    for i in range(total - sum(base)):
        base[i] += 1
    return base


class Game:
    def __init__(self, variant, rng):
        self.v, self.rng = variant, rng
        self.n, self.total = CONFIG[variant]["n"], CONFIG[variant]["total"]
        self.round = 1
        self.ours, self.theirs, self.values_hist = [], [], []
        self.reserve = [30, 30] if variant == "reserve" else None
        self.values = self.new_values()
        self.wins = [0, 0]

    def new_values(self):
        if self.v != "values":
            return [1] * self.n
        vals = list(range(1, 7))
        self.rng.shuffle(vals)
        return vals

    def budget(self, side):
        return self.reserve[side] if self.reserve else self.total

    def observation(self, side=0):
        """The text one side sees (side 1 sees our history swapped)."""
        mine, theirs = (self.ours, self.theirs) if side == 0 else (self.theirs, self.ours)
        lines = [f"COLONEL BLOTTO. Round {self.round} of 5."]
        if self.v == "values":
            lines.append("Battlefield values this round: " + ", ".join(f"F{i + 1}={v}" for i, v in enumerate(self.values)))
        if self.reserve:
            res = self.reserve if side == 0 else self.reserve[::-1]
            lines.append(f"Reserves: you {res[0]}, opponent {res[1]}.")
        for i, (a, b) in enumerate(zip(mine, theirs), 1):
            lines.append(f"Round {i}: you {' '.join(map(str, a))} | opponent {' '.join(map(str, b))}")
        return chr(10).join(lines)

    def play(self, mine, theirs):
        for alloc, side in ((mine, 0), (theirs, 1)):
            cap = self.budget(side)
            assert len(alloc) == self.n and all(isinstance(x, int) and x >= 0 for x in alloc), alloc
            assert (sum(alloc) <= cap) if self.reserve else (sum(alloc) == cap), (self.v, alloc, cap)
        a = sum(v for x, y, v in zip(mine, theirs, self.values) if x > y)
        b = sum(v for x, y, v in zip(mine, theirs, self.values) if y > x)
        self.wins[0] += a > b
        self.wins[1] += b > a
        self.ours.append(mine)
        self.theirs.append(theirs)
        if self.reserve:
            self.reserve = [self.reserve[0] - sum(mine) + 30, self.reserve[1] - sum(theirs) + 30]
        self.round += 1
        self.values = self.new_values()


def parse_action(text, n):
    nums = [int(x) for x in text.split() if x.isdigit()]
    assert len(nums) == n, text
    return nums


def adversary(kind, variant, rng):
    """f(game, side_history) -> allocation for the opponent (side 1)."""
    cfg = CONFIG[variant]
    n, total = cfg["n"], cfg["total"]
    fixed = {"equal": [34, 34, 32, 0, 0], "values": [20, 20, 20, 0, 0, 0], "reserve": [15, 15, 0]}[variant]
    cycle = {"equal": [[34, 33, 33, 0, 0], [0, 34, 33, 33, 0], [0, 0, 34, 33, 33]],
             "values": [[20, 20, 20, 0, 0, 0], [0, 0, 0, 20, 20, 20], [10] * 6],
             "reserve": [[15, 15, 0], [0, 15, 15], [15, 0, 15]]}[variant]

    def play(g):
        cap = g.budget(1)
        if kind == "constant":
            return split_even(n, cap) if variant != "reserve" else [min(10, cap // 3)] * 3
        if kind == "fixed":
            return [min(x, cap) for x in fixed] if variant == "reserve" else fixed
        if kind == "copy":      # plays our previous allocation (scaled to the budget)
            if not g.ours:
                return split_even(n, cap)
            prev = g.ours[-1]
            return B._clip(prev, cap) if variant != "reserve" else [min(x, cap) for x in prev][:n]
        if kind == "cycle":
            a = cycle[(g.round - 1) % len(cycle)]
            return a if variant != "reserve" else [min(x, cap // 2) for x in a]
        if kind == "dirichlet":
            w = [rng.expovariate(1.0) for _ in range(n)]
            use = cap if variant != "reserve" else int(cap * rng.uniform(0.3, 1.0))
            alloc = [int(use * x / sum(w)) for x in w]
            alloc[0] += use - sum(alloc)
            return alloc
        if kind == "self":      # the same strategy as ours, seeing the mirrored history
            text, _how = B.decide(CONFIG[variant]["rules"], g.observation(1), rng)
            return parse_action(text, n)
        if kind == "third":     # 34/33/33 on three fields, the same fields every round
            base = [34, 33, 33] + [0] * (n - 3) if variant == "equal" else ([20, 20, 20] + [0] * (n - 3) if variant == "values" else [15, 15, 0])
            return base if variant != "reserve" else [min(x, cap) for x in base]
        raise ValueError(kind)
    return play


def play_game(variant, opp_kind, seed, strategy_decide=None, our_chat=None):
    """One game of 5 rounds; returns (our rounds, their rounds). Our answers are validated by the simulator."""
    rng = random.Random(seed)
    g = Game(variant, rng)
    opp = adversary(opp_kind, variant, random.Random(seed + 1))
    decide = strategy_decide or (lambda rules, obs, r: B.decide(rules, obs, r))
    for _ in range(5):
        text, _how = decide(CONFIG[variant]["rules"], g.observation(), random.Random(rng.random()))
        g.play(parse_action(text, g.n), opp(g))
    return g.wins[0], g.wins[1]


def win_rate(variant, opp_kind, games=200, seed=0):
    """(win share, draw share, loss share) over `games` best-of-5-round games."""
    w = d = l = 0
    for k in range(games):
        a, b = play_game(variant, opp_kind, seed * 100000 + k)
        w, d, l = w + (a > b), d + (a == b), l + (a < b)
    return w / games, d / games, l / games
