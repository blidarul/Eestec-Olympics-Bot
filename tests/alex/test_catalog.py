"""catalog + schema: validation, call() never raises, deadline, truncation, OpenAI export."""
import itertools
import json
import time

import pytest

from solvers import catalog
from solvers.catalog import ToolError, ToolSpec
from solvers.schema import validate

SCHEMA = {"type": "object", "required": ["n"], "additionalProperties": False,
          "properties": {"n": {"type": "integer", "minimum": 0, "maximum": 10},
                         "mode": {"type": "string", "enum": ["a", "b"], "maxLength": 1},
                         "xs": {"type": "array", "maxItems": 2, "items": {"type": "number"}}}}


def test_schema_accepts_good_and_rejects_bad():
    assert validate({"n": 3, "mode": "a", "xs": [1, 2.5]}, SCHEMA) is None
    assert "missing required field 'n'" in validate({}, SCHEMA)
    assert "type integer" in validate({"n": "3"}, SCHEMA)
    assert "type integer" in validate({"n": True}, SCHEMA)          # bool is not an int
    assert "type integer" in validate({"n": 1.5}, SCHEMA)
    assert ">= 0" in validate({"n": -1}, SCHEMA)
    assert "<= 10" in validate({"n": 11}, SCHEMA)
    assert "one of" in validate({"n": 1, "mode": "z"}, SCHEMA)
    assert "more than 2 items" in validate({"n": 1, "xs": [1, 2, 3]}, SCHEMA)
    assert "args.xs[1]" in validate({"n": 1, "xs": [1, "x"]}, SCHEMA)
    assert "unknown field" in validate({"n": 1, "zzz": 1}, SCHEMA)
    assert validate([1], SCHEMA) is not None
    assert validate({"n": 1, "xs": [float("nan")]}, SCHEMA) is not None


def _spec(name, fn, **kw):
    return ToolSpec(name=name, summary="test tool", params={"type": "object", "properties": {"n": {"type": "integer"}}},
                    fn=fn, families=kw.pop("families", ("any",)), model_callable=kw.pop("model_callable", True), **kw)


@pytest.fixture
def reg():
    added = []

    def add(spec):
        catalog.register(spec)
        added.append(spec.name)
        return spec.name

    yield add
    for n in added:
        catalog._REGISTRY.pop(n, None)


def test_call_ok_unknown_and_string_args(reg):
    name = reg(_spec("t_echo", lambda a, d: {"got": a.get("n"), "explain": "echoed"}))
    r = catalog.call(name, {"n": 4})
    assert r["ok"] and r["result"] == {"got": 4} and r["explain"] == "echoed" and isinstance(r["ms"], int)
    assert catalog.call(name, '{"n": 5}')["result"] == {"got": 5}
    assert catalog.call(name, "")["result"] == {"got": None}
    assert catalog.call("nope", {})["ok"] is False
    assert catalog.call(name, "{bad json")["ok"] is False
    assert catalog.call(name, "[1,2]")["ok"] is False
    assert catalog.call(name, {"n": "x"})["ok"] is False
    assert catalog.call(name, 12345)["ok"] is False
    assert catalog.call(name, {"n": 1, "pad": "x" * 70000})["ok"] is False


def test_call_never_raises(reg):
    def boom(a, d):
        raise RuntimeError("kaboom")

    def toolerr(a, d):
        raise ToolError("lo must be <= hi")

    def exits(a, d):
        raise SystemExit(3)

    n1 = reg(_spec("t_boom", boom))
    n2 = reg(_spec("t_toolerr", toolerr))
    n3 = reg(_spec("t_exit", exits))
    n4 = reg(_spec("t_nodict", lambda a, d: 42))
    r = catalog.call(n1, {})
    assert r["ok"] is False and "kaboom" in r["error"]
    r2 = catalog.call(n2, {})
    assert (r2["ok"], r2["tool"], r2["error"]) == (False, n2, "lo must be <= hi")
    assert catalog.call(n3, {})["ok"] is False
    assert catalog.call(n4, {})["ok"] is False
    assert catalog.call(n1, None)["ok"] is False


