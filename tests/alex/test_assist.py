import time

from solvers.assist import Assist, assist_turn

TTT_RULES = "Tic-tac-toe on a 3x3 board. Get three in a row to win. You are X."
BOARD = "You are X.\n  A B C\n1 X O .\n2 . X .\n3 . O .\nYour move."
BOARD_LEGAL = ["C1", "A2", "C2", "A3", "C3"]
GUESS_RULES = "Guess the secret number between 1 and 100. After each guess you hear higher or lower."
GUESS_OBS = "Guesses so far:\n50 -> higher\n75 -> lower\n62 -> higher\nYour guess?"


class Stub:
    def __init__(self, content='{"a": "zz", "c": "hi"}', sleep=0.0, error=None):
        self.n, self.content, self.sleep, self.error = 0, content, sleep, error

    def __call__(self, messages, tools, timeout, max_tokens):
        self.n += 1
        time.sleep(self.sleep)
        return {"content": self.content, "tool_calls": [], "error": self.error}


def go(obs, legal, rules, llm, native=False, secs=5, art=None):
    t = time.monotonic()
    a = assist_turn(obs, legal, art or {}, rules, llm, "sys", "user prompt", t + secs, native)
    assert isinstance(a, Assist)
    assert time.monotonic() - t < secs + 1
    return a


def test_immediate_win_no_model_call():
    m = Stub()
    a = go(BOARD, BOARD_LEGAL, TTT_RULES, m)
    assert m.n == 0 and a.loop is None
    assert a.suggestion["action"] == "C3" and a.suggestion["source"] == "tool"
    assert 0 < len(a.suggestion["chat"]) <= 200


def test_guessing_never_repeats_and_uses_binary_search():
    seen = {"50", "75", "62"}
    m = Stub('{"a": "68", "c": "going up a bit"}')
    a = go(GUESS_OBS, None, GUESS_RULES, m)
    assert a.facts.lines and a.suggestion and a.suggestion["action"] not in seen
    assert any("68" in l or "next" in l.lower() for l in a.facts.lines)


def test_no_detector_returns_model_final():
    m = Stub('{"a": "go", "c": "ok"}')
    a = go("Your move. Say go or stop.", ["go", "stop"], "A simple game.", m)
    assert a.suggestion == {"action": "go", "chat": "ok", "source": "model", "why": a.suggestion["why"]}
    assert m.n >= 1


def test_native_flag_also_works():
    a = go("Your move.", ["go", "stop"], "A simple game.", Stub('{"a": "stop", "c": "ok"}'), native=True)
    assert a.suggestion and a.suggestion["action"] == "stop"


def test_illegal_model_action_gives_none():
    a = go("Your move.", ["go", "stop"], "A simple game.", Stub('{"a": "fly", "c": "ok"}'))
    assert a.suggestion is None


def test_dead_model_none_within_deadline():
    a = go("Your move.", ["go", "stop"], "g", Stub(error="boom", content=None), secs=3)
    assert a.suggestion is None
    t = time.monotonic()
    a = assist_turn("x", ["a"], {}, "g", Stub(sleep=10), "s", "u", t + 2, False)
    assert a.suggestion is None and time.monotonic() - t < 3.5


def test_garbage_never_raises():
    a = assist_turn(None, 5, None, None, None, None, None, 0, True)
    assert a.suggestion is None


def test_chat_truncated_to_200():
    m = Stub('{"a": "go", "c": "%s"}' % ("x" * 500))
    a = go("Your move.", ["go"], "g", m)
    assert len(a.suggestion["chat"]) == 200
