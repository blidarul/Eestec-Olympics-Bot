import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import generic, memory  # noqa: E402
from core.llm import LLM  # noqa: E402
from core.validate import validate  # noqa: E402
from strategies.base import TurnState  # noqa: E402
from test_p2 import START, TURN, run  # noqa: E402

FMT = {"action_format": {"regex": r"move \d \d", "examples": ["move 1 2", "move 3 4"]}}


def test_validate_list():
    legal = ["A1", "B2", "C3"]
    assert validate("B2", legal) == "B2"
    assert validate(" b2 ", legal) == "B2"
    assert validate("'c3'", legal) == "C3"
    assert validate("Z9", legal) is None
    assert validate("", legal) is None and validate(None, legal) is None
    assert validate("B2", legal, rejected="B2") is None


def test_validate_fuzzy():
    assert validate("place card number 7", ["place card number 17"]) == "place card number 17"


def test_validate_null_list():
    assert validate("move 5 6", None, FMT) == "move 5 6"
    assert validate("mov 5 6!!", None, FMT) in FMT["action_format"]["examples"]
    assert validate("", None, FMT) is None
    assert validate("anything", None, {}) == "anything"


def test_warning_second_try_uses_conservative_fallback():
    llm = LLM({"api_key": "k", "base_url": "x"})
    os.environ["STUB_LLM"] = "1"
    llm.stub = True
    os.environ["STUB_LLM_REPLY"] = '{"a":"B2","c":"hi"}'  # same as rejected
    try:
        st = TurnState("g", "r", {}, 0, "o", ["A1", "B2", "C3"], 2, {"rejected": "B2", "reason": "bad"}, [], {}, time.monotonic() + 9, llm)
        d = generic.STRATEGY.decide(st)
        assert d.action == "A1" and d.source == "fallback"
    finally:
        os.environ.pop("STUB_LLM_REPLY")
        os.environ.pop("STUB_LLM")


def test_budget_guard_no_model():
    llm = LLM({"api_key": "k", "base_url": "http://127.0.0.1:1/v1"})
    llm.spend = 0.41
    assert llm.over_budget()
    st = TurnState("g", "r", {}, 0, "o", ["A1", "B2"], 1, None, [], {}, time.monotonic() + 9, llm)
    assert generic.STRATEGY.decide(st).source == "fallback"


def test_env_fallback_and_block_wins(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://env/v1")
    monkeypatch.setenv("LLM_API_KEY", "envkey")
    monkeypatch.setenv("LLM_MODEL", "haiku")
    assert LLM(None).available() and LLM(None).info["base_url"] == "http://env/v1"
    l = LLM({"base_url": "http://block/v1", "api_key": "blockkey"})
    assert l.info["base_url"] == "http://block/v1" and l.info["api_key"] == "blockkey" and l.info["model"] == "haiku"


def test_memory_atomic_and_corrupt(tmp_path):
    d = memory.game_dir("g", "rules", str(tmp_path))
    p = os.path.join(d, "artifacts.json")
    assert memory.save_json(p, {"a": 1}) and memory.load_json(p) == {"a": 1}
    open(p, "w").write("{corrupt")
    assert memory.load_json(p, "dflt") == "dflt"
    assert memory.load_json(os.path.join(d, "nope.json")) is None
    assert memory.append_log(d, {"x": 1}) and memory.append_log(d, {"x": 2})
    assert [json.loads(l)["x"] for l in open(os.path.join(d, "log.jsonl"))] == [1, 2]


def test_null_list_bad_format_falls_back_to_example(tmp_path):
    art_dir = memory.game_dir("tic_tac_toe", START["rules"], str(tmp_path))
    memory.save_json(os.path.join(art_dir, "artifacts.json"), dict(FMT, label="3x3 classic"))
    turn = dict(TURN, legal_actions=None)
    out, _ = run([START, turn, {"type": "shutdown"}], {"STUB_LLM_REPLY": '{"a":"zzz qqq","c":"ok"}', "MEMORY_DIR": str(tmp_path)})
    assert out[1]["action"] in FMT["action_format"]["examples"]


def test_corrupt_artifacts_bot_still_plays(tmp_path):
    art_dir = memory.game_dir("tic_tac_toe", START["rules"], str(tmp_path))
    os.makedirs(art_dir)
    open(os.path.join(art_dir, "artifacts.json"), "w").write("{{{corrupt")
    out, _ = run([START, TURN, {"type": "shutdown"}], {"MEMORY_DIR": str(tmp_path)})
    assert out[1]["action"] in TURN["legal_actions"]


def test_end_writes_log(tmp_path):
    end = {"type": "end", "game_index": 1, "result": "win", "reason": "x", "match_over": False}
    out, _ = run([START, TURN, end, {"type": "shutdown"}], {"MEMORY_DIR": str(tmp_path)})
    logs = [os.path.join(r, f) for r, _, fs in os.walk(tmp_path) for f in fs if f == "log.jsonl"]
    assert logs and json.loads(open(logs[0]).readline())["result"] == "win"
