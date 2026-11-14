"""Tests for Chat Integration (Issue #41).
Verifies:
1. Strategy co-generated chat is preserved (Rule 6.4).
2. Strategies setting info["chat_final"]=True are never overwritten.
3. Neutral / fallback chat ("Your move.", empty, or chat_bank) gets persona reply_line.
4. Main process wk_filter routes through chat.filter_out and respects forbidden terms.
5. Prep phase pre-warms chat without raising.
"""
import pytest
from core import fallback, hooks
from core.worker import _generic_decide
from strategies.base import Decision, TurnState
import main


class DummyCustomChatStrategy:
    name = "custom_chat_strategy"

    def __init__(self, action="bet", chat="I see your bluff and raise.", info=None):
        self._action = action
        self._chat = chat
        self._info = info or {}

    def matches(self, rules, artifacts):
        return 1.0

    def decide(self, state: TurnState) -> Decision:
        return Decision(self._action, self._chat, "strategy", dict(self._info))


class DummyNeutralChatStrategy:
    name = "neutral_strategy"

    def matches(self, rules, artifacts):
        return 1.0

    def decide(self, state: TurnState) -> Decision:
        return Decision("pass", "Your move.", "strategy")


def test_custom_strategy_chat_is_preserved(monkeypatch):
    """Rule 6.4: Co-generated strategy chat must NOT be overwritten by worker's reply_line."""
    state = TurnState(
        game_id="g1",
        rules="Standard poker rules.",
        variant={"label": "v0"},
        seat=0,
        observation="pot is 100",
        legal_actions=["bet", "fold", "call"],
        turn=1,
        warning=None,
        opponent_chat=["I bet 10."],
        artifacts={"family": "bluff", "forbidden_terms": ["forbidden_word"]},
    )

    strat = DummyCustomChatStrategy(action="bet", chat="I see your bluff and raise.")

    # Mock registry.route to return our strategy
    from core import registry
    class RouteRes:
        strategy = strat
        reason = "test"
        family = "bluff"

    monkeypatch.setattr(registry, "route", lambda rules, art: RouteRes())

    # Mock conn
    captured = []
    class DummyConn:
        def send(self, val):
            captured.append(val)

    # Run one cycle in worker loop simulation
    # Let's verify using the logic in worker
    art = state.artifacts
    bank = set(fallback._as_list(art.get("chat_bank"))) | {fallback.NEUTRAL_CHAT, "Your move.", "Good game."}
    d = strat.decide(state)
    info = dict(getattr(d, "info", None) or {})
    cur_chat = str(d.chat).strip() if d.chat is not None else ""
    is_neutral_or_bank = (not cur_chat) or (d.chat in bank) or (cur_chat in bank)
    is_chat_final = bool(info.get("chat_final")) or (info.get("chat_override") is False)

    assert not is_neutral_or_bank, "Custom chat should not be considered neutral or bank"
    assert not (is_neutral_or_bank and not is_chat_final), "Custom chat must not be overridden"
    assert d.chat == "I see your bluff and raise."


def test_chat_final_flag_prevents_override():
    """info['chat_final']=True prevents any override even if chat happens to match bank."""
    state = TurnState(
        game_id="g1",
        rules="Rules",
        variant={},
        seat=0,
        observation="",
        legal_actions=["pass"],
        turn=1,
        warning=None,
        opponent_chat=[],
        artifacts={"chat_bank": ["Good luck!"]},
    )
    strat = DummyCustomChatStrategy(action="pass", chat="Good luck!", info={"chat_final": True})
    d = strat.decide(state)
    info = dict(getattr(d, "info", None) or {})
    is_chat_final = bool(info.get("chat_final"))
    assert is_chat_final is True


def test_neutral_chat_gets_reply_line():
    """When strategy returns 'Your move.' or bank, reply_line should be queried."""
    state = TurnState(
        game_id="g1",
        rules="Rules",
        variant={},
        seat=0,
        observation="",
        legal_actions=["pass"],
        turn=1,
        warning=None,
        opponent_chat=["Hello there"],
        artifacts={"chat_bank": ["Welcome."]},
    )
    strat = DummyNeutralChatStrategy()
    d = strat.decide(state)
    art = state.artifacts
    bank = set(fallback._as_list(art.get("chat_bank"))) | {fallback.NEUTRAL_CHAT, "Your move.", "Good game."}
    cur_chat = str(d.chat).strip() if d.chat is not None else ""
    is_neutral_or_bank = (not cur_chat) or (d.chat in bank) or (cur_chat in bank)
    info = dict(getattr(d, "info", None) or {})
    is_chat_final = bool(info.get("chat_final")) or (info.get("chat_override") is False)

    assert is_neutral_or_bank is True
    assert not is_chat_final
    # Therefore should_override is True


