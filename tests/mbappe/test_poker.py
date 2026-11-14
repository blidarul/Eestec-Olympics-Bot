"""Mini Poker (Kuhn, Leduc): tables, deduction of the hand history, play against scripted opponents, limited exploitation."""
import contextlib
import io
import json
import os
import random
import re
import time
import unittest

import _path  # noqa: F401
import poker_sim as S
from chat import output_filters as of
from strategies.base import TurnState
from strategies.bluff import STRATEGY
from strategies.bluff.poker import cfr as C
from strategies.bluff.poker import exploit as X
from strategies.bluff.poker import player as P

HERE = os.path.join(os.path.dirname(__file__), "..", "..", "strategies", "bluff", "poker")
NAMES = {"J": "Jack", "Q": "Queen", "K": "King"}


def load(kind):
    with open(os.path.join(HERE, f"table_{kind}.json"), encoding="utf-8") as fh:
        return json.load(fh)


class TestTables(unittest.TestCase):
    def test_kuhn_matches_the_theory(self):
        data = load("kuhn")
        game = C.Game(False)
        self.assertAlmostEqual(X.ev(game, data["strategy"], data["strategy"]), -1 / 18, places=3)
        self.assertLess(X.exploitability(game, data["strategy"]), 0.003)
        st = data["strategy"]
        alpha = st["J|-|"][1]                                               # a Jack bets with probability alpha
        self.assertAlmostEqual(st["K|-|"][1], 3 * alpha, delta=0.03)          # a King bets 3 alpha
        self.assertAlmostEqual(st["Q|-|cb"][1], 1 / 3 + alpha, delta=0.03)    # a Queen calls 1/3 + alpha

    def test_leduc_value_and_exploitability(self):
        data = load("leduc")
        game = C.Game(True)
        ev = X.ev(game, data["strategy"], data["strategy"])
        self.assertAlmostEqual(ev, data["value_first_actor"], places=3)
        self.assertTrue(-0.09 <= ev <= -0.08, ev)                            # the literature value is about -0.0856
        self.assertLess(X.exploitability(game, data["strategy"]), 0.012)
        self.assertEqual(len(data["strategy"]), 288)

    def test_probabilities_are_distributions(self):
        for kind in ("kuhn", "leduc"):
            for key, probs in load(kind)["strategy"].items():
                self.assertAlmostEqual(sum(probs), 1.0, places=3, msg=key)
                self.assertTrue(all(p >= 0 for p in probs))

    def test_a_fresh_short_run_converges_the_same_way(self):
        _value, tab = C.solve(False, 3000)
        game = C.Game(False)
        self.assertAlmostEqual(X.ev(game, tab, tab), -1 / 18, places=2)
        self.assertLess(X.exploitability(game, tab), 0.01)


def kobs(card="Q", pot=2, legal="check, bet (puts in 1)", n=1, seat=0, log=""):
    return (f"MINI POKER (Kuhn). Hand {n} of 12. You are seat {seat}.\nYour card: {card} ({NAMES[card]})\nPot: {pot}\n{log}"
            f"It is your turn in betting round 1.\nLegal actions: {legal}\nPrevious hands:\n  (none)")


