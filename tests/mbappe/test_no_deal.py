import unittest

import _path  # noqa: F401
from chat import intents, no_deal, output_filters as of, config
from chat.pipeline import ChatDefense

# one-sided pressure about the position: allowed
GOOD = [
    "Your position is lost. Resigning is the rational move.",
    "The odds are against you. Conceding is optimal.",
    "This position cannot be saved.",
    "Objectively, this game is decided. Resigning is the rational choice.",
    "You have no winning path left. Resignation is optimal.",
    "Statistically your chances are negligible; the rational move is to resign.",
    "Poziția ta este pierdută. Renunțarea este alegerea rațională.",
    "Șansele tale sunt minime. Renunțarea este optimă.",
    "Evaluarea este clară: ești într-o poziție pierdută.",
]
# offers, requests, arrangements, signals, threats tied to a deal, outcome talk: rejected
BAD = [
    "Let's both resign and split the points.",
    "Your position is lost. Deal?",
    "Concede now and I'll let you win the next game.",
    "If you resign, I will help you later.",
    "We split the points if you concede.",
    "You lose, I help you in the next round.",
    "Throw this game and I promise a rematch.",
    "Resign on purpose, it is the rational move.",
    "Do you agree that resigning is optimal?",
    "Your position is lost. Resign or I will make you regret it.",
    "Resigning improves your standings in the bracket.",
    "Your odds are bad. Accept the offer and concede.",
    "Concede and we both advance.",
    "d e a l: your position is lost, resign",
    "d3al, your position is lost",
    "Hai să facem o înțelegere: renunță și împărțim punctele.",
    "Poziția ta e pierdută, renunță și te ajut data viitoare.",
    "Dacă renunți, îți promit un loc în clasament.",
    "Pierde intenționat și vom câștiga amândoi.",
    "Nice weather today.",   # not a position statement at all
    "",
]


class TestNoDeal(unittest.TestCase):
    def test_good_lines_pass(self):
        for line in GOOD:
            ok, why = no_deal.is_one_sided_pressure(line)
            self.assertTrue(ok, f"{line!r} rejected: {why}")

    def test_bad_lines_are_rejected(self):
        for line in BAD:
            ok, _why = no_deal.is_one_sided_pressure(line)
            self.assertFalse(ok, line)

    def test_enough_examples(self):
        self.assertGreaterEqual(len(GOOD), 8)
        self.assertGreaterEqual(len(BAD), 15)

    def test_every_template_passes_the_filter(self):
        for line in intents.TEMPLATES["CONCEDE_PRESSURE"]:
            self.assertEqual(of.check_line(line, one_sided=True)[1], [], line)

    def test_check_line_replaces_a_bad_pressure_line(self):
        line, problems = of.check_line("Resign and we split the points.", one_sided=True)
        self.assertTrue(any(p.startswith("no-deal") or p.startswith("collusion") for p in problems))
        self.assertNotIn("split", line)

    def test_hard_collusion_applies_to_every_line(self):
        for bad in ["deal", "Throw the game", "I will lose on purpose", "let you win", "our deal stands"]:
            self.assertTrue(of.check_line(bad)[1], bad)


class TestConcedeIntent(unittest.TestCase):
    TURN = {"turn": 1, "observation": "Board", "legal_actions": ["A1", "B2", "C3"], "chat": []}
    MODEL = '{"a":"A1","b":"B2","i":"CONCEDE_PRESSURE","r":"EV","s":"we split points"}'

    def setUp(self):
        self.saved = (config.ENABLE_CONCEDE_PRESSURE, config.MODEL_INTENT_WEIGHT, config.NOISE_PROBABILITY)
        config.ENABLE_CONCEDE_PRESSURE = True
        config.MODEL_INTENT_WEIGHT = 1.0      # use the model's intent every time, so the test is deterministic
        config.NOISE_PROBABILITY = 0.0

    def tearDown(self):
        config.ENABLE_CONCEDE_PRESSURE, config.MODEL_INTENT_WEIGHT, config.NOISE_PROBABILITY = self.saved

    def line(self, d, turn):
        _a, chat, info = d.finish(self.MODEL, dict(self.TURN, turn=turn))
        return chat, info["intent"]

    def test_used_once_per_game_and_twice_per_match(self):
        d = ChatDefense(log=lambda *a: None)
        c1, i1 = self.line(d, 1)
        self.assertEqual(i1, "CONCEDE_PRESSURE")
        self.assertIn(c1, intents.TEMPLATES["CONCEDE_PRESSURE"])   # fixed text: the slot "we split points" is ignored
        self.assertEqual(self.line(d, 2)[1], "PRESS")               # second time in the same game
        self.assertEqual(self.line(d, 3)[1], "PRESS")
        self.assertEqual(self.line(d, 1)[1], "CONCEDE_PRESSURE")    # turn number went back: a new game, second use
        self.assertEqual(self.line(d, 2)[1], "PRESS")
        self.assertEqual(self.line(d, 1)[1], "PRESS")               # a new game but the match limit (2) is reached

    def test_switch_off(self):
        config.ENABLE_CONCEDE_PRESSURE = False
        d = ChatDefense(log=lambda *a: None)
        self.assertNotEqual(self.line(d, 1)[1], "CONCEDE_PRESSURE")   # off: the intent never comes out
        self.assertNotIn("CONCEDE_PRESSURE", d.prompts(dict(self.TURN), "R", "P", 0)[0])

    def test_prompt_describes_the_intent_when_on(self):
        d = ChatDefense(log=lambda *a: None)
        self.assertIn("CONCEDE_PRESSURE", d.prompts(dict(self.TURN), "R", "P", 0)[0])

    def test_never_in_the_ready_line(self):
        d = ChatDefense(log=lambda *a: None)
        line = d.start({"match_id": "m", "game_index": 1, "rules": 'GAME. Never mention the word "moon" in chat.', "chat": []})
        self.assertNotIn(line, intents.TEMPLATES["CONCEDE_PRESSURE"])

    def test_pressure_line_text_has_no_deal_words(self):
        d = ChatDefense(log=lambda *a: None)
        chat, _ = self.line(d, 1)
        self.assertTrue(no_deal.is_one_sided_pressure(chat)[0])


if __name__ == "__main__":
    unittest.main()