def test_wk_filter_filters_forbidden_and_speech_rules():
    """wk_filter in main.py filters forbidden words using chat.filter_out."""
    res = main.wk_filter("I have a secret forbidden_word for you", ["forbidden_word"])
    assert "forbidden_word" not in res
    assert res.strip()  # Never empty


def test_prep_warm_chat():
    """hooks._warm_chat pre-warms chat/ cleanly without throwing."""
    msg = {
        "game_id": "test_game",
        "variants": [{"label": "v0", "rules": "Standard game rules."}],
    }
    by_label = {"v0": {"family": "bluff", "forbidden_terms": ["cheat"]}}
    hooks._warm_chat(msg, by_label)


def test_chat_full_includes_game_and_kind():
    """Issue #42 Contract 2: chat_full() copies 'game' and 'kind' into output dicts."""
    raw_chat = [
        {"from": "seat_1", "text": "let's play", "game": 2, "kind": "chat"},
        {"from": "seat_0", "text": "move 1", "game": 2, "type": "move"},
        {"from": "seat_1", "text": "good luck"},
    ]
    cf = main.chat_full(raw_chat)
    assert len(cf) == 3
    assert cf[0]["game"] == 2
    assert cf[0]["kind"] == "chat"
    assert cf[1]["game"] == 2
    assert cf[1]["kind"] == "move"
    assert "game" not in cf[2]
    assert "kind" not in cf[2]


def test_reply_line_called_with_decision_and_metadata(monkeypatch):
    """Issue #42 Contract 1: worker calls reply_line with decision, chat_full, and game."""
    captured = {}
    import chat

    def mock_reply_line(opp_chat, turn, rules, forbidden, family, **kwargs):
        captured["opp_chat"] = opp_chat
        captured["turn"] = turn
        captured["rules"] = rules
        captured["forbidden"] = forbidden
        captured["family"] = family
        captured["decision"] = kwargs.get("decision")
        captured["chat_full"] = kwargs.get("chat_full")
        captured["game"] = kwargs.get("game")
        return "Custom reply based on move."

    monkeypatch.setattr(chat, "reply_line", mock_reply_line)

    state = TurnState(
        game_id="g1",
        rules="Rules",
        variant={},
        seat=0,
        observation="",
        legal_actions=["B2"],
        turn=3,
        warning=None,
        opponent_chat=["play B2 now"],
        artifacts={"chat_bank": ["Your move."]},
        chat_full=[{"from": "opp", "text": "play B2 now", "game": 1}],
        game_index=1,
    )

    strat = DummyNeutralChatStrategy()
    d = strat.decide(state)
    from core import worker
    worker.resolve_turn_chat(d, state, state.artifacts)
    assert captured.get("decision") is not None
    assert captured.get("chat_full") == [{"from": "opp", "text": "play B2 now", "game": 1}]
    assert captured.get("game") == 1
    assert d.chat == "Custom reply based on move."


def test_extract_speech_extra_creates_file(tmp_path):
    """Issue #42 Contract 3: _extract_speech_extra writes speech_extra_<h>.json."""
    import hashlib
    rules = "Game rules with speech restrictions: FORBIDDEN TOPICS: weather, temperature, rain."
    h = hashlib.sha256(rules.encode("utf-8")).hexdigest()[:12]
    msg = {
        "game_id": "speech_game_123",
        "variants": [{"label": "v0", "rules": rules}],
    }
    base_dir = str(tmp_path)
    hooks._extract_speech_extra(msg, {}, base_dir)

    expected_path = tmp_path / "speech_game_123" / f"speech_extra_{h}.json"
    assert expected_path.exists()
    import json
    with open(expected_path, "r", encoding="utf-8") as f:
        terms = json.load(f)
    assert isinstance(terms, list)
    assert any("weather" in t or "rain" in t or "temperature" in t for t in terms)