def test_deadline_is_a_hard_backstop(reg):
    stop = []

    def spin(a, d):  # ignores its deadline
        while not stop:
            time.sleep(0.005)
        return {}

    name = reg(_spec("t_spin", spin, max_ms=100))
    t0 = time.monotonic()
    r = catalog.call(name, {})
    stop.append(1)
    assert r["ok"] is False and "timeout" in r["error"]
    assert time.monotonic() - t0 < 1.0
    # explicit deadline wins over max_ms
    stop.clear()
    t0 = time.monotonic()
    r = catalog.call(name, {}, deadline=time.monotonic() + 0.05)
    stop.append(1)
    assert r["ok"] is False and time.monotonic() - t0 < 0.5
    # a deadline already in the past
    assert catalog.call(name, {}, deadline=time.monotonic() - 1)["ok"] is False


def test_tool_gets_deadline_and_can_return_partial(reg):
    seen = {}

    def fn(a, d):
        seen["d"] = d
        return {"partial": True}

    name = reg(_spec("t_deadline", fn))
    dl = time.monotonic() + 5
    assert catalog.call(name, {}, deadline=dl)["ok"] and seen["d"] == dl


def test_oversized_result_is_truncated(reg):
    name = reg(_spec("t_big", lambda a, d: {"blob": "x" * 20000}))
    r = catalog.call(name, {})
    assert r["ok"] and r["result"]["truncated"] is True
    assert len(json.dumps(r["result"])) < catalog.MAX_RESULT_BYTES


def test_unserialisable_result_does_not_raise(reg):
    name = reg(_spec("t_obj", lambda a, d: {"s": {1, 2}, "o": object()}))
    assert catalog.call(name, {})["ok"] is True


def test_register_rejects_duplicates_and_non_specs(reg):
    reg(_spec("t_dup", lambda a, d: {}))
    with pytest.raises(ValueError):
        catalog.register(_spec("t_dup", lambda a, d: {}))
    with pytest.raises(TypeError):
        catalog.register({"name": "x"})


def test_list_tools_filters(reg):
    reg(_spec("t_g", lambda a, d: {}, families=("guessing",)))
    reg(_spec("t_h", lambda a, d: {}, families=("any",), model_callable=False))
    names = lambda **kw: {s.name for s in catalog.list_tools(**kw)}  # noqa: E731
    assert "t_g" in names(family="guessing") and "t_g" not in names(family="bluff")
    assert "t_h" in names(family="bluff")                    # "any" matches every family
    assert "t_h" not in names(model_callable=True) and "t_h" in names(model_callable=False)


def test_openai_tools_format(reg):
    reg(_spec("t_mc", lambda a, d: {}))
    reg(_spec("t_hidden", lambda a, d: {}, model_callable=False))
    tools = catalog.openai_tools()
    json.dumps(tools)  # serialisable
    for t in tools:
        assert t["type"] == "function"
        f = t["function"]
        assert set(f) == {"name", "description", "parameters"}
        assert f["parameters"]["type"] == "object" and f["description"]
    names = {t["function"]["name"] for t in tools}
    assert "t_mc" in names and "t_hidden" not in names
    assert {t["function"]["name"] for t in catalog.openai_tools(["t_mc", "t_hidden"])} == {"t_mc"}
    assert catalog.openai_tools([]) == []
    # every model-callable registered tool is exported
    assert names == {s.name for s in catalog.list_tools(model_callable=True)}


def test_package_registers_basic_tools():
    import solvers  # noqa: F401
    have = {s.name for s in catalog.list_tools()}
    assert {"binary_search_next", "bisect_predicate_points", "dice_sum_distribution"} <= have
