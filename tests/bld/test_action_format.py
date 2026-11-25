"""B1: strict-format fallback (rules 8.1, 9.4): the rules' ACTION FORMAT becomes a template, a regex and placeholder ranges."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import main  # noqa: E402
from core import actionfmt, fallback, hooks  # noqa: E402

CLAIM = ('CLAIM GRID. A 12x12 grid, rows R1-R12, columns C1-C12. Players alternate claiming one UNCLAIMED cell.\n'
         'ACTION FORMAT (strict, legal list is NOT sent): exactly "CLAIM R<row>-C<col>", e.g. "CLAIM R12-C12". Anything else is illegal.')
QA = 'GUARDED Q&A. ... \nACTION FORMAT: "answer <text>" (free text, legal list not sent).'
DROP = 'ACTION FORMAT: "drop <column 1-7>", e.g. "drop 4". You receive the legal moves every turn.'
BARE = "Action format: move <from> <to> where both are numbers between 1 and 9"


def test_parse_claim():
    f = actionfmt.parse_template(CLAIM)
    assert f["template"] == "CLAIM R<row>-C<col>"
    assert [(p["type"], p["min"], p["max"]) for p in f["placeholders"]] == [("int", 1, 12), ("int", 1, 12)]
    assert re.fullmatch(f["regex"], "claim r3-c12", re.I)
    assert actionfmt.matches(f, "CLAIM R12-C12") and not actionfmt.matches(f, "CLAIM R13-C1")
    assert not actionfmt.matches(f, "F6") and not actionfmt.matches(f, "guess 50") and not actionfmt.matches(f, "pass")


def test_parse_text_and_inline_range_and_none():
    q = actionfmt.parse_template(QA)
    assert q["placeholders"][0]["type"] == "text" and actionfmt.matches(q, "answer ada fenn")
    assert not actionfmt.matches(q, "answer") and not actionfmt.matches(q, "pass")
    d = actionfmt.parse_template(DROP)
    assert d["placeholders"][0]["max"] == 7 and not actionfmt.matches(d, "drop 8")
    assert actionfmt.parse_template("Pick a number 1-100. Format: a number") is None
    assert actionfmt.parse_template('ACTION FORMAT: "A", "B" or "C".') is None  # literals only: nothing to enforce


def test_fill_never_generic_and_unused():
    f = actionfmt.parse_template(CLAIM)
    obs = "You are seat 0. Claimed: " + ", ".join(f"R{r}-C{c}=opp" for r in range(1, 13) for c in range(1, 13) if (r, c) != (5, 7))
    for _ in range(20):
        assert actionfmt.fill(f, [], obs) == "CLAIM R5-C7" or actionfmt.fill(f, [], obs) is not None
    assert actionfmt.fill(f, ["CLAIM R5-C7"], "") != "CLAIM R5-C7"
    assert actionfmt.fill(actionfmt.parse_template(QA), ["answer unknown"], "") == "answer unknown"  # free text may repeat


def test_fallback_uses_template_not_generic():
    art = {"action_format": actionfmt.parse_template(CLAIM) | {"examples": []}}
    seen = ["CLAIM R12-C12"]
    for _ in range(30):
        a = fallback.fallback_action(None, art, rejected="CLAIM R2-C2", avoid_also=seen)
        assert actionfmt.matches(art["action_format"], a) and a not in seen and a != "CLAIM R2-C2"
        seen.append(a)
    art2 = {"action_format": actionfmt.parse_template(QA)}
    assert fallback.fallback_action(None, art2) == "answer unknown"


def test_warning_reason_refines():
    art = {"action_format": actionfmt.parse_template(DROP)}
    f = actionfmt.from_artifacts(art, {"reason": "illegal move: column must be between 2 and 5"})
    assert f["placeholders"][0]["min"] == 2 and not actionfmt.matches(f, "drop 6")
    f2 = actionfmt.from_artifacts({}, {"reason": 'bad action; expected "take <heap> <count>"'})
    assert f2 and actionfmt.matches(f2, "take 1 2")


def test_attach_to_artifacts():
    art = hooks._default_artifacts()
    hooks.attach_action_template(art, CLAIM)
    af = art["action_format"]
    assert af["template"] and af["regex"] and af["placeholders"] and af["examples"] == []


class FakeWk:
    def __init__(self, action):
        self.action = action

    def ask(self, req, timeout):
        return {"action": self.action, "chat": "hi", "source": "model", "model_error": None}


def _turn(monkeypatch, art, action, warning=None, obs="obs", mine=()):
    sent = []
    monkeypatch.setattr(main.protocol, "send", lambda m: sent.append(m))
    monkeypatch.setattr(main, "log_decision", lambda *a, **k: None)
    main.STATE.update({"artifacts": art, "game": {"rules": CLAIM, "game_id": "g"}, "my_actions": list(mine), "prev_obs": "", "llm": None})
    msg = {"type": "turn", "turn": 1, "observation": obs, "legal_actions": None, "seconds": 20, "chat": []}
    if warning:
        msg["warning"] = warning
    main.on_turn(msg, FakeWk(action))
    return sent[-1]["action"]


def test_main_gate_replaces_bad_model_answers(monkeypatch):
    art = {"action_format": actionfmt.parse_template(CLAIM)}
    for bad in ["F6", "guess 50", "pass", "CLAIM R99-C1", "", "I would like to claim R3-C3 please"]:
        out = _turn(monkeypatch, art, bad)
        assert actionfmt.matches(art["action_format"], out), (bad, out)
    assert _turn(monkeypatch, art, "CLAIM R3-C4") == "CLAIM R3-C4"
    assert _turn(monkeypatch, art, "claim r3-c4.") == "claim r3-c4" or actionfmt.matches(art["action_format"], "CLAIM R3-C4")


def test_main_after_warning_never_second_bad(monkeypatch):
    art = {"action_format": actionfmt.parse_template(CLAIM)}
    w = {"count": 1, "max": 2, "reason": "illegal move: 'F6'", "rejected": "F6"}
    for bad in ["F6", "G6", "pass", "CLAIM R3-C3"]:
        out = _turn(monkeypatch, art, bad, warning=w, mine=["F6"])
        assert actionfmt.matches(art["action_format"], out) and out != "F6"


def test_ensure_template_from_rules_when_prep_missing():
    art = {}
    main.ensure_action_template(art, {"rules": CLAIM})
    assert actionfmt.has_template(art["action_format"])


def test_parse_bulls_and_cows_action_format():
    rules = """ACTION FORMAT
    guess <code>      exactly 4 characters from 0123456789
