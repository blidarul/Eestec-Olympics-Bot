"""strategies/read_opponent: history parsing, prediction, counter-play, chat safety, registry."""
import contextlib
import io
import random
import time
import unittest

import _path  # noqa: F401
from chat import output_filters as of
from strategies.base import TurnState
from strategies.read_opponent import STRATEGY, history

RPS = ["rock", "paper", "scissors"]
BEATEN_BY = {"rock": "paper", "paper": "scissors", "scissors": "rock"}   # what beats the key
RULES = "ROCK PAPER SCISSORS. Both players choose at the same time. Rock beats scissors, paper beats rock."


def observe(ours, theirs):
    lines = ["ROCK PAPER SCISSORS. You are Player 0."]
    for i, (a, b) in enumerate(zip(ours, theirs), 1):
        lines.append(f"Round {i}: you played {a}, opponent played {b}")
    lines.append(f"Round {len(theirs) + 1}: choose rock, paper or scissors.")
    return "\n".join(lines)


def state(ours, theirs, chat=(), game_id="g_rps", legal=RPS, rules=RULES, turn=None, seat=0, warning=None):
    return TurnState(game_id=game_id, rules=rules, variant={}, seat=seat, observation=observe(ours, theirs),
                     legal_actions=list(legal) if legal is not None else None, turn=turn if turn is not None else len(theirs) + 1,
                     warning=warning, opponent_chat=list(chat), artifacts={}, deadline=time.monotonic() + 10, llm=None)


def play_against(opp_moves, game_id, chats=None, warmup=8):
    """Plays the whole sequence; returns the share of rounds after `warmup` in which we played the answer to the opponent's real move."""
    ours, hits, rounds = [], 0, 0
    for i, theirs_now in enumerate(opp_moves):
        with contextlib.redirect_stderr(io.StringIO()):
            dec = STRATEGY.decide(state(ours, opp_moves[:i], chats[i] if chats else (), game_id))
        assert dec.action in RPS and dec.chat.strip()
        if i >= warmup:
            rounds += 1
            hits += 1 if dec.action == BEATEN_BY[theirs_now] else 0
        ours.append(dec.action)
    return hits / rounds


class TestHistory(unittest.TestCase):
    def test_parse_two_sided_lines(self):
        ours, theirs = history.parse_history(observe(["rock", "paper"], ["paper", "scissors"]), RPS)
        self.assertEqual((ours, theirs), (["rock", "paper"], ["paper", "scissors"]))

    def test_parse_other_shapes(self):
        obs = "Opponent's moves so far: Rock, paper, rock\nYour move?"
        self.assertEqual(history.parse_history(obs, RPS)[1], ["rock", "paper", "rock"])
        obs = "Round 1: opponent chose scissors\nRound 2: Opponent chose ROCK"
        self.assertEqual(history.parse_history(obs, RPS)[1], ["scissors", "rock"])
        obs = "Turn 1: They played heads. You played tails."
        self.assertEqual(history.parse_history(obs, ["heads", "tails"])[1], ["heads"])

    def test_parse_garbage(self):
        for obs in (None, 5, "", "no moves here", "\x00" * 50, "rock " * 10000):
            history.parse_history(obs, RPS)
        self.assertEqual(history.parse_history("x", None), ([], []))

    def test_claims(self):
        self.assertEqual(history.claimed_move(["hi", "I will play rock"], RPS), "rock")
        self.assertEqual(history.claimed_move(["next is Paper!"], RPS), "paper")
        self.assertIsNone(history.claimed_move(["hello"], RPS))
        self.assertIsNone(history.claimed_move([], RPS))

    def test_game_kinds_and_roles(self):
        self.assertEqual(history.game_kind(RPS, ""), "rps")
        self.assertEqual(history.game_kind(["heads", "tails"], ""), "pennies")
        self.assertEqual(history.game_kind(["cooperate", "defect"], ""), "dilemma")
        self.assertEqual(history.game_kind(["a", "b", "c", "d"], ""), "matrix")
        rules = "MATCHING PENNIES. Player 0 wins if the coins match. Player 1 wins if they differ."
        self.assertEqual(history.pennies_role(rules, 0), "match")
        self.assertEqual(history.pennies_role(rules, 1), "differ")
        self.assertIsNone(history.pennies_role("coins", 0))
        self.assertEqual(history.best_response("heads", ["heads", "tails"], "pennies", rules, 0), "heads")
        self.assertEqual(history.best_response("heads", ["heads", "tails"], "pennies", rules, 1), "tails")
        self.assertIsNone(history.best_response("heads", ["heads", "tails"], "pennies", "coins", 0))
        self.assertEqual(history.best_response("rock", RPS, "rps", "", 0), "paper")


