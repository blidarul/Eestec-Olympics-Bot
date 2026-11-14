"""End-to-end acceptance test for new unknown games.
Verifies that:
1. A completely new game with no hardcoded fallback (ElementalDuel) requires LLM preparation.
2. The harness accepts the new game, synthesizes prep artifacts and action format via LLM,
   and successfully executes turns with valid legal actions.
3. Without LLM prep, default emergency fallbacks ('pass', 'ready', '0', 'A1') are rejected by the game.
Owned by agent `bld`.
"""
import json
import os
import sys
import pytest

ARENA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "arena-lite")
if ARENA_DIR not in sys.path:
    sys.path.insert(0, ARENA_DIR)

from core import fallback, validate
from arena.practice.elemental_duel import ElementalDuel, SPELLS


def test_new_game_has_no_fallback_without_llm():
    game = ElementalDuel(ElementalDuel.variants()[0], seed=42)
    rules = game.rules()
    obs = game.observation(0)
    
    # 1. Game provides no legal actions list
    assert game.legal_actions(0) is None

    # 2. Game rejects all generic emergency fallback strings
    for bad_move in ["pass", "ready", "0", "1", "A1", "yes", "play", "stop", "go", "10 10 10"]:
        assert game.normalize(0, bad_move) is None, f"Game unexpectedly accepted generic move {bad_move}"

    # 3. An empty artifact dictionary produces generic fallback actions that fail game normalization
    empty_art = {"family": "generic"}
    fb = fallback.fallback_action(
        None,
        empty_art,
        avoid_also=["CAST MEDITATE"],  # Base example avoided
        observation=obs,
        rules=rules,
    )
    # The generic fallback will be a generic string (e.g. 'pass'), which is strictly illegal in ElementalDuel
    norm = game.normalize(0, fb)
    assert norm is None, f"Expected generic fallback '{fb}' to be rejected by the new game"


def test_harness_accepts_new_game_with_llm_prep():
    game = ElementalDuel(ElementalDuel.variants()[0], seed=123)
    rules = game.rules()
    obs = game.observation(0)

    # Simulated LLM prep output for the new game
    llm_prep_result = {
        "family": "generic",
        "playbook": "Cast spells according to available mana. Use ICE_BARRIER to block FIREBALL, LIGHTNING for heavy damage.",
        "action_format": {
            "regex": r"^CAST\s+(MEDITATE|FIREBALL|ICE_BARRIER|LIGHTNING|GROUND_SPIKE|SIPHON)$",
            "examples": ["CAST MEDITATE", "CAST FIREBALL", "CAST ICE_BARRIER"],
        },
        "fallback_policy": {
            "prefer": ["CAST MEDITATE", "CAST FIREBALL", "CAST ICE_BARRIER", "CAST LIGHTNING", "CAST GROUND_SPIKE", "CAST SIPHON"],
            "avoid": [],
        },
        "chat_bank": ["May the elements favor the swift.", "Well cast."],
        "forbidden_terms": [],
    }

    art = {
        "family": "generic",
        "action_format": llm_prep_result["action_format"],
        "fallback_policy": llm_prep_result["fallback_policy"],
        "chat_bank": llm_prep_result["chat_bank"],
        "forbidden_terms": llm_prep_result["forbidden_terms"],
    }

    # 1. Validator accepts prepped legal spells
    for spell in SPELLS:
        action = f"CAST {spell}"
        v = validate.validate(action, None, art, observation=obs, rules=rules)
        assert v == action
        assert game.normalize(0, v) == action

    # 2. Fallback action from prepped artifacts selects from the LLM preferred actions
    fb = fallback.fallback_action(
        None,
        art,
        avoid_also=["CAST MEDITATE"],
        observation=obs,
        rules=rules,
    )
    assert fb in llm_prep_result["fallback_policy"]["prefer"]
    assert game.normalize(0, fb) is not None, f"Action '{fb}' was rejected by game!"


