"""End-to-end through main.py (stub LLM, no network): guessing safety net, deduce via prep, ready_line, decision log."""
import json
import os
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from tests.alex.games import GUESS_MODEL_CODE, guess_obs, guess_rules  # noqa: E402

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

    def send(self, msg, answer=True):
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline()) if answer else None

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
    from chat.pipeline import ready_line
    b = Bot(tmp_path, '{"a": "", "c": "x"}')
    try:
        r = b.send(start_msg("seed-7"))
    finally:
        b.close()
    assert r["type"] == "ready" and r["chat"] and r["chat"] == ready_line(RULES, [], "seed-7")


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
    import time
    from core import hooks
    from tests.alex.games import TTT_SIM, ttt_sample
    msg = {"type": "prep", "game_id": "tic_tac_toe", "game_name": "T", "seconds": 600, "llm": None,
           "variants": [{"label": "3x3", "rules": "TIC-TAC-TOE 3x3 grid, columns A-C rows 1-3. Connect 3 marks in a row.",
                         "sample_turn": ttt_sample(list("XO.X....O"))},
                        {"label": "no sample", "rules": "TIC-TAC-TOE 3x3 grid, columns A-C rows 1-3."}]}
    res = hooks.run_prep(msg, memory_dir=str(tmp_path))
    sim = res["by_label"]["3x3"]["simulator"]
    assert sim["path"].endswith("simulator.py") and sim["has_chance"] is False
    assert sim["verified"] is True, sim            # bld's grid template has parse() since #20
    assert res["by_label"]["3x3"]["classification"]["has_hidden_information"] is False
    assert res["by_label"]["no sample"]["simulator"]["verified"] is False and "first variant" in res["by_label"]["no sample"]["simulator"]["reason"]
    with open(sim["path"], "w", encoding="utf-8") as f:   # a simulator without parse() stays unverified
        f.write(TTT_SIM.split("def parse")[0])
    by = {k: {"family": v["family"]} for k, v in res["by_label"].items()}
    hooks._verify_simulators(msg, by, str(tmp_path), time.monotonic())
    assert by["3x3"]["simulator"]["verified"] is False and "parse" in by["3x3"]["simulator"]["reason"]


def test_search_strategy_end_to_end_from_cold_memory(tmp_path):
    """A cold container: no prep message, artifacts (with a verified simulator) come from /memory; the router picks
    think_ahead/search and the decision log says alpha-beta."""
    from core import memory
    from tests.alex.games import TTT_SIM, ttt_sample
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