The word "guess" is optional. Examples: "guess 0123".
"""
    f = actionfmt.parse_template(rules)
    assert f is not None
    assert f["template"] == "guess <code>"
    assert f["placeholders"][0]["type"] == "code"
    assert f["placeholders"][0]["length"] == 4
    val = actionfmt.fill(f, set(), "")
    assert val.startswith("guess ")
    code = val.split()[1]
    assert len(code) == 4
    assert all(c in "0123456789" for c in code)
    assert "exactly" not in val


def test_word_template_uppercase():
    rules = """WORD GUESSING
ACTION FORMAT: "guess <WORD>" where WORD is a 5-letter uppercase word.
"""
    f = actionfmt.parse_template(rules)
    assert f is not None
    assert f["placeholders"][0]["type"] == "word"
    assert f["placeholders"][0]["case"] == "upper"
    val = actionfmt.fill(f, set(), "")
    assert val.startswith("guess ")
    w = val.split()[1]
    assert w.isupper()
    assert len(w) == 5


def test_flexible_header_and_rules_scan():
    rules_actions = """BATTLE ARENA
ACTIONS:
claim <row>-<col>
"""
    f1 = actionfmt.parse_template(rules_actions)
    assert f1 is not None
    assert "claim" in f1["template"]

    rules_commands = """NAVAL WAR
### COMMANDS:
fire <col><row>
"""
    f2 = actionfmt.parse_template(rules_commands)
    assert f2 is not None
    assert "fire" in f2["template"]

    rules_inlined = """AUCTION HOUSE
Players alternate bidding. Each round you must send "bid <amount>" to stay in.
e.g. "bid 50".
"""
    f3 = actionfmt.parse_template(rules_inlined)
    assert f3 is not None
    assert f3["template"] == "bid <amount>"
    assert f3["placeholders"][0]["type"] == "int"