def test_elemental_duel_simulation_rounds():
    """Verify that simulated turns between two wizards play through cleanly."""
    game = ElementalDuel(ElementalDuel.variants()[0], seed=999)
    assert not game.is_over()

    # Round 1: Both meditate (gain 20 mana + 10 round regen)
    game.apply({0: "CAST MEDITATE", 1: "CAST MEDITATE"})
    assert game.round_no == 2
    assert game.hp[0] == 100 and game.hp[1] == 100

    # Round 2: Wizard 0 casts FIREBALL (costs 15, deals 25), Wizard 1 casts ICE_BARRIER (costs 10, blocks 30)
    game.apply({0: "CAST FIREBALL", 1: "CAST ICE_BARRIER"})
    # Fireball was blocked by ice barrier!
    assert game.round_no == 3
    assert game.hp[1] == 100  # took 0 damage

    # Round 3: Wizard 0 casts LIGHTNING (costs 20, deals 35), Wizard 1 casts MEDITATE
    game.apply({0: "CAST LIGHTNING", 1: "CAST MEDITATE"})
    assert game.hp[1] == 65  # took 35 damage
    assert not game.is_over()


def test_elemental_duel_through_harness_prep_and_turns(tmp_path):
    """End-to-end test running main.py as a subprocess with LLM prep and turns on ElementalDuel."""
    import subprocess
    import threading

    game = ElementalDuel(ElementalDuel.variants()[0], seed=777)
    rules = game.rules()

    llm_reply = json.dumps({
        "family": "generic",
        "playbook": "Cast spells according to available mana.",
        "action_format": {
            "regex": r"^CAST\s+(MEDITATE|FIREBALL|ICE_BARRIER|LIGHTNING|GROUND_SPIKE|SIPHON)$",
            "examples": ["CAST MEDITATE", "CAST FIREBALL"],
        },
        "fallback_policy": {
            "prefer": ["CAST MEDITATE", "CAST FIREBALL"],
            "avoid": [],
        },
        "a": "CAST MEDITATE",
        "c": "May the elements guide us.",
    })

    env = dict(os.environ, BOT_STUB_LLM="1", BOT_STUB_LLM_REPLY=llm_reply, MEMORY_DIR=str(tmp_path))
    p = subprocess.Popen([sys.executable, "-u", "main.py"], cwd=os.path.dirname(ARENA_DIR),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    err_lines = []
    reader = threading.Thread(target=lambda: [err_lines.append(l) for l in p.stderr], daemon=True)
    reader.start()

    try:
        # 1. Prep message
        prep_req = {
            "type": "prep",
            "game_id": "elemental_duel",
            "game_name": "Elemental Duel",
            "seconds": 10,
            "llm": {"api_key": "k", "base_url": "http://x/v1", "model": "haiku"},
            "variants": [{"label": "Standard", "rules": rules, "sample_turn": None}],
        }
        p.stdin.write(json.dumps(prep_req) + "\n")
        p.stdin.flush()
        prep_resp = json.loads(p.stdout.readline())
        assert prep_resp["type"] == "ready"

        # 2. Start message
        start_req = {
            "type": "start",
            "match_id": "m_elem_1",
            "game_index": 1,
            "game_id": "elemental_duel",
            "variant": {"label": "Standard"},
            "rules": rules,
            "seat": 0,
            "llm": {"api_key": "k", "base_url": "http://x/v1", "model": "haiku"},
        }
        p.stdin.write(json.dumps(start_req) + "\n")
        p.stdin.flush()
        start_resp = json.loads(p.stdout.readline())
        assert start_resp["type"] == "ready"

        # 3. Turn message
        obs = game.observation(0)
        turn_req = {
            "type": "turn",
            "game_index": 1,
            "turn": 1,
            "observation": obs,
            "legal_actions": None,
            "seconds": 20,
            "chat": [],
        }
        p.stdin.write(json.dumps(turn_req) + "\n")
        p.stdin.flush()
        turn_resp = json.loads(p.stdout.readline())
        assert turn_resp["type"] == "action"
        action = turn_resp["action"]
        
        # Verify the action produced by the harness is 100% accepted by the game
        norm = game.normalize(0, action)
        assert norm is not None, f"Harness action {action!r} was rejected by ElementalDuel!"
        assert norm == "CAST MEDITATE"

    finally:
        p.kill()

