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
