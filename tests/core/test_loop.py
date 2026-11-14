import json
import os
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core import fallback, worker  # noqa: E402


def run_bot(msgs, env=None, wait=0.0):
    e = dict(os.environ, **(env or {}))
    p = subprocess.Popen([sys.executable, "-u", "main.py"], cwd=ROOT, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=e)
    outs = []
    for m in msgs:
        p.stdin.write((m if isinstance(m, str) else json.dumps(m)) + "\n")
        p.stdin.flush()
    time.sleep(wait)
    return p, outs


START = {"type": "start", "game_id": "g", "rules": "r", "seat": 0, "variant": {}, "llm": {"api_key": "k"}}
TURN = {"type": "turn", "turn": 1, "observation": "o", "legal_actions": ["a", "b"], "seconds": 20, "chat": []}


def finish(p):
    out, err = p.communicate(timeout=30)
    return [json.loads(l) for l in out.splitlines()], err


def test_silent_until_message():
    p = subprocess.Popen([sys.executable, "-u", "main.py"], cwd=ROOT, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    assert p.poll() is None
    out, _ = p.communicate("", timeout=15)  # EOF ends it
    assert out == ""


def test_full_flow_and_garbage_and_match_over():
    p, _ = run_bot(["not json", "[1]", {"type": "prep", "game_id": "g", "variants": []}, START, TURN,
                    {"type": "end", "result": "win", "reason": "x"}, TURN, {"type": "shutdown"}])
    out, _ = finish(p)
    assert [o["type"] for o in out] == ["ready", "ready", "action", "action"]
    assert out[1]["chat"]
    assert all(o["action"] in ("a", "b") and o["chat"] for o in out[2:])


def test_null_legal_actions_never_empty():
    p, _ = run_bot([START, dict(TURN, legal_actions=None), {"type": "shutdown"}])
    out, _ = finish(p)
    assert out[1]["action"] and out[1]["chat"]


def _sleeper(conn):
    conn.recv()
    time.sleep(60)


def _raiser(conn):
    conn.recv()
    conn.send(None)


def _garbage(conn):
    while True:
        conn.recv()
        conn.send({"action": 12, "chat": None})


def test_worker_timeout_restart_and_crash():
    wk = worker.WorkerClient(target=_sleeper)
    t = time.monotonic()
    assert wk.ask({"state": {}}, 1.0) is None
    assert time.monotonic() - t < 3
    wk.stop()
    wk = worker.WorkerClient()  # real worker answers after restart
    ans = wk.ask({"state": dict(game_id="g", rules="", variant={}, seat=0, observation="", legal_actions=["x"],
                                turn=1, warning=None, opponent_chat=[], artifacts={}), "budget": 3}, 20)
    assert ans["action"] == "x"
    wk._proc.kill()
    wk._proc.join()
    ans = wk.ask({"state": dict(game_id="g", rules="", variant={}, seat=0, observation="", legal_actions=["y"],
                                turn=1, warning=None, opponent_chat=[], artifacts={}), "budget": 3}, 20)
    assert ans["action"] == "y"  # killed worker: next turn still answered
    wk.stop()


def test_raising_worker_returns_none():
    wk = worker.WorkerClient(target=_raiser)
    assert wk.ask({"state": {}}, 5) is None
    wk.stop()


def test_garbage_from_strategy_gives_legal_move(monkeypatch):
    import main
    monkeypatch.setattr(main.protocol, "send", lambda o: sent.append(o))
    sent = []
    wk = worker.WorkerClient(target=_garbage)
    main.STATE["game"] = START
    main.on_turn(dict(TURN), wk)
    wk.stop()
    assert sent[0]["action"] in ("a", "b") and sent[0]["chat"]


def test_fallback_rungs():
    art = {"fallback_policy": {"prefer": ["b"], "avoid": ["a"]}, "chat_bank": ["hi"]}
    assert fallback.fallback_action(["a", "b"], art) == "b"
    assert fallback.fallback_action(["a", "c"], art) == "c"
    assert fallback.fallback_action(["a", "c"], {}, rejected="c") == "a"
    assert fallback.fallback_action(None, {"action_format": {"examples": ["e1"]}}) == "e1"
    assert fallback.fallback_action(None, None) == "pass"
    assert fallback.fallback_chat(art) == "hi" and fallback.fallback_chat(None)