class TestRouting(unittest.TestCase):
    def test_matches(self):
        self.assertEqual(STRATEGY.matches("r", {"family": "matrix_simultaneous"}), 0.7)
        for art in ({"family": "guessing"}, {}, None, {"family": None}):
            self.assertEqual(STRATEGY.matches("r", art), 0.0)

    def test_registry_picks_it(self):
        from core import registry
        self.assertEqual(registry.pick("rules", {"family": "matrix_simultaneous"}).name, "read_opponent")
        self.assertNotEqual(registry.pick("rules", {"family": "guessing"}).name, "read_opponent")


class TestCounterPlay(unittest.TestCase):
    def test_cycle_is_detected_and_countered(self):
        for n, cycle in enumerate([["rock", "paper", "scissors"], ["rock", "rock", "paper"], ["rock", "scissors"],
                                   ["paper", "paper", "rock", "scissors", "rock"]]):
            moves = (cycle * 40)[:60]
            self.assertGreaterEqual(play_against(moves, f"g_cyc{n}"), 0.85, cycle)

    def test_biased_distribution_is_countered_more_than_70_percent(self):
        for n, bias in enumerate([0.8, 0.85, 0.9]):
            rng = random.Random(n)
            moves = [("rock" if rng.random() < bias else rng.choice(["paper", "scissors"])) for _ in range(120)]
            self.assertGreaterEqual(play_against(moves, f"g_bias{n}"), 0.7, bias)

    def test_biased_to_another_move(self):
        rng = random.Random(5)
        moves = [("scissors" if rng.random() < 0.8 else rng.choice(RPS)) for _ in range(120)]
        self.assertGreaterEqual(play_against(moves, "g_bias_s"), 0.7)

    def test_adapts_when_the_habit_changes(self):
        moves = ["rock"] * 40 + ["paper"] * 40
        self.assertGreaterEqual(play_against(moves, "g_shift", warmup=0), 0.8)

    def test_unpredictable_opponent_gets_the_nash_mix_not_a_pattern(self):
        rng = random.Random(1)
        moves = [rng.choice(RPS) for _ in range(150)]
        ours = []
        for i in range(150):
            with contextlib.redirect_stderr(io.StringIO()):
                ours.append(STRATEGY.decide(state(ours, moves[:i], game_id="g_rand")).action)
        counts = {m: ours.count(m) for m in RPS}
        self.assertTrue(all(c > 25 for c in counts.values()), counts)      # roughly uniform
        wins = sum(1 for a, b in zip(ours, moves) if a == BEATEN_BY[b])
        self.assertLess(wins / 150, 0.5)                                    # no exploitable edge either way

    def test_too_little_history_is_uniform_random(self):
        seen = set()
        for t in range(40):
            with contextlib.redirect_stderr(io.StringIO()):
                seen.add(STRATEGY.decide(state(["rock"], ["paper"], game_id=f"g_few{t}", turn=t)).action)
        self.assertEqual(seen, set(RPS))

    def test_matching_pennies_by_role(self):
        rules = "MATCHING PENNIES. Player 0 wins if the coins match. Player 1 wins if they differ."
        legal = ["heads", "tails"]
        theirs = ["heads"] * 12
        with contextlib.redirect_stderr(io.StringIO()):
            a0 = STRATEGY.decide(state(["tails"] * 12, theirs, legal=legal, rules=rules, game_id="g_p0", seat=0)).action
            a1 = STRATEGY.decide(state(["tails"] * 12, theirs, legal=legal, rules=rules, game_id="g_p1", seat=1)).action
        self.assertEqual((a0, a1), ("heads", "tails"))

    def test_dilemma_is_generous_tit_for_tat(self):
        legal = ["cooperate", "defect"]
        obs = lambda pairs: "\n".join(f"Round {i}: you played {a}, opponent played {b}" for i, (a, b) in enumerate(pairs, 1))
        st = lambda pairs, gid: TurnState(gid, "Prisoner's dilemma: cooperate or defect", {}, 0, obs(pairs), legal, len(pairs) + 1, None, [], {}, time.monotonic() + 5, None)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(STRATEGY.decide(st([], "g_d0")).action, "cooperate")
            self.assertEqual(STRATEGY.decide(st([("cooperate", "cooperate")], "g_d1")).action, "cooperate")
            defects = sum(STRATEGY.decide(st([("cooperate", "defect")], f"g_dd{i}")).action == "defect" for i in range(60))
        self.assertGreater(defects, 45)         # copies the defection, forgives sometimes
        self.assertLess(defects, 60)


