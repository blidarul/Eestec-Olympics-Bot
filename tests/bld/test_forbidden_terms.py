"""B3: forbidden terms from the rules by code, with variants; filter on ready chat, turn chat and the action (6.8, 6.9)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import main  # noqa: E402
from core import actionfmt, forbidden, hooks  # noqa: E402

QA = ('GUARDED Q&A. DOCUMENT: "The city of Lumen has 40 bridges." Answer ONLY from the document; if it does not say, answer exactly "unknown". '
      'SPEECH RULE: you must never say the word "harbor" in your chat; a player who does loses the game.\n'
      'ACTION FORMAT: "answer <text>" (free text, legal list not sent).')


@pytest.mark.parametrize("rules,expect", [
    (QA, ["harbor"]),
    ("You may not mention the word bananas or apples in chat.", ["bananas", "apples"]),
    ("Forbidden words: gold, silver; copper", ["gold", "silver", "copper"]),
    ("Banned topics are politics and religion.", ["politics", "religion"]),
    ("Never use the words 'cheese' and 'milk'. You lose the game if you do.", ["cheese", "milk"]),
    ("Do not say \"red alert\" ever. Chat is free otherwise.", ["red alert"]),
    ("Forbidden subject: the weather", ["weather"]),
    ("Players take turns. Say anything you like in chat.", []),
    ('Answer exactly "unknown" if the document does not say. ACTION FORMAT: "answer <text>"', []),
])
def test_extract(rules, expect):
    got = [t.lower() for t in forbidden.extract_terms(rules)]
    for e in expect:
        assert e in got, (rules, got)
    if not expect:
        assert got == []


def test_variants_and_matching():
    terms = forbidden.merge(QA, [])
    assert "harbor" in terms and "Harbor" in terms and "harbors" in terms and "h4rbor" in terms
    for bad in ["harbor", "Harbor", "HARBOR", "h4rbor", "harbors", "h a r b o r", "h-a-r-b-o-r", "hárbor", "the harbor.", "H4RB0R"]:
        assert forbidden.contains(bad, terms), bad
    for ok in ["I like the arbor day", "answer unknown", "40 bridges", "Your move.", "carbon"]:
        assert forbidden.contains(ok, terms) is None, ok
    short = forbidden.merge("never say the word \"ass\"", [])
    assert forbidden.contains("a class of its own", short) is None and forbidden.contains("ass", short)


def test_merge_with_model_terms():
    terms = forbidden.merge(QA, ["anchor"])
    assert forbidden.contains("an anchor", terms) and forbidden.contains("harbor", terms)


def test_prep_attaches_terms_without_model():
    art = hooks._default_artifacts()
    assert art["forbidden_terms"] == []
    hooks.attach_forbidden_terms(art, QA)
    assert "harbor" in art["forbidden_terms"] and art["forbidden_base"] == ["harbor"]
    assert any(t in art["forbidden_terms"] for t in ("Harbor", "harbors", "h4rbor"))


def test_safe_action_template_value_not_cut():
    terms = forbidden.merge(QA, [])
    fmt = actionfmt.parse_template(QA)
    out = forbidden.safe_action("answer harbor", terms, fmt=fmt)
    assert out == "answer unknown" and out != "answer " and forbidden.contains(out, terms) is None
    legal = ["say harbor", "say sea"]
    assert forbidden.safe_action("say harbor", terms, legal=legal) == "say sea"


class FakeWk:
    def __init__(self, action, chat):
        self.action, self.chat = action, chat

    def ask(self, req, timeout):
        return {"action": self.action, "chat": self.chat, "source": "model", "model_error": None}


def _turn(monkeypatch, art, action, chat, legal=None):
    sent = []
    monkeypatch.setattr(main.protocol, "send", lambda m: sent.append(m))
    monkeypatch.setattr(main, "log_decision", lambda *a, **k: None)
    main.STATE.update({"artifacts": art, "game": {"rules": QA, "game_id": "g"}, "my_actions": [], "prev_obs": "", "llm": None})
    main.on_turn({"type": "turn", "turn": 1, "observation": "Q1", "legal_actions": legal, "seconds": 20, "chat": []}, FakeWk(action, chat))
    return sent[-1]


def _art():
    art = hooks._default_artifacts()
    art["action_format"] = actionfmt.parse_template(QA) | {"examples": []}
    hooks.attach_forbidden_terms(art, QA)
    return art


@pytest.mark.parametrize("word", ["harbor", "Harbor", "h4rbor", "harbors"])
def test_turn_nothing_forbidden_reaches_the_arena(monkeypatch, word):
    out = _turn(monkeypatch, _art(), f"answer {word}", f"I love the {word}!")
    terms = _art()["forbidden_terms"]
    assert forbidden.contains(out["action"], terms) is None and out["action"].startswith("answer ")
    assert forbidden.contains(out["chat"], terms) is None and out["chat"].strip() and len(out["chat"]) <= 200


def test_ready_chat_filtered_and_never_empty(monkeypatch):
    sent = []
    monkeypatch.setattr(main.protocol, "send", lambda m: sent.append(m))

    class Wk:
        def ask(self, req, timeout):
            if req["kind"] == "load":
                return {"artifacts": {}}
            return {"line": "Welcome to the h4rbor!"}
    main.STATE.update({"prep": None, "llm": None})
    main.on_start({"type": "start", "rules": QA, "game_id": "g", "match_id": "m", "variant": {"label": "v"}}, Wk())
    terms = forbidden.merge(QA, [])
    assert forbidden.contains(sent[-1]["chat"], terms) is None and sent[-1]["chat"].strip()
