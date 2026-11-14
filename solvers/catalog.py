"""Toolbox catalog: one registry, one dispatcher, one result format (TOOLS_PLAN.md, issue #34).

Harness use:   catalog.call("binary_search_next", {...}, deadline)
Haiku use:     catalog.openai_tools() -> `tools` of a chat.completions request; run the tool calls
               the model returns through catalog.call(name, arguments_json_string).

call() never raises and never prints to stdout (rule 5.1). Tools take plain data and return a dict;
an optional "explain" key in that dict is lifted into the envelope.
"""
import json
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Callable, Optional

from solvers.schema import validate

MAX_RESULT_BYTES = 4096
MAX_ARGS_BYTES = 65536
GRACE_S = 0.05  # how long after the deadline call() waits for a tool that ignores it


class ToolError(Exception):
    """Raise from a tool for a bad-input or no-answer condition; the message goes to the caller as is."""


@dataclass(frozen=True)
class ToolSpec:
    name: str                  # snake_case, unique, e.g. "binary_search_next"
    summary: str               # one line: when to use it (shown to Haiku)
    params: dict               # JSON Schema (type object) for the arguments
    fn: Callable               # fn(args: dict, deadline: float) -> dict
    families: tuple = ("any",)  # e.g. ("guessing",) or ("any",)
    model_callable: bool = True  # True if inputs are plain JSON a model can fill in
    max_ms: int = 2000         # default time budget for one call


_REGISTRY: dict = {}


def register(spec: ToolSpec) -> None:
    if not isinstance(spec, ToolSpec):
        raise TypeError("register() needs a ToolSpec")
    if spec.name in _REGISTRY:
        raise ValueError("tool already registered: %s" % spec.name)
    _REGISTRY[spec.name] = spec


def list_tools(family: Optional[str] = None, model_callable: Optional[bool] = None) -> list:
    out = []
    for spec in _REGISTRY.values():
        if family is not None and family not in spec.families and "any" not in spec.families:
            continue
        if model_callable is not None and spec.model_callable != model_callable:
            continue
        out.append(spec)
    return out


def openai_tools(names: Optional[list] = None) -> list:
    """OpenAI `tools` entries for model-callable tools (all of them, or only those in `names`)."""
    out = []
    for spec in _REGISTRY.values():
        if not spec.model_callable or (names is not None and spec.name not in names):
            continue
        out.append({"type": "function",
                    "function": {"name": spec.name, "description": spec.summary,
                                 "parameters": spec.params}})
    return out


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _fail(name, error, t0) -> dict:
    return {"ok": False, "tool": name, "error": str(error)[:300], "ms": _ms(t0)}


def _bound_result(result: dict) -> dict:
    """Keep the JSON of `result` within MAX_RESULT_BYTES; an oversized result becomes a stub."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) <= MAX_RESULT_BYTES:
        return json.loads(text)
    return {"truncated": True, "size_bytes": len(text.encode("utf-8")), "preview": text[:1500]}


def call(name: str, args, deadline: Optional[float] = None) -> dict:
    """Run one tool. Always returns {ok, tool, result|error, explain?, ms}; never raises."""
    t0 = time.monotonic()
    try:
        spec = _REGISTRY.get(name)
        if spec is None:
            return _fail(name, "unknown tool", t0)
        if isinstance(args, (str, bytes)):
            if len(args) > MAX_ARGS_BYTES:
                return _fail(name, "arguments too large", t0)
            args = json.loads(args) if args.strip() else {}
        if not isinstance(args, dict):
            return _fail(name, "arguments must be a JSON object", t0)
        if len(json.dumps(args, default=str)) > MAX_ARGS_BYTES:
            return _fail(name, "arguments too large", t0)
        err = validate(args, spec.params)
        if err:
            return _fail(name, err, t0)
        if deadline is None:
            deadline = t0 + spec.max_ms / 1000.0
        if deadline <= t0:
            return _fail(name, "no time left before the deadline", t0)

        box: dict = {}

        def run():
            try:
                box["result"] = spec.fn(args, deadline)
            except BaseException as exc:  # noqa: BLE001 - a tool must never take the harness down
                box["exc"] = exc
                if not isinstance(exc, ToolError):
                    print("[solvers] tool %s failed:\n%s" % (name, traceback.format_exc()), file=sys.stderr)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(max(0.0, deadline - time.monotonic()) + GRACE_S)
        if worker.is_alive():
            return _fail(name, "timeout: tool did not finish before the deadline", t0)
        if "exc" in box:
            exc = box["exc"]
            if isinstance(exc, ToolError):
                return _fail(name, exc, t0)
            return _fail(name, "internal error: %s: %s" % (type(exc).__name__, exc), t0)
        result = box.get("result")
        if not isinstance(result, dict):
            return _fail(name, "internal error: tool returned no dict", t0)
        result = dict(result)
        explain = str(result.pop("explain", ""))[:300]
        return {"ok": True, "tool": name, "result": _bound_result(result), "explain": explain, "ms": _ms(t0)}
    except BaseException as exc:  # noqa: BLE001 - last line of defence, call() must not raise
        return _fail(name, "%s: %s" % (type(exc).__name__, exc), t0)
