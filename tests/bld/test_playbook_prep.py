"""Tests for Strategic LLM Playbook Synthesizer in prep phase (Issue #47).
Tests schema validation, rule-based baselines, fake/mock gateway synthesis,
turn prompt injection, and prep artifact reuse (0 model calls).
Owned by agent `bld`.
"""
from __future__ import annotations

import os
import tempfile
import pytest

from prep.playbook import (
    synthesize_playbook,
    format_playbook_for_prompt,
    _generate_rule_based_baseline,
)
from prep.engine import PrepEngine
from core.generic import Generic
from strategies.base import TurnState


class MockLLM:
    def __init__(self, reply: dict | None = None, available: bool = True):
        self.reply = reply
        self._available = available
        self.call_count = 0

    def available(self) -> bool:
        return self._available

    def over_budget(self) -> bool:
        return False

    def ask_json(self, system: str, user: str, **kw) -> dict | None:
        self.call_count += 1
        return self.reply


def test_rule_based_baseline_extraction():
    rules = "TIC-TAC-TOE - 3x3 grid. 2 players, alternating turns. First to make 3 in a row wins. Target: 10."
    baseline = _generate_rule_based_baseline(rules)
    assert isinstance(baseline, dict)
    assert "invariants" in baseline
    assert "traps" in baseline
    assert "opening_guidelines" in baseline
    assert "endgame_goals" in baseline
    assert any("10" in g for g in baseline["endgame_goals"])


def test_mock_llm_playbook_synthesis():
    mock_reply = {
        "invariants": ["Center cell control is critical", "Corners offer multiple winning forks"],
        "traps": ["Never allow opponent an unblocked 2-in-a-row", "Avoid playing edges on move 1"],
        "opening_guidelines": ["Take center cell on opening move", "Respond to center with corner"],
        "endgame_goals": ["Secure 3 in a row or force draw"],
    }
    llm = MockLLM(reply=mock_reply)
    res = synthesize_playbook("Tic Tac Toe rules", llm_client=llm)
    assert llm.call_count == 1
    assert res["invariants"] == mock_reply["invariants"]
    assert res["traps"] == mock_reply["traps"]


def test_format_playbook_for_prompt():
    pb = {
        "invariants": ["Inv 1", "Inv 2"],
        "traps": ["Trap 1"],
        "opening_guidelines": ["Guideline 1"],
        "endgame_goals": ["Goal 1"],
    }
    fmt = format_playbook_for_prompt(pb, max_len=300)
    assert "- Invariants: Inv 1; Inv 2" in fmt
    assert "- Traps to Avoid: Trap 1" in fmt
    assert "- Guidelines: Guideline 1" in fmt
    assert "- Goals: Goal 1" in fmt
    assert len(fmt) <= 300


def test_prompt_injection_in_generic_strategy():
    strat = Generic()
    state = TurnState(
        game_id="g1",
        rules="Some rules",
        variant={},
        seat=0,
        observation="Observation text",
        legal_actions=["A1", "B2"],
        turn=1,
        warning=None,
        opponent_chat=[],
        artifacts={
            "playbook_structured": {
                "invariants": ["Center cell is paramount"],
                "traps": ["Do not give away double attacks"],
                "opening_guidelines": ["Take center"],
                "endgame_goals": ["Reach victory"],
            }
        },
    )
    prompt = strat._prompt(state, state.artifacts)
    assert "Strategy Guidelines:" in prompt
    assert "Center cell is paramount" in prompt
    assert "Do not give away double attacks" in prompt


def test_prep_engine_synthesizes_and_saves_playbook():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PrepEngine(memory_dir=tmpdir)
        mock_llm = MockLLM(
            reply={
                "invariants": ["Secret word is 5 letters"],
                "traps": ["Do not repeat eliminated letters"],
                "opening_guidelines": ["Start with high vowel word"],
                "endgame_goals": ["Guess secret word"],
            }
        )
        engine.llm = mock_llm

        prep_msg = {
            "game_id": "test_wordle_pb",
            "game_name": "Wordle Duel",
            "seconds": 60.0,
            "variants": [
                {
                    "label": "5 letters",
                    "rules": "WORDLE - Guess 5-letter word in 6 guesses.",
                    "sample_turn": {"observation": "Round 1", "legal_actions": None},
                }
            ],
        }

        res = engine.run_prep(prep_msg)
        assert res.get("type") == "ready"
        assert mock_llm.call_count == 1

        game_dir = os.path.join(tmpdir, "test_wordle_pb")
        playbook_file = os.path.join(game_dir, "playbook.json")
        assert os.path.exists(playbook_file)

        # Acceptance 3: 0 extra model calls if playbook.json already exists
        res2 = engine.run_prep(prep_msg)
        assert res2.get("type") == "ready"
        assert mock_llm.call_count == 1  # Still 1, 0 extra calls made!