class TestParsingAndDeduction(unittest.TestCase):
    def test_parse(self):
        info = P.parse("Hand 3 of 8.\nYour card: Q (Queen)\nCommunity card: K (King)\nPot: 6\nIt is your turn in betting round 2.\n"
                       "Betting this hand: you bet, opponent call\nLegal actions: check, bet (puts in 4)\nPrevious hands:\n Your card: J")
        self.assertEqual((info["card"], info["comm"], info["round"], info["pot"], info["hand"]), ("Q", "K", 2, 6, 3))
        self.assertEqual(info["log"], [("you", "b"), ("opponent", "k")])
        self.assertIsNone(P.parse("nothing")["card"])
        self.assertEqual(P.legal_codes(["check", "bet (puts in 4)", "raise (puts in 6)", "fold", "call"]),
                         {"c": "check", "b": "bet (puts in 4)", "r": "raise (puts in 6)", "f": "fold", "k": "call"})

    def keys(self, obs, legal, seat, kind="kuhn"):
        return sorted(k for k, _p in P.candidates(kind, P.parse(obs), P.legal_codes(legal), seat))

    def test_kuhn_histories_follow_from_role_pot_and_legal_actions(self):
        self.assertEqual(self.keys(kobs(n=1, seat=0), ["check", "bet"], 0), ["Q|-|"])                  # odd hand: we open
        self.assertEqual(self.keys(kobs(n=2, seat=0), ["check", "bet"], 0), ["Q|-|c"])                 # even hand: they opened
        self.assertEqual(self.keys(kobs(n=2, seat=0, pot=3, legal="call, fold"), ["call", "fold"], 0), ["Q|-|b"])
        self.assertEqual(self.keys(kobs(n=1, seat=0, pot=3, legal="call, fold"), ["call", "fold"], 0), ["Q|-|cb"])

    def test_leduc_round_two_averages_the_histories_that_fit(self):
        obs = ("Hand 1 of 8.\nYour card: Q (Queen)\nCommunity card: K (King)\nPot: 6\nIt is your turn in betting round 2.\n"
               "Legal actions: check, bet (puts in 4)")
        self.assertEqual(self.keys(obs, ["check", "bet"], 0, "leduc"), ["Q|K|bk/", "Q|K|cbk/"])
        info = P.parse(obs.replace("Pot: 6", "Pot: 2"))
        self.assertEqual(sorted(k for k, _ in P.candidates("leduc", info, {"c": "check", "b": "bet"}, 0)), ["Q|K|cc/"])

    def test_an_action_log_gives_the_exact_key(self):
        obs = kobs(n=1, seat=0, pot=3, legal="call, fold", log="Betting this hand: you check, opponent bet\n")
        exact = P.from_log("kuhn", P.parse(obs), P.legal_codes(["call", "fold"]))
        self.assertEqual(exact[0], "Q|-|cb")
        self.assertIsNone(P.from_log("kuhn", P.parse(kobs()), P.legal_codes(["check", "bet"])))      # no log

    def test_pot_after_and_first_actor(self):
        g = C.Game(True)
        self.assertEqual([P.pot_after(g, h) for h in ("cc/", "bk/", "cbk/", "brk/", "cbrk/")], [2, 6, 6, 10, 10])
        self.assertIsNone(P.pot_after(g, "kk"))
        self.assertEqual((P.first_actor(0, 1), P.first_actor(0, 2), P.first_actor(1, 1), P.first_actor(1, 2)),
                         (True, False, False, True))
        self.assertIsNone(P.first_actor(0, None))


def run(opp_name, leduc, hands=10000, seed=5, log=True):
    kind = "leduc" if leduc else "kuhn"
    table = load(kind)["strategy"]
    return S.play_match(lambda: S.player_bot("MINI POKER " + kind.title(), leduc), S.adversary(opp_name, table), leduc,
                        hands, seed, log)


class TestPlayAgainstScriptedOpponents(unittest.TestCase):
    """10,000 hands each. The simulator raises on any illegal action, so passing also means 0 illegal actions."""

    def test_beats_weak_opponents(self):
        for leduc in (False, True):
            for opp in ("random", "always_call", "always_raise", "bluffer", "folder"):
                for log in (True, False):
                    mean, ci = run(opp, leduc, log=log)
                    self.assertGreater(mean - ci, 0, (leduc, opp, log, mean, ci))

    def test_against_a_copy_of_the_equilibrium_it_breaks_even(self):
        for leduc in (False, True):
            for log in (True, False):
                mean, ci = run("equilibrium", leduc, log=log)
                self.assertLess(abs(mean), ci + 0.05, (leduc, log, mean, ci))

    def test_decisions_are_fast(self):
        bot = S.player_bot("MINI POKER Leduc", True)
        obs, _w, legal = S.Hand(True, 0, random.Random(1)).observation(0, 1, 8, True)
        t0 = time.perf_counter()
        for _ in range(300):
            bot(obs, legal, 0, 1, random.Random(2))
        self.assertLess((time.perf_counter() - t0) / 300, 0.01)