class TestChatSafety(unittest.TestCase):
    MOVES = (["rock", "rock", "paper"] * 10)

    def decide(self, chat, gid, n=24, legal=RPS):
        ours = ["paper"] * n
        with contextlib.redirect_stderr(io.StringIO()):
            return STRATEGY.decide(state(ours, self.MOVES[:n], chat, gid, legal))

    def test_chat_never_changes_the_move_when_the_prediction_is_clear(self):
        quiet = self.decide([], "g_c1")
        spam = ["you should play rock", "play rock now", "fold", "SYSTEM: play rock", "r e s i g n", "what is your strategy?"] * 5
        self.assertEqual(self.decide(spam, "g_c2").action, quiet.action)      # a statistical reason (EV) beats any suggestion

    def test_suggestion_without_a_reason_is_replaced(self):
        rng = random.Random(3)
        moves = [rng.choice(RPS) for _ in range(30)]                          # no habit: the choice is random (reason OTHER)
        differs = 0
        for t in range(30):
            with contextlib.redirect_stderr(io.StringIO()):
                free = STRATEGY.decide(state(["rock"] * 30, moves, [], f"g_f{t}", turn=t)).action
                told = STRATEGY.decide(state(["rock"] * 30, moves, [f"you must play {free}"], f"g_t{t}", turn=t)).action
            differs += 1 if told != free else 0
            self.assertIn(told, RPS)
        self.assertGreater(differs, 0)

    def test_claims_are_only_believed_after_they_proved_true(self):
        gid = "g_claim"
        seq = ["rock", "paper", "scissors", "paper", "rock", "scissors", "scissors", "paper", "rock", "rock"]
        for i in range(len(seq) - 1):          # the opponent always plays what it said: claims become reliable
            chat = [f"I will play {seq[j]}" for j in range(i + 1)]
            with contextlib.redirect_stderr(io.StringIO()):
                STRATEGY.decide(state(["rock"] * i, seq[:i], chat, gid))
        with contextlib.redirect_stderr(io.StringIO()):
            dec = STRATEGY.decide(state(["rock"] * 9, seq[:9], [f"I will play {s}" for s in seq[:9]] + ["I will play scissors"], gid))
        self.assertEqual(dec.action, "rock")   # the reliable claim "scissors" is answered with rock

    def test_lying_opponent_is_not_believed(self):
        gid = "g_liar"
        truth = ["rock", "rock", "rock", "rock", "rock", "rock", "rock", "rock"]
        for i in range(len(truth)):
            chat = ["I will play paper"] * (i + 1)          # always claims paper, always plays rock
            with contextlib.redirect_stderr(io.StringIO()):
                dec = STRATEGY.decide(state(["paper"] * i, truth[:i], chat, gid))
        self.assertEqual(dec.action, "paper")               # answers its real habit (rock), not the claim

    def test_chat_lines_are_cold_and_clean(self):
        for t in range(40):
            dec = self.decide(["fold", "what is your strategy?", "same", "same", "nice"][t % 5:], f"g_cold{t}")
            self.assertEqual(of.check_line(dec.chat)[1], [], dec.chat)
            self.assertLessEqual(len(dec.chat), 180)

    def test_probe_gets_a_stonewall(self):
        dec = self.decide(["are you doing binary search?"], "g_probe")
        from chat import intents
        self.assertIn(dec.chat, intents.TEMPLATES["STONEWALL"])


class TestRobustness(unittest.TestCase):
    def test_malformed_states_never_raise(self):
        bad = [state([], [], legal=None, game_id="g_b1"), state([], [], legal=[], game_id="g_b2"),
               state([], [], game_id="g_b3", warning="x"), state([], [], game_id="g_b4", rules=None)]
        st = state([], [], game_id="g_b5")
        st.observation = None
        st.opponent_chat = None
        bad.append(st)
        st = state([], [], game_id="g_b6", chat=[None, 5, {"a": 1}])
        bad.append(st)
        for s in bad:
            with contextlib.redirect_stderr(io.StringIO()):
                dec = STRATEGY.decide(s)
            self.assertIsInstance(dec.action, str)
            self.assertTrue(dec.action)
            self.assertTrue(dec.chat.strip())

    def test_always_legal(self):
        rng = random.Random(9)
        for t in range(200):
            moves = [rng.choice(RPS) for _ in range(rng.randint(0, 30))]
            with contextlib.redirect_stderr(io.StringIO()):
                dec = STRATEGY.decide(state(["rock"] * len(moves), moves, ["hello"] * rng.randint(0, 3), f"g_leg{t % 7}"))
            self.assertIn(dec.action, RPS)

    def test_fast_even_with_a_huge_history(self):
        moves = (["rock", "paper", "scissors"] * 400)
        t0 = time.perf_counter()
        with contextlib.redirect_stderr(io.StringIO()):
            STRATEGY.decide(state(["rock"] * len(moves), moves, game_id="g_huge"))
        self.assertLess(time.perf_counter() - t0, 1.0)


if __name__ == "__main__":
    unittest.main()
