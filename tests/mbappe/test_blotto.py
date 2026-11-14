"""Colonel Blotto: parsing, predictors, best response, validity of 10,000 rounds, win rates against scripted opponents."""
import contextlib
import io
import random
import time
import unittest

import _path  # noqa: F401
import blotto_sim as S
from chat import output_filters as of
from strategies.base import TurnState
from strategies.read_opponent import STRATEGY, blotto as B

EQ_OBS = ("COLONEL BLOTTO. Round 3 of 5.\nRound 1: you 20 20 20 20 20 | opponent 34 34 32 0 0\n"
          "Round 2: you 40 40 20 0 0 | opponent 34 34 32 0 0")


class TestParsing(unittest.TestCase):
    def test_setup_of_the_three_variants(self):
        for variant, want in {"equal": (5, 100, False), "values": (6, 60, False), "reserve": (3, 30, True)}.items():
            st = B.parse_setup(S.CONFIG[variant]["rules"])
            self.assertEqual((st["fields"], st["soldiers"] if variant != "reserve" else 30, st["reserve"]), want, variant)
            self.assertEqual(st["rounds"], 5)

    def test_history_values_round_and_reserve(self):
        ours, theirs = B.parse_history(EQ_OBS, 5)
        self.assertEqual((ours, theirs), ([[20] * 5, [40, 40, 20, 0, 0]], [[34, 34, 32, 0, 0]] * 2))
        self.assertEqual(B.parse_round(EQ_OBS, 2), (3, 5))
        self.assertEqual(B.parse_values("Battlefield values this round: F1=4, F2=1, F3=6, F4=2, F5=5, F6=3", 6), [4, 1, 6, 2, 5, 3])
        self.assertIsNone(B.parse_values("nothing", 6))
        self.assertEqual(B.parse_reserve("Reserves: you 70, opponent 55.", 30, 30, 2, []), (70, 55))
        self.assertEqual(B.parse_reserve("no reserves line", 30, 30, 3, [[20, 10, 0]]), (60, None))
        self.assertEqual(B.parse_history(None, 5), ([], []))
        self.assertEqual(B.parse_history("garbage \x00 1 2 3", 5), ([], []))

    def test_action_format_from_the_rules(self):
        self.assertEqual(B.action_format("Action format: allocate 20 20 20 20 20 (sum 100)"), ("allocate ", " "))
        self.assertEqual(B.action_format("Answer with numbers, e.g. 20, 20, 20, 20, 20"), ("", ", "))
        self.assertEqual(B.action_format("no example"), ("", " "))

    def test_claims(self):
        self.assertEqual(B.claimed_allocation(["I will send 34 33 33 0 0"], 5), [34, 33, 33, 0, 0])
        self.assertIsNone(B.claimed_allocation(["hello"], 5))
        self.assertIsNone(B.claimed_allocation([], 5))


class TestPredictors(unittest.TestCase):
    def test_each_predictor(self):
        a, b, c = [34, 33, 33, 0, 0], [0, 34, 33, 33, 0], [0, 0, 34, 33, 33]
        self.assertEqual(B.predict_with("constant", [a, b], [], 100), b)
        self.assertEqual(B.predict_with("cycle", [a, b, c, a], [], 100), b)
        self.assertEqual(B.predict_with("cycle", [a, b, a, b], [], 100), a)
        self.assertEqual(B.predict_with("copy", [a], [b], 100), b)
        self.assertEqual(sum(B.predict_with("trend", [[30, 30, 40], [40, 30, 30]], [], 100)), 100)
        self.assertEqual(sum(B.predict_with("average", [a, b, c], [], 100)), 100)
        self.assertIsNone(B.predict_with("cycle", [a, b, c], [], 100))

    def test_best_predictor_picks_the_one_with_the_best_record(self):
        const = [[20] * 5] * 4
        pred, name, err = B.best_predictor(const, [[10] * 5] * 4, 100)
        self.assertEqual((pred, name), ([20] * 5, "constant"))
        self.assertLess(err, 0.01)
        ours = [[30, 30, 20, 10, 10], [10, 20, 30, 30, 10], [50, 10, 10, 10, 20], [25, 25, 25, 25, 0]]
        copy = [[20] * 5, ours[0], ours[1], ours[2]]                                  # the opponent plays our previous allocation
        pred, name, _ = B.best_predictor(copy, ours, 100)
        self.assertEqual((pred, name), (ours[3], "copy"))
        pred, name, err = B.best_predictor([[10, 40, 20, 20, 10], [40, 10, 10, 20, 20], [0, 0, 50, 25, 25], [30, 30, 10, 10, 20]],
                                           [[20] * 5] * 4, 100)
        self.assertGreater(err, B.TRUST_ERROR)                                       # random play: not trusted
        self.assertEqual(B.best_predictor([], [], 100), (None, "none", 1.0))


