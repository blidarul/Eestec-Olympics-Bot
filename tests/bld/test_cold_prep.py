"""G3 cold container, family label for dice games, G4 prep reuse (X3)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alex", "audit"))
import msgs  # noqa: E402

from core import hooks, registry  # noqa: E402


def _start(gid):
    prep, start, turn, g = msgs.build(gid)
    return start, turn


def test_cold_pig_uses_search_not_generic(tmp_path):
    start, turn = _start("pig")
    art = hooks.run_cold(start, 60.0, memory_dir=str(tmp_path))
    assert art["family"] != "bluff" and art["simulator"]["path"] and not art["simulator"]["verified"]   # no sample turn yet
    assert art["forbidden_terms"] is not None and art["action_format"]
    first = turn(1)
    art = hooks.cold_verify(art, start, first, memory_dir=str(tmp_path))                              # first real turn
    assert art["simulator"]["verified"], art["simulator"]
    r = registry.route(start["rules"], art)
    assert r.strategy.name == "search", r.reason
    # saved like a warm container's artifacts: the next load finds them
    assert hooks.load_artifacts(start["game_id"], start["rules"], str(tmp_path)).get("family") == art["family"]


def test_pig_family_is_not_bluff(tmp_path):
    start, _ = _start("pig")
    assert hooks.run_cold(start, 60.0, memory_dir=str(tmp_path))["family"] == "chance"


def test_cold_guess_number_routes_to_deduce(tmp_path):
    start, _ = _start("guess_number")
    art = hooks.run_cold(start, 60.0, memory_dir=str(tmp_path))
    assert registry.route(start["rules"], art).strategy.name == "deduce"


def test_cold_container_end_to_end_pig_uses_search(tmp_path):
    from tests.bld.test_core_p4 import Bot
    start, turn = _start("pig")
    start["study_seconds"] = 120
    b = Bot(tmp_path, '{"a": "roll", "c": "ok"}')          # no prep message: empty /memory
    try:
        assert b.send(start)["type"] == "ready"
        for n in (1, 2):
            a = b.send(turn(n))
            assert a["type"] == "action" and a["action"] in ("roll", "hold") and a["chat"]
    finally:
        err = b.close()
    dec = [l for l in err.splitlines() if l.startswith("decision ")]
    assert dec and all('"strategy": "search"' in l for l in dec), dec


def test_second_prep_makes_no_model_calls(tmp_path, monkeypatch):
    calls = []

    class Fake:
        def __init__(self, info=None): self.info = info or {}
        def available(self): return True
        def over_budget(self): return False
        def ask(self, *a, **k): calls.append(1); return None
        def ask_json(self, *a, **k): calls.append(1); return None

    monkeypatch.setattr(hooks, "LLM", Fake)
    prep, _, _, _ = msgs.build("guess_number")
    first = hooks.run_prep(prep, memory_dir=str(tmp_path))
    n1 = len(calls)
    second = hooks.run_prep(prep, memory_dir=str(tmp_path))
    assert n1 > 0 and len(calls) == n1, (n1, len(calls))
    assert second["by_label"].keys() == first["by_label"].keys() and second["first"] == first["first"]
    assert all(a["family"] and a["prep_complete"] for a in second["by_label"].values())


def test_partial_or_cold_artifacts_are_not_reused(tmp_path):
    prep, start, _, _ = msgs.build("pig")
    cold = hooks.run_cold(start, 60.0, memory_dir=str(tmp_path))
    assert cold["cold_prep"] and hooks._reuse_prep(prep, prep["variants"], str(tmp_path)) is None   # a cold file is code-only
    assert hooks._reuse_prep(prep, prep["variants"], str(tmp_path / "empty")) is None