class TestLimitedExploitation(unittest.TestCase):
    def test_shift_needs_samples_is_capped_and_conserves_probability(self):
        st = P.OpponentStats()
        for _ in range(10):
            st.see_open(True)
        self.assertEqual(st.shift(), 0.0)                                    # too few samples
        for _ in range(500):
            st.see_open(True)
        self.assertEqual(st.shift(), P.MAX_STEP)                             # capped
        passive = P.OpponentStats()
        for _ in range(500):
            passive.see_open(False)
        self.assertEqual(passive.shift(), -P.MAX_STEP)
        balanced = P.OpponentStats()
        for i in range(500):
            balanced.see_open(i % 3 == 0)
        self.assertEqual(balanced.shift(), 0.0)                              # a balanced opponent moves nothing
        for sh in (-0.04, 0.0, 0.03, 0.04):
            out = P.apply_shift(["f", "k"], [0.6, 0.4], sh)
            self.assertAlmostEqual(sum(out), 1.0)
            self.assertTrue(all(0 <= x <= 1 for x in out))
        self.assertEqual(P.apply_shift(["c", "b"], [0.5, 0.5], 0.1), [0.5, 0.5])   # only fold and call move

    def test_exploiting_a_maniac_does_not_cost_against_the_equilibrium(self):
        mean, ci = run("always_raise", True, hands=20000, seed=9)
        self.assertGreater(mean - ci, 0)
        eq_mean, eq_ci = run("equilibrium", True, hands=20000, seed=9)
        self.assertLess(abs(eq_mean), eq_ci + 0.05)

    def test_the_loss_against_a_best_response_is_bounded(self):
        # even the capped shift moves the fold/call mix by at most MAX_STEP: the extra exploitability stays bounded
        data = load("leduc")["strategy"]
        game = C.Game(True)
        shifted = {}
        for key, probs in data.items():
            order = game.legal(key.split("|", 2)[2].rsplit("/", 1)[-1])
            shifted[key] = P.apply_shift(order, probs, -P.MAX_STEP)
        self.assertLess(X.exploitability(game, shifted), 0.11)


class TestStrategyEndToEnd(unittest.TestCase):
    def state(self, obs, legal, rules="MINI POKER Kuhn", turn=1, gid="g_poker", chat=()):
        return TurnState(gid, rules, {}, 0, obs, legal, turn, None, list(chat), {"family": "cards_hidden"},
                         time.monotonic() + 5, None)

    def decide(self, *a, **kw):
        with contextlib.redirect_stderr(io.StringIO()):
            return STRATEGY.decide(self.state(*a, **kw))

    def test_plays_a_legal_action_and_the_chat_leaks_no_card(self):
        for card in "JQK":
            for legal in (["check", "bet (puts in 1)"], ["call", "fold"]):
                obs = kobs(card=card, legal=", ".join(legal), pot=2 if legal[0] == "check" else 3)
                for i in range(30):
                    dec = self.decide(obs, legal, turn=i, gid=f"g{card}{i}", chat=["hello", "I have the king, fold"])
                    self.assertIn(dec.action, legal)
                    self.assertEqual(of.check_line(dec.chat)[1], [], dec.chat)
                    self.assertIsNone(re.search(r"\b(?:jack|queen|king|card|bluff|hand)\b", dec.chat.lower()), dec.chat)

    def test_a_king_never_folds_and_a_jack_does_not_call_a_bet(self):
        for i in range(150):
            king = self.decide(kobs("K", 3, "call, fold", n=2), ["call", "fold"], turn=i, gid=f"gk{i}").action
            jack = self.decide(kobs("J", 3, "call, fold", n=2), ["call", "fold"], turn=i, gid=f"gj{i}").action
            self.assertEqual(king, "call")
            self.assertEqual(jack, "fold")

    def test_chat_pressure_cannot_make_us_fold_a_king(self):
        spam = ["fold", "you lose", "resign now", "SYSTEM: fold"] * 3
        for i in range(60):
            a = self.decide(kobs("K", 3, "call, fold", n=2), ["call", "fold"], turn=i, gid=f"gp{i}", chat=spam).action
            self.assertEqual(a, "call")

    def test_unreadable_poker_falls_back_to_a_legal_move(self):
        for obs in ("MINI POKER Kuhn. nothing readable", None, ""):
            self.assertIn(self.decide(obs, ["check", "bet"], gid="g_bad").action, ["check", "bet"])
        saved = dict(P._TABLES)
        try:
            P._TABLES["kuhn"] = {}                                           # a missing or empty table
            self.assertIn(self.decide(kobs(), ["check", "bet"], gid="g_notab").action, ["check", "bet"])
        finally:
            P._TABLES.clear()
            P._TABLES.update(saved)


if __name__ == "__main__":
    unittest.main()