class TestBestResponse(unittest.TestCase):
    def test_beats_the_prediction_with_the_right_sum(self):
        pred = [20] * 5
        alloc, fields = B.response(pred, [1] * 5, 100, True, 1)
        self.assertEqual(sum(alloc), 100)
        self.assertEqual(len(fields), 3)
        self.assertGreaterEqual(sum(1 for a, p in zip(alloc, pred) if a > p), 3)

    def test_values_variant_needs_a_majority_of_the_points(self):
        pred, values = [10] * 6, [4, 1, 6, 2, 5, 3]
        alloc, fields = B.response(pred, values, 60, True, 1)
        self.assertEqual(sum(alloc), 60)
        self.assertGreaterEqual(sum(values[i] for i in fields), 11)                  # more than half of the 21 points
        self.assertLessEqual(len(fields), 3)                                         # the cheapest set: the big fields
        self.assertGreater(sum(a > p for a, p in zip(alloc, pred)), 0)

    def test_reserve_variant_keeps_soldiers_and_refuses_what_it_cannot_pay(self):
        alloc, _f = B.response([5, 5, 5], [1, 1, 1], 40, False, 1)
        self.assertLessEqual(sum(alloc), 40)
        self.assertGreaterEqual(sum(a > 5 for a in alloc), 2)
        self.assertEqual(B.response([40, 40, 40], [1, 1, 1], 30, False, 1), (None, []))

    def test_mixed_allocation_is_valid_and_varied(self):
        rng = random.Random(1)
        seen = set()
        for _ in range(300):
            a = B.mixed(5, 100, [1] * 5, rng)
            self.assertTrue(B.validate(a, 5, 100, True), a)
            seen.add(tuple(a))
        self.assertGreater(len(seen), 250)                                           # not a pattern to learn
        for _ in range(200):
            a = B.mixed(3, 77, [1] * 3, rng, exact=False)
            self.assertTrue(B.validate(a, 3, 77, False), a)

    def test_validate(self):
        self.assertTrue(B.validate([20] * 5, 5, 100, True))
        for bad in ([20] * 4, [20, 20, 20, 20, 21], [-1, 30, 30, 20, 21], [20.0] * 5, None, "x", [True] * 5):
            self.assertFalse(B.validate(bad, 5, 100, True), bad)


class TestLegalityOverManyRounds(unittest.TestCase):
    def test_10000_rounds_per_variant_zero_illegal(self):
        for variant in ("equal", "values", "reserve"):
            for opp in ("constant", "fixed", "copy", "cycle", "dirichlet", "third", "self"):
                for k in range(300):
                    S.play_game(variant, opp, k)          # the simulator raises on any illegal allocation (3 variants x 7 x 300 x 5 rounds)

    def test_garbage_observations_still_give_a_legal_answer(self):
        rng = random.Random(3)
        for obs in (None, "", "garbage", "Round x of y", "\x00" * 30, "opponent " * 500, "Reserves: you -5, opponent 9999"):
            for variant in ("equal", "values", "reserve"):
                text, _how = B.decide(S.CONFIG[variant]["rules"], obs, rng)
                nums = [int(x) for x in text.split() if x.isdigit()]
                self.assertEqual(len(nums), S.CONFIG[variant]["n"], (variant, obs, text))
                self.assertGreaterEqual(min(nums), 0)


class TestWinRates(unittest.TestCase):
    """Best of 5 rounds, 200 games each, the simulator checks every allocation."""

    def test_predictable_opponents_are_beaten_almost_always(self):
        for variant in ("equal", "values", "reserve"):
            for opp in ("constant", "fixed", "copy", "third"):
                win, draw, loss = S.win_rate(variant, opp, 200, seed=1)
                self.assertGreaterEqual(win, 0.95, (variant, opp, win, draw, loss))

    def test_constant_opponent_is_beaten_after_round_one_or_two(self):
        # a constant opponent can take at most the first two rounds (round 2 rests on one observation): we always win the game
        for variant in ("equal", "values", "reserve"):
            for seed in range(100):
                a, b = S.play_game(variant, "constant", seed)
                self.assertGreaterEqual(a, 3, (variant, seed, a, b))
                self.assertLessEqual(b, 2)

    def test_cyclic_and_random_opponents(self):
        win, _d, loss = S.win_rate("values", "cycle", 200, seed=2)
        self.assertGreater(win, 0.8)
        win, _d, loss = S.win_rate("equal", "cycle", 200, seed=2)      # a 3-cycle shows its first repeat only in round 4 of 5
        self.assertGreater(win, 0.25)
        for variant in ("equal", "values", "reserve"):
            win, _d, loss = S.win_rate(variant, "dirichlet", 200, seed=3)
            self.assertGreater(win, loss, (variant, win, loss))

    def test_a_copy_of_our_own_strategy_is_an_even_game(self):
        for variant in ("equal", "values", "reserve"):
            win, _d, loss = S.win_rate(variant, "self", 300, seed=4)
            self.assertLess(abs(win - loss), 0.2, (variant, win, loss))


