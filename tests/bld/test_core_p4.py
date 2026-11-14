"""End-to-end through main.py (stub LLM, no network): guessing safety net, deduce via prep, ready_line, decision log."""
import json
import os
import subprocess
import sys
import threading
import time
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from chat import config  # noqa: E402
from chat.pipeline import ready_line  # noqa: E402
from core import fallback, hooks, memory, registry, validate  # noqa: E402
from core.hooks import map_engine_variant  # noqa: E402
from core.llm import LLM as LLMClient  # noqa: E402
from strategies.base import TurnState  # noqa: E402
from tests.alex.games import GUESS_MODEL_CODE, TTT_SIM, guess_obs, guess_rules, ttt_sample  # noqa: E402

RULES = guess_rules()
LLM = {"api_key": "k", "base_url": "http://x/v1", "model": "haiku"}


def prep_msg():
    return {"type": "prep", "game_id": "guess_number", "game_name": "Guess", "seconds": 600, "llm": LLM,
            "variants": [{"label": "1-100", "rules": RULES,
                          "sample_turn": {"type": "turn", "turn": 5, "observation": guess_obs([(30, "higher"), (60, "lower")]),
                                          "legal_actions": None, "seconds": 20, "chat": []}}]}


def start_msg(match="m1"):
    return {"type": "start", "match_id": match, "game_index": 1, "game_id": "guess_number", "variant": {"label": "1-100"},
            "rules": RULES, "seat": 0, "llm": LLM}


def turn_msg(history, turn, warning=None, chat=None):
    m = {"type": "turn", "game_index": 1, "turn": turn, "observation": guess_obs(history), "legal_actions": None,
         "seconds": 20, "chat": chat or []}
    if warning:
        m["warning"] = warning
    return m


