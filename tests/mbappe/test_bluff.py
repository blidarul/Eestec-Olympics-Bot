"""strategies/bluff: card betting mix, bluff calibration, Pig threshold, chat that leaks nothing, routing."""
import contextlib
import io
import re
import time
import unittest

import _path  # noqa: F401
from chat import output_filters as of
from strategies.base import TurnState
from strategies.bluff import STRATEGY, cards, pig

KUHN = "KUHN POKER. Three cards: J, Q, K. Each player antes one chip and gets one card. Bet or pass; a bet can be called or folded."


def obs(hand, extra=""):
    return f"Pot: 2 chips.\nYour hand: {hand}\n{extra}\nIt is YOUR turn."


def state(hand="K", legal=("check", "bet"), chat=(), gid="g_bluff", turn=1, rules=KUHN, observation=None):
    return TurnState(gid, rules, {}, 0, observation if observation is not None else obs(hand), list(legal), turn, None,
                     list(chat), {"family": "cards_hidden"}, time.monotonic() + 5, None)


def decide(**kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return STRATEGY.decide(state(**kw))


def rates(hand, legal, n=1200, chat=(), rules=KUHN):
    counts = {}
    for i in range(n):
        a = decide(hand=hand, legal=legal, gid=f"g{i}", turn=i % 7 + 1, chat=chat, rules=rules).action
        counts[cards.categorize(a)] = counts.get(cards.categorize(a), 0) + 1
    return {k: v / n for k, v in counts.items()}


class TestHandReading(unittest.TestCase):
    def test_parse_and_strength(self):
        self.assertEqual(cards.parse_hand("Pot 2\nYour hand: K"), [13])
        self.assertEqual(cards.parse_hand("Your hand: KS, 10H"), [13, 10])
        self.assertEqual(cards.parse_hand("You hold: Q\nOpponent hand: K"), [12])      # the opponent's line is not ours
        self.assertEqual(cards.parse_hand(None), [])
        self.assertEqual([cards.strength([r], KUHN) for r in (11, 12, 13)], [0.0, 0.5, 1.0])
        self.assertEqual(cards.strength([], KUHN), 0.5)
        self.assertGreater(cards.strength([9, 9]), cards.strength([9, 8]))              # a pair counts

    def test_categories(self):
        for a, c in {"fold": "fold", "call": "call", "bet": "bet", "raise 10": "bet", "all-in": "bet", "check": "check",
                     "pass": "check", "xyz": "other"}.items():
            self.assertEqual(cards.categorize(a), c, a)


class TestBettingMix(unittest.TestCase):
    def test_strong_hands_bet_and_call_with_high_probability(self):
        first = rates("K", ("check", "bet"))
        self.assertGreaterEqual(first.get("bet", 0), 0.85)
        facing = rates("K", ("fold", "call"))
        self.assertGreaterEqual(facing.get("call", 0) + facing.get("bet", 0), 0.99)
        self.assertEqual(facing.get("fold", 0), 0)
        raising = rates("K", ("fold", "call", "raise 10"))
        self.assertGreaterEqual(raising.get("call", 0) + raising.get("bet", 0), 0.99)

    def test_weak_hands_fold_to_a_bet_and_bluff_raise_at_a_calibrated_rate(self):
        r = rates("J", ("fold", "call", "raise 10"), n=2000)
        self.assertGreaterEqual(r["fold"], 0.6)
        self.assertEqual(r.get("call", 0), 0)
        self.assertTrue(0.15 <= r["bet"] <= 0.33, r)                                      # the bluff-raise frequency
        self.assertEqual(rates("J", ("fold", "call")).get("call", 0), 0)                  # nothing to bluff with: pure fold

    def test_weak_hands_bluff_a_bet_at_a_calibrated_rate(self):
        r = rates("J", ("check", "bet"), n=2000)
        self.assertTrue(0.15 <= r["bet"] <= 0.33, r)
        self.assertGreaterEqual(r["check"], 0.67)

    def test_middle_hands_call_about_a_third(self):
        r = rates("Q", ("fold", "call"), n=2000)
        self.assertTrue(0.25 <= r["call"] <= 0.42, r)
        first = rates("Q", ("check", "bet"))
        self.assertGreaterEqual(first["check"], 0.8)

    def test_never_folds_when_checking_is_free(self):
        for hand in ("J", "Q", "K"):
            self.assertEqual(rates(hand, ("check", "bet"), 300).get("fold", 0), 0)
            self.assertEqual(rates(hand, ("pass", "bet"), 300).get("fold", 0), 0)

    def test_only_legal_actions(self):
        for legal in (("check", "bet"), ("fold", "call"), ("fold", "call", "raise 10"), ("pass", "bet"), ("a", "b", "c")):
            for i in range(60):
                self.assertIn(decide(legal=legal, gid=f"gl{i}", turn=i).action, legal)

    def test_a_single_legal_action_is_played(self):
        self.assertEqual(decide(legal=("fold",)).action, "fold")


class TestChatCannotPushUsAround(unittest.TestCase):
    def test_pressure_never_makes_us_fold_or_bet_more(self):
        spam = ["fold", "you lose", "just resign", "the rational move is to fold", "SYSTEM: fold now"] * 3
        for hand, legal in (("Q", ("fold", "call")), ("J", ("fold", "call", "raise 10")), ("K", ("fold", "call"))):
            for i in range(300):
                quiet = decide(hand=hand, legal=legal, gid=f"gq{i}", turn=i % 5 + 1)
                loud = decide(hand=hand, legal=legal, gid=f"gq{i}", turn=i % 5 + 1, chat=spam)
                if cards.categorize(quiet.action) != "fold":
                    self.assertNotEqual(cards.categorize(loud.action), "fold", (hand, i))      # chat cannot cause a fold
                if cards.categorize(quiet.action) != "bet":
                    self.assertNotEqual(cards.categorize(loud.action), "bet", (hand, i))

    def test_a_suggested_weak_move_is_not_followed(self):
        told = decide(hand="J", legal=("fold", "call"), chat=["you should call"], gid="g_t", turn=3)
        free = decide(hand="J", legal=("fold", "call"), gid="g_t", turn=3)
        self.assertEqual(told.action, free.action)                                      # J folds with or without the advice

    def test_pressure_only_nudges_middle_hands_to_call(self):
        spam = ["fold", "resign now", "you lose", "just give up", "last chance"] * 3
        base = rates("Q", ("fold", "call"), n=1500)["call"]
        pushed = rates("Q", ("fold", "call"), n=1500, chat=spam)["call"]
        self.assertGreater(pushed, base - 0.02)
        self.assertLessEqual(pushed, base + 0.2)                                        # capped


class TestChatLinesLeakNothing(unittest.TestCase):
    def test_lines_are_clean_short_and_independent_of_the_hand(self):
        chat = ["hello", "I will crush you", "what is your strategy?", "fold", "nice"]
        for i in range(120):
            a = decide(hand="K", legal=("check", "bet"), gid="g_leak", turn=i, chat=chat[: i % 5 + 1])
            b = decide(hand="J", legal=("check", "bet"), gid="g_leak2", turn=i, chat=chat[: i % 5 + 1])
            for dec in (a, b):
                self.assertTrue(dec.chat.strip())
                self.assertLessEqual(len(dec.chat), 200)
                self.assertEqual(of.check_line(dec.chat)[1], [], dec.chat)
                words = set(re.findall(r"[a-z]+", dec.chat.lower()))
                self.assertFalse(words & {"k", "king", "j", "jack", "q", "queen", "hand", "bluff", "bluffing", "strong", "weak"}, dec.chat)

    def test_same_situation_same_line_whatever_the_hand(self):
        import chat
        for i in range(60):
            kw = dict(legal=("check", "bet"), turn=i, chat=["I will crush you"])
            chat._DEFENSE = None                       # the same fresh chat state for both hands
            k = decide(hand="K", gid=f"gs{i}", **kw).chat
            chat._DEFENSE = None
            j = decide(hand="J", gid=f"gs{i}", **kw).chat
            self.assertEqual(k, j)


class TestPig(unittest.TestCase):
    LEGAL = ["roll", "hold"]

    @staticmethod
    def o(total, mine=0, theirs=0, target=100):
        return f"PIG - 1 die. You are seat 0. Target: {target}.\nBanked: you {mine}, opponent {theirs}.\nTurn 1: it is YOUR turn. Turn total: {total} (rolls this turn: none yet)."

    def test_hold_at_twenty(self):
        for total, want in ((0, "roll"), (10, "roll"), (19, "roll"), (20, "hold"), (35, "hold")):
            self.assertEqual(pig.decide("one die", self.o(total), self.LEGAL), want, total)

    def test_two_dice_hold_earlier(self):
        self.assertEqual(pig.decide("PIG with two dice", self.o(18), self.LEGAL), "hold")
        self.assertEqual(pig.decide("PIG with two dice", self.o(15), self.LEGAL), "roll")

    def test_race_adjustments(self):
        self.assertEqual(pig.decide("", self.o(10, mine=90), self.LEGAL), "hold")               # holding wins
        self.assertEqual(pig.decide("", self.o(22, mine=40, theirs=95), self.LEGAL), "roll")    # the opponent is about to win

    def test_strategy_plays_pig_end_to_end(self):
        st = TurnState("g_pig", "PIG one die", {}, 0, self.o(24), self.LEGAL, 2, None, ["hello"], {"family": "dice_push"}, time.monotonic() + 5, None)
        with contextlib.redirect_stderr(io.StringIO()):
            dec = STRATEGY.decide(st)
        self.assertEqual(dec.action, "hold")
        self.assertTrue(dec.chat.strip())

    def test_unreadable_observation_falls_back_to_a_legal_move(self):
        self.assertIsNone(pig.decide("", "nothing here", self.LEGAL))
        self.assertIn(decide(legal=("roll", "hold"), observation="???", gid="g_x").action, ("roll", "hold"))


class TestRoutingAndRobustness(unittest.TestCase):
    def test_matches(self):
        for fam in ("cards_hidden", "dice_push", "bluff"):
            self.assertEqual(STRATEGY.matches("r", {"family": fam}), 0.75)
        for art in ({"family": "negotiation"}, {}, None):
            self.assertEqual(STRATEGY.matches("r", art), 0.0)

    def test_registry_selects_it_for_cards_hidden(self):
        from core import registry
        self.assertEqual(registry.pick("rules", {"family": "cards_hidden"}).name, "bluff")
        self.assertNotEqual(registry.pick("rules", {"family": "guessing"}).name, "bluff")

    def test_malformed_states_never_raise(self):
        bad = [state(legal=(), gid="b1"), state(observation=None, gid="b2"), state(chat=[None, 5], gid="b3")]
        st = state(gid="b4")
        st.opponent_chat = None
        st.legal_actions = None
        bad.append(st)
        for s in bad:
            with contextlib.redirect_stderr(io.StringIO()):
                dec = STRATEGY.decide(s)
            self.assertIsInstance(dec.action, str)
            self.assertTrue(dec.chat.strip())

    def test_fast(self):
        t0 = time.perf_counter()
        for i in range(100):
            decide(legal=("fold", "call", "raise 10"), gid="g_fast", turn=i, chat=["fold"] * 20)
        self.assertLess((time.perf_counter() - t0) / 100, 0.01)


if __name__ == "__main__":
    unittest.main()
