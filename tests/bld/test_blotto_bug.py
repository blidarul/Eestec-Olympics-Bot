"""Tests for Colonel Blotto validation, fallback, and solver integration.
Owned by agent `bld`.
"""
import pytest
from core import validate, fallback
from optimization.blotto_solver import generate_blotto_allocations, select_blotto_action


def test_blotto_validation_all_variants():
    # Variant 1: 100 soldiers, 5 fields
    obs1 = "COLONEL BLOTTO - 100 soldiers, 5 equal fields. Round 1/5.\nYour soldiers this round: 100.\nEnter your allocation of 100 soldiers across 5 fields."
    art1 = {"family": "blotto", "action_format": {"examples": ["20 20 20 20 20"]}}
    assert validate.validate("20 20 20 20 20", None, art1, observation=obs1) == "20 20 20 20 20"
    assert validate.validate("30 20 20 15 15", None, art1, observation=obs1) == "30 20 20 15 15"
    # Action not summing to 100 gets scaled to 100
    scaled1 = validate.validate("10 10 10 10 10", None, art1, observation=obs1)
    assert scaled1 is not None
    assert sum(int(x) for x in scaled1.split()) == 100
    assert len(scaled1.split()) == 5

    # Variant 2: 60 soldiers, 6 fields (CRITICAL: should NOT be matched to "20 20 20 20 20")
    obs2 = "COLONEL BLOTTO - 60 soldiers, 6 fields. Round 1/5.\nYour soldiers this round: 60.\nEnter your allocation of 60 soldiers across 6 fields."
    art2 = {"family": "blotto", "action_format": {"examples": ["10 10 10 10 10 10"]}}
    v2 = validate.validate("10 10 10 10 10 10", None, art2, observation=obs2)
    assert v2 == "10 10 10 10 10 10"
    assert sum(int(x) for x in v2.split()) == 60
    assert len(v2.split()) == 6

    # Variant 3: 30 soldiers, 3 fields reserves (CRITICAL: must not use 100 soldiers)
    obs3 = "COLONEL BLOTTO - Reserves. Round 1/5.\nYour soldiers this round: 30.\nEnter your allocation of 30 soldiers across 3 fields.\nReserves: you 30, opponent 30."
    art3 = {"family": "blotto", "action_format": {"examples": ["10 10 10"]}}
    v3 = validate.validate("10 10 10", None, art3, observation=obs3)
    assert v3 == "10 10 10"
    assert sum(int(x) for x in v3.split()) == 30
    assert len(v3.split()) == 3


def test_blotto_fallback_never_pass():
    obs_reserves = "COLONEL BLOTTO - Reserves. Round 2/5.\nYour soldiers this round: 30.\nEnter your allocation of 30 soldiers across 3 fields."
    rules_reserves = "COLONEL BLOTTO. 3 fields. 30 soldiers. Reserves."
    
    # Even if avoid contains the base allocation, it must NOT return "pass"
    fb = fallback.fallback_action(
        None,
        {"family": "blotto"},
        avoid_also=["10 10 10"],
        observation=obs_reserves,
        rules=rules_reserves,
    )
    assert fb != "pass"
    assert fb != "ready"
    tokens = [int(x) for x in fb.split()]
    assert len(tokens) == 3
    assert sum(tokens) == 30


def test_select_blotto_action_portfolios():
    # 5 fields, 100 soldiers
    port5 = generate_blotto_allocations(soldiers=100, fields=5, count=20)
    act5 = select_blotto_action(port5, available_soldiers=100, fields=5)
    toks5 = [int(x) for x in act5.split()]
    assert len(toks5) == 5
    assert sum(toks5) == 100

    # 3 fields, 30 soldiers (reserves) with mismatching portfolio (e.g. 5 fields)
    act3 = select_blotto_action(port5, available_soldiers=30, fields=3)
    toks3 = [int(x) for x in act3.split()]
    assert len(toks3) == 3
    assert sum(toks3) == 30


def test_blotto_repetition_allowed_in_previous():
    obs = "COLONEL BLOTTO - 100 soldiers, 5 equal fields. Round 2/5.\nYour soldiers this round: 100.\nBattlefield values: F1=1, F2=1, F3=1, F4=1, F5=1"
    art = {"family": "matrix_simultaneous", "action_format": {"examples": ["20 20 20 20 20"]}}
    prev = ["20 20 20 20 20"]
    # In blotto, repeating the previous allocation across rounds is legal unless rejected by a warning
    res = validate.validate("20 20 20 20 20", None, art, rejected=None, previous=prev, observation=obs)
    assert res == "20 20 20 20 20"

    # But if rejected by warning, it must return None
    res_rej = validate.validate("20 20 20 20 20", None, art, rejected="20 20 20 20 20", previous=prev, observation=obs)
    assert res_rej is None


def test_blotto_field_count_and_reserves_repair():
    obs = "COLONEL BLOTTO - Reserves: +30 per round, 3 fields. Round 2/5.\nYour soldiers this round: 45.\nBattlefield values: F1=1, F2=1, F3=1"
    art = {"family": "read_opponent", "action_format": {"examples": ["10 10 10"]}}
    
    # 2 fields given instead of 3: repair pads to 3 fields and scales
    v_repair = validate.validate("20 25", None, art, observation=obs)
    assert v_repair is not None
    toks = [int(x) for x in v_repair.split()]
    assert len(toks) == 3
    assert sum(toks) <= 45

    # Allocation exceeding available soldiers in reserves: scales down to <= 45
    v_over = validate.validate("30 30 30", None, art, observation=obs)
    assert v_over is not None
    toks_over = [int(x) for x in v_over.split()]
    assert len(toks_over) == 3
    assert sum(toks_over) <= 45