class Bot:
    def __init__(self, tmp_path, reply):
        env = dict(os.environ, BOT_STUB_LLM="1", BOT_STUB_LLM_REPLY=reply, MEMORY_DIR=str(tmp_path))
        self.p = subprocess.Popen([sys.executable, "-u", "main.py"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, env=env)
        self.err = []
        self.reader = threading.Thread(target=lambda: [self.err.append(l) for l in self.p.stderr], daemon=True)
        self.reader.start()  # drain stderr: a full pipe would block the bot
        self.dog = threading.Timer(90, self.p.kill)   # a stuck bot must fail the test, not hang the run
        self.dog.daemon = True
        self.dog.start()

    def send(self, msg, answer=True) -> dict:
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        return json.loads(line) if (answer and line) else {}

    def close(self):
        self.dog.cancel()
        try:
            self.p.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
            self.p.stdin.flush()
            self.p.wait(timeout=20)
        except Exception:
            self.p.kill()
        self.reader.join(5)
        return "".join(self.err)


def test_safety_net_never_repeats_a_guess_even_if_the_model_does(tmp_path):
    b = Bot(tmp_path, '{"a": "guess 50", "c": "Fifty."}')   # a model that always says the same thing; prepare() cannot verify
    try:
        assert b.send(prep_msg())["type"] == "ready"
        assert b.send(start_msg())["type"] == "ready"
        hist, sent = [], []
        for t in range(1, 9):
            a = b.send(turn_msg(hist, t))
            assert a["type"] == "action" and a["action"].split()[-1].isdigit() and a["chat"]
            assert a["action"] not in sent, f"repeated {a['action']} at turn {t}"
            sent.append(a["action"])
            hist.append((int(a["action"].split()[-1]), "higher"))
    finally:
        err = b.close()
    assert any('"strategy": "generic"' in l for l in err.splitlines() if l.startswith("decision "))


def test_deduce_through_prep_solves_without_repeats_and_logs_decisions(tmp_path):
    reply = json.dumps({"a": "guess 50", "c": "ok", "code": GUESS_MODEL_CODE})
    b = Bot(tmp_path, reply)
    secret = 46
    try:
        assert b.send(prep_msg())["type"] == "ready"
        r = b.send(start_msg("m2"))
        assert r["type"] == "ready" and 0 < len(r["chat"]) <= 200
        hist, sent = [], []
        for t in range(1, 13):
            a = b.send(turn_msg(hist, t))
            assert a["action"] not in sent
            sent.append(a["action"])
            n = int(a["action"].split()[-1])
            if n == secret:
                break
            hist.append((n, "higher" if secret > n else "lower"))
        assert sent[-1] == f"guess {secret}" and len(sent) <= 7, sent
    finally:
        err = b.close()
    recs = [json.loads(l[len("decision "):]) for l in err.splitlines() if l.startswith("decision ")]
    assert recs and all(r["strategy"] == "deduce" and r["tool"] == "deduction" and r["source"] == "tool" for r in recs)
    assert all(r["candidates_left"] is not None and r["answer_ms"] < 12000 and r["family"] == "guessing" for r in recs)
    assert "guessing family, feedback model verified" in recs[0]["reason"]
    assert [r["candidates_left"] for r in recs][0] > [r["candidates_left"] for r in recs][-1] or len(recs) == 1
    assert any(os.path.exists(os.path.join(dp, "feedback_model.py")) for dp, _, fs in os.walk(tmp_path) for f in fs)
    log = [json.loads(l) for dp, _, fs in os.walk(tmp_path) for f in fs if f == "log.jsonl"
           for l in open(os.path.join(dp, f), encoding="utf-8")]
    assert any(r.get("kind") == "decision" and r.get("tool") == "deduction" for r in log)


def test_ready_line_comes_from_chat_pipeline(tmp_path):
    saved = config.PERSONA
    try:
        config.PERSONA = "human"
        b = Bot(tmp_path, '{"a": "", "c": "x"}')
        try:
            r = b.send(start_msg("seed-7"))
        finally:
            b.close()
        assert r["type"] == "ready" and r["chat"] and r["chat"] == ready_line(RULES, [], "seed-7")
    finally:
        config.PERSONA = saved


def test_warning_resend_does_not_count_rejected_action_as_played(tmp_path):
    b = Bot(tmp_path, '{"a": "guess 50", "c": "x"}')
    try:
        b.send(prep_msg())
        b.send(start_msg("m3"))
        a1 = b.send(turn_msg([], 1))
        a2 = b.send(turn_msg([], 1, warning={"reason": "illegal", "rejected": a1["action"]}))
        assert a2["action"] != a1["action"]          # rejected answer is never resent
    finally:
        b.close()


def test_prep_verifies_simulator_per_variant(tmp_path):
    msg = {"type": "prep", "game_id": "tic_tac_toe", "game_name": "T", "seconds": 600, "llm": None,
           "variants": [{"label": "3x3", "rules": "TIC-TAC-TOE 3x3 grid, columns A-C rows 1-3. Connect 3 marks in a row.",
                         "sample_turn": ttt_sample(list("XO.X....O"))},
                        {"label": "no sample", "rules": "TIC-TAC-TOE 3x3 grid, columns A-C rows 1-3."}]}
    res = hooks.run_prep(msg, memory_dir=str(tmp_path))
    sim = res["by_label"]["3x3"]["simulator"]
    assert os.path.basename(sim["path"]) in ("simulator.py", "simulator_0.py") and sim["has_chance"] is False
    assert sim["verified"] is True, sim            # bld's grid template has parse() since #20
    assert res["by_label"]["3x3"]["classification"]["has_hidden_information"] is False
    ns = res["by_label"]["no sample"]["simulator"]   # no sample_turn (or, with older prep, no own simulator): never verified
    assert ns["verified"] is False and ("sample" in ns["reason"] or "first variant" in ns["reason"]), ns
    with open(sim["path"], "w", encoding="utf-8") as f:   # a simulator without parse() stays unverified
        f.write(TTT_SIM.split("def parse")[0])
    by = {k: {"family": v["family"]} for k, v in res["by_label"].items()}
    hooks._verify_simulators(msg, by, str(tmp_path), time.monotonic())
    assert by["3x3"]["simulator"]["verified"] is False and "parse" in by["3x3"]["simulator"]["reason"]


def test_search_strategy_end_to_end_from_cold_memory(tmp_path):
    """A cold container: no prep message, artifacts (with a verified simulator) come from /memory; the router picks
    think_ahead/search and the decision log says alpha-beta."""
    rules = "TIC-TAC-TOE - 3x3 classic. Cells A1..C3."
    sim = tmp_path / "simulator.py"
    sim.write_text(TTT_SIM, encoding="utf-8")
    art = {"label": "3x3", "family": "grid_board", "classification": {"has_hidden_information": False, "is_simultaneous": False},
           "simulator": {"path": str(sim), "verified": True, "has_chance": False, "calibration": {"transitions_per_sec": 40000.0}},
           "chat_bank": ["Your move."], "forbidden_terms": []}
    memory.save_json(os.path.join(memory.game_dir("tic_tac_toe", rules, str(tmp_path)), "artifacts.json"), art)
    b = Bot(tmp_path, '{"a": "", "c": "x"}')
    try:
        r = b.send({"type": "start", "match_id": "c1", "game_index": 1, "game_id": "tic_tac_toe", "variant": {"label": "3x3"},
                    "rules": rules, "seat": 0, "llm": LLM})
        assert r["type"] == "ready"
        s = ttt_sample(list("XX.OO...."))
        a = b.send({"type": "turn", "game_index": 1, "turn": 5, "observation": s["observation"],
                    "legal_actions": s["legal_actions"], "seconds": 20, "chat": []})
        assert a["action"] == "C1" and a["chat"]
    finally:
        err = b.close()
    rec = [json.loads(l[9:]) for l in err.splitlines() if l.startswith("decision ")][-1]
    assert rec["strategy"] == "search" and rec["tool"] == "alpha-beta" and rec["source"] == "tool"
    assert "perfect information, simulator verified, deterministic" in rec["reason"]


def test_cut_off_reply_is_used_only_if_it_holds_a_complete_json_object():
    def llm_with(content, finish):
        l = LLMClient({"api_key": "k", "base_url": "http://x/v1", "model": "haiku"})
        resp = NS(choices=[NS(message=NS(content=content), finish_reason=finish)], usage=None)
        l._client = NS(chat=NS(completions=NS(create=lambda **kw: resp)))
        return l

    assert llm_with('{"a": "B2", "c": "hi"} then it kept talking and was cut', "length").ask_json("s", "u") == {"a": "B2", "c": "hi"}
    l = llm_with('I think the best move is {"a": "B', "length")
    assert l.ask_json("s", "u") is None and l.last_error == "empty_or_cut_off"
    assert llm_with('{"a": "B2", "c": "hi"}', "stop").ask_json("s", "u") == {"a": "B2", "c": "hi"}


def test_dice_push_routes_to_bluff():
    r = registry.route("PIG rules", {"family": "dice_push"})
    assert r.strategy.name == "bluff"
    assert r.family == "bluff"


def test_turn_state_opponent_field(tmp_path):
    ts = TurnState("g1", "rules", {}, 0, "obs", ["A1"], 1, None, [], opponent="team-beta")
    assert ts.opponent == "team-beta"

    b = Bot(tmp_path, '{"a": "guess 50", "c": "hi"}')
    try:
        b.send(prep_msg())
        s = start_msg("m1")
        s["opponent"] = "team-beta"
        r = b.send(s)
        assert r["type"] == "ready"
        a = b.send(turn_msg([], 1))
        assert a["action"]
    finally:
        b.close()


def test_validate_prevents_repeats_across_numeric_formats():
    art = {"grammar": {"kind": "numeric_range", "numeric_min": 1, "numeric_max": 100, "numeric_prefix": "guess "}}
    # bare "54" in previous rejects "guess 54"
    assert validate.validate("guess 54", None, art, previous=["54"]) is None
    # "guess 54" in previous rejects bare "54"
    assert validate.validate("54", None, art, previous=["guess 54"]) is None
    # untried "guess 55" is valid
    assert validate.validate("guess 55", None, art, previous=["54"]) == "guess 55"

    # unused_numeric avoids numbers in avoid even if prefix differs
    for _ in range(20):
        n = fallback.unused_numeric(art, avoid=["54", "guess 55"])
        assert n not in ("guess 54", "guess 55", "54", "55")


def test_hooks_exposes_tools_in_artifacts():
    vd = {
        "label": "test_game",
        "classification": {"family": "deduction"},
        "grammar": {"kind": "discrete", "discrete_actions": ["pass"]},
        "tools": [{"type": "function", "function": {"name": "test_tool"}}],
        "tools_prompt": "test_tool(): a helper tool",
    }
    art = map_engine_variant(vd)
    assert art["tools"] == [{"type": "function", "function": {"name": "test_tool"}}]
    assert "test_tool(): a helper tool" in art["tools_prompt"]


def test_wordle_grammar_and_validation():
    from prep.action_parser import parse_action_grammar
    rules = (
        "WORDLE RULES\n"
        "Guess the secret 5-letter word in 6 tries.\n"
        "Feedback is given as green, yellow, grey.\n\n"
        "ACTION FORMAT: Send a 5-letter English word, e.g. 'crane', 'slate'."
    )
    grammar = parse_action_grammar(rules)
    assert grammar.kind == "word"
    assert grammar.word_length == 5
    assert "crane" in grammar.examples or "slate" in grammar.examples

    art = {"grammar": grammar.to_dict(), "family": "deduction", "action_format": {"kind": "word", "examples": grammar.examples}}
    # Valid 5-letter guesses
    assert validate.validate("crane", None, art) == "crane"
    assert validate.validate("AUDIO", None, art) == "audio"
    assert validate.validate("  slate  ", None, art) == "slate"
    # Invalid guesses (wrong length, numbers)
    assert validate.validate("cat", None, art) == "pass" or validate.validate("cat", None, art) is None
    assert validate.validate("toolongword", None, art) is None

    # Never repeat rejected move
    assert validate.validate("crane", None, art, rejected="crane") is None
    assert validate.validate(" Crane ", None, art, rejected="crane") is None

    # Fallback produces valid non-rejected 5-letter word
    w1 = fallback.fallback_action(None, art, rejected="pass")
    assert w1 != "pass"
    assert len(w1) == 5
    w2 = fallback.fallback_action(None, art, rejected=w1, avoid_also=[w1])
    assert w2 != w1
    assert len(w2) == 5


def test_main_circuit_breaker_on_warning_rejection(tmp_path):
    # If the stub LLM stubborn-repeats the rejected move on a warning,
    # main.py must intercept it and send an alternative action.
    b = Bot(tmp_path, '{"a": "pass", "c": "chat"}')
    try:
        b.send(prep_msg())
        b.send(start_msg("m1"))
        # First turn: model outputs "pass" (or fallback)
        t1 = b.send(turn_msg([], 1))
        # Now send warning saying "pass" was rejected
        warn = {"rejected": t1["action"], "reason": "invalid action format"}
        t2 = b.send(turn_msg([], 2, warning=warn))
        # The bot MUST NOT re-send the rejected action!
        assert t2["action"] != warn["rejected"]
        assert fallback.norm(t2["action"]) != fallback.norm(warn["rejected"])
    finally:
        b.close()


def test_generic_prompt_includes_rules_when_legal_actions_null():
    from core.generic import STRATEGY as generic
    state = TurnState(
        game_id="wordle_test",
        rules="Wordle rules: guess 5-letter words only.",
        variant={},
        seat=0,
        observation="Guess 1: -----",
        legal_actions=None,
        turn=2,
        warning={"rejected": "slate", "reason": "not in word list"},
        opponent_chat=[],
        artifacts={"action_format": {"examples": ["crane"]}},
        my_actions=["slate"],
    )
    prompt = generic._prompt(state, state.artifacts)
    assert "Wordle rules: guess 5-letter words only." in prompt
    assert "CRITICAL WARNING" in prompt
    assert "slate" in prompt


def test_multi_length_word_grammar_and_fallback():
    from prep.action_parser import parse_action_grammar
    # 4-letter word game
    rules_4 = "Word game: guess the secret four-letter word.\nACTION FORMAT: 'play', 'game', 'word'."
    g4 = parse_action_grammar(rules_4)
    assert g4.kind == "word" and g4.word_length == 4
    art4 = {"grammar": g4.to_dict(), "family": "deduction"}
    assert validate.validate("play", None, art4) == "play"
    assert validate.validate("crane", None, art4) is None
    w4 = fallback.fallback_action(None, art4)
    assert len(w4) == 4

    # 6-letter word game
    rules_6 = "Word game: guess the 6-letter word.\nACTION FORMAT: 'planet', 'stream'."
    g6 = parse_action_grammar(rules_6)
    assert g6.kind == "word" and g6.word_length == 6
    art6 = {"grammar": g6.to_dict(), "family": "deduction"}
    assert validate.validate("planet", None, art6) == "planet"
    assert validate.validate("game", None, art6) is None
    w6 = fallback.fallback_action(None, art6)
    assert len(w6) == 6

    # 7-letter word game
    rules_7 = "Word game: seven-letter secret word.\nACTION FORMAT: 'balance', 'playing'."
    g7 = parse_action_grammar(rules_7)
    assert g7.kind == "word" and g7.word_length == 7
    art7 = {"grammar": g7.to_dict(), "family": "deduction"}
    assert validate.validate("freedom", None, art7) == "freedom"
    w7 = fallback.fallback_action(None, art7)
    assert len(w7) == 7


def test_generic_uses_assist_certain_move_with_zero_model_calls():
    from core.generic import STRATEGY as generic
    # Board with immediate winning move at C3
    board = "You are X.\n  A B C\n1 X O .\n2 . X .\n3 . O .\nYour move."
    legal = ["C1", "A2", "C2", "A3", "C3"]
    rules = "Tic-tac-toe on a 3x3 board. Get three in a row to win. You are X."
    art = {"family": "generic"}
    state = TurnState("ttt_test", rules, {}, 0, board, legal, 3, None, [], art, time.monotonic() + 10.0, None)
    decision = generic.decide(state)
    assert decision.action == "C3"
    assert decision.source == "strategy"
    assert "facts_used" in decision.info
    assert "assist_source" in decision.info
    assert decision.info["assist_source"] == "tool"


def test_end_to_end_generic_assist_certain_move(tmp_path):
    b = Bot(tmp_path, '{"a": "C1", "c": "chat"}')
    rules = "Tic-tac-toe on a 3x3 board. Get three in a row to win. You are X."
    try:
        p = {"type": "prep", "game_id": "simple_grid", "game_name": "SimpleGrid", "seconds": 60, "llm": LLM,
             "variants": [{"label": "v1", "rules": rules, "sample_turn": None}]}
        b.send(p)
        b.send({"type": "start", "match_id": "m1", "game_index": 1, "game_id": "simple_grid",
                "variant": {"label": "v1"}, "rules": rules, "seat": 0, "llm": LLM})
        board = "You are X.\n  A B C\n1 X O .\n2 . X .\n3 . O .\nYour move."
        legal = ["C1", "A2", "C2", "A3", "C3"]
        m = {"type": "turn", "game_index": 1, "turn": 1, "observation": board, "legal_actions": legal, "seconds": 20, "chat": []}
        t = b.send(m)
        # Even though stub says "C1", precompute certain move C3 overrides with 0 model calls!
        assert t["action"] == "C3"
    finally:
        b.close()



