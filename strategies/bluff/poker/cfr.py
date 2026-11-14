"""Counterfactual regret minimisation for Kuhn and Leduc poker with the arena's rules (run at BUILD time, not in the arena).

Rules used (from the T1 games): both players ante 1; the player who acts first in a hand is "player 0" here (the arena
alternates who that is from hand to hand); Kuhn: deck J Q K, one betting round, bet 1, no raise; Leduc: deck J J Q Q K K, a
community card after round 1, round 1 bet 2, round 2 bet 4, at most one bet and one raise per round, a pair with the
community card beats everything. Utilities are chips won by player 0.

Information set key (a plain string, also used by the player at run time):
    "<own card>|<community or ->|<history>"   history = actions of this hand so far, rounds separated by "/",
    actions c(heck) b(et) r(aise) k(call) f(old), e.g. "cb/" is round 1 "check, bet", the call "k" closes the round.
The history includes round 1 when we are in round 2 (perfect recall), so the table is a true equilibrium.
"""
import itertools
import json
import sys

RANK = {"J": 0, "Q": 1, "K": 2}


class Game:
    def __init__(self, leduc):
        self.leduc = leduc
        self.bets = (2, 4) if leduc else (1,)
        self.rounds = 2 if leduc else 1
        self.deck = list("JJQQKK") if leduc else list("JQK")

    def legal(self, rh):
        """Legal actions after the betting sequence `rh` of the current round."""
        if rh in ("", "c"):
            return ["c", "b"]
        if rh in ("b", "cb"):
            return ["f", "k"] + (["r"] if self.leduc else [])
        if rh in ("br", "cbr"):
            return ["f", "k"]
        return []

    def showdown(self, c0, c1, comm):
        if self.leduc:
            p0, p1 = RANK[c0] == RANK[comm], RANK[c1] == RANK[comm]
            if p0 != p1:
                return 1 if p0 else -1
        return (RANK[c0] > RANK[c1]) - (RANK[c0] < RANK[c1])

    def deals(self):
        if self.leduc:
            return [((self.deck[i], self.deck[j]), self.deck[k]) for i, j, k in itertools.permutations(range(6), 3)]
        return [(c, None) for c in itertools.permutations("JQK", 2)]


class Node:
    __slots__ = ("regret", "strat_sum", "n")

    def __init__(self, n):
        self.regret, self.strat_sum, self.n = [0.0] * n, [0.0] * n, n

    def strategy(self, weight):
        pos = [max(r, 0.0) for r in self.regret]
        s = sum(pos)
        st = [p / s for p in pos] if s > 0 else [1.0 / self.n] * self.n
        for i in range(self.n):
            self.strat_sum[i] += weight * st[i]
        return st

    def average(self):
        s = sum(self.strat_sum)
        return [x / s for x in self.strat_sum] if s > 0 else [1.0 / self.n] * self.n


def key_of(card, comm, hist):
    return f"{card}|{comm or '-'}|{hist}"


def cfr(game, nodes, cards, comm, rd, rh, hist, pot0, pot1, player, reach):
    bet = game.bets[rd]
    acts = game.legal(rh)
    key = key_of(cards[player], comm if rd == 1 else None, hist)
    node = nodes.get(key)
    if node is None:
        node = nodes[key] = Node(len(acts))
    strat = node.strategy(reach[player] * ITERATION[0])
    util, nu = [0.0] * len(acts), 0.0
    for i, a in enumerate(acts):
        p0, p1 = pot0, pot1
        mine, opp = (p0, p1) if player == 0 else (p1, p0)
        nr = reach[:]
        nr[player] *= strat[i]
        if a == "f":
            u = -pot0 if player == 0 else pot1
        else:
            add = {"c": 0, "b": bet, "r": (opp - mine) + bet, "k": opp - mine}[a]
            if player == 0:
                p0 += add
            else:
                p1 += add
            nrh = rh + a
            if a == "k" or nrh == "cc":
                if rd + 1 < game.rounds:
                    u = cfr(game, nodes, cards, comm, rd + 1, "", hist + a + "/", p0, p1, 0, nr)
                else:
                    s = game.showdown(cards[0], cards[1], comm)
                    u = p1 if s == 1 else (-p0 if s == -1 else 0)
            else:
                u = cfr(game, nodes, cards, comm, rd, nrh, hist + a, p0, p1, 1 - player, nr)
        util[i] = u
        nu += strat[i] * u
    sign = 1 if player == 0 else -1
    for i in range(len(acts)):
        node.regret[i] += reach[1 - player] * sign * (util[i] - nu)
    return nu


ITERATION = [1]   # CFR+ weights the average strategy by the iteration number


def solve(leduc, iterations):
    """CFR+ (regrets floored at 0, average weighted by the iteration): much faster than plain CFR.
    Returns (value for the first actor, {key: [probabilities in the order of Game.legal]})."""
    game, nodes = Game(leduc), {}
    deals = game.deals()
    value = 0.0
    for t in range(1, iterations + 1):
        ITERATION[0] = t
        total = 0.0
        for cards, comm in deals:
            total += cfr(game, nodes, cards, comm, 0, "", "", 1, 1, 0, [1.0, 1.0])
        value = total / len(deals)
        for node in nodes.values():  # the "plus": negative regrets are forgotten
            node.regret = [max(r, 0.0) for r in node.regret]
    return value, {k: [round(x, 5) for x in n.average()] for k, n in nodes.items()}


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "kuhn"
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    v, table = solve(kind == "leduc", iters)
    print(kind, iters, "iterations, value of the first actor:", round(v, 4), "infosets:", len(table))
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump({"game": kind, "iterations": iters, "value_first_actor": v, "strategy": table}, fh, separators=(",", ":"))