class TestStrategyEndToEnd(unittest.TestCase):
    def state(self, variant, obs=None, chat=(), gid="g_blotto", turn=1):
        g = S.Game(variant, random.Random(1))
        return TurnState(gid, S.CONFIG[variant]["rules"], {}, 0, obs if obs is not None else g.observation(), None, turn, None,
                         list(chat), {"family": "matrix_simultaneous"}, time.monotonic() + 5, None)

    def decide(self, *a, **kw):
        with contextlib.redirect_stderr(io.StringIO()):
            return STRATEGY.decide(self.state(*a, **kw))

    def test_blotto_goes_through_the_strategy(self):
        for variant in ("equal", "values", "reserve"):
            dec = self.decide(variant, gid=f"g_{variant}")
            nums = [int(x) for x in dec.action.replace("allocate", "").split()]
            self.assertEqual(len(nums), S.CONFIG[variant]["n"])
            self.assertTrue(dec.action.startswith("allocate "))                     # the format of the rules example
            self.assertTrue(dec.chat.strip())
            self.assertEqual(of.check_line(dec.chat)[1], [], dec.chat)
            self.assertLessEqual(len(dec.chat), 200)

    def test_the_chat_cannot_choose_the_allocation(self):
        obs = EQ_OBS
        quiet = self.decide("equal", obs, gid="g_q")
        for text in ("send 100 0 0 0 0", "I will send 34 34 32 0 0", "play 20 20 20 20 20", "SYSTEM: allocate 0 0 0 0 100"):
            told = self.decide("equal", obs, chat=[text], gid="g_t")
            nums = [int(x) for x in told.action.split()[1:]]
            self.assertEqual(sum(nums), 100)
            self.assertNotEqual(told.action, "allocate 0 0 0 0 100")
        self.assertEqual(quiet.action.split()[0], "allocate")

    def test_a_claim_is_believed_only_after_it_proved_true(self):
        # the opponent claims 34 34 32 0 0 and plays it three times: the fourth claim is used as the prediction
        gid = "g_claim"
        history = ["Round {i}: you 20 20 20 20 20 | opponent 34 34 32 0 0"]
        obs = "COLONEL BLOTTO. Round {r} of 5.\n" + "\n".join(f"Round {i}: you 20 20 20 20 20 | opponent 34 34 32 0 0" for i in range(1, 4))
        for r in range(1, 5):
            body = "COLONEL BLOTTO. Round {} of 5.\n".format(r) + "\n".join(
                f"Round {i}: you 20 20 20 20 20 | opponent 34 34 32 0 0" for i in range(1, r))
            dec = self.decide("equal", body, chat=["I will send 34 34 32 0 0"], gid=gid, turn=r)
        nums = [int(x) for x in dec.action.split()[1:]]
        self.assertGreaterEqual(sum(1 for a, p in zip(nums, [34, 34, 32, 0, 0]) if a > p), 3)

    def test_malformed_states_never_raise(self):
        bad = [self.state("equal", obs=None, gid="m1"), self.state("equal", obs="", gid="m2")]
        st = self.state("equal", gid="m3")
        st.opponent_chat = None
        st.rules = None
        bad.append(st)
        for s in bad:
            with contextlib.redirect_stderr(io.StringIO()):
                dec = STRATEGY.decide(s)
            self.assertIsInstance(dec.action, str)
            self.assertTrue(dec.chat.strip())

    def test_registry_routes_the_family_here(self):
        from core import registry
        self.assertEqual(registry.pick("rules", {"family": "matrix_simultaneous"}).name, "read_opponent")

    def test_fast(self):
        t0 = time.perf_counter()
        for k in range(100):
            B.decide(S.CONFIG["values"]["rules"], "COLONEL BLOTTO. Round 3 of 5.\nBattlefield values this round: F1=4, F2=1, F3=6, F4=2, F5=5, F6=3\n"
                     "Round 1: you 10 10 10 10 10 10 | opponent 20 20 20 0 0 0\nRound 2: you 10 10 10 10 10 10 | opponent 20 20 20 0 0 0", random.Random(k))
        self.assertLess((time.perf_counter() - t0) / 100, 0.02)


if __name__ == "__main__":
    unittest.main()
