"""Layer 2, phase L3: let the model call catalog tools for one decision, inside a deadline.

run_tool_loop(llm_call, system, user, tool_names, deadline, max_rounds=2, native=True) -> LoopResult

Library only. Never raises: any failure returns final=None (plus the trace) so the caller uses its fallback.
The caller validates the final action. Opponent chat is never an argument here: the caller keeps it inside
`user` as an untrusted block. Model output is parsed as JSON only, never eval'd.

llm_call(messages, tools_or_None, timeout_s, max_tokens) -> {"content", "tool_calls": [{id,name,arguments}], "error"}
"""
import json
import sys
import threading
import time
from dataclasses import dataclass, field

import solvers  # noqa: F401  (registers the tools)
from solvers import catalog

MAX_CALLS_PER_ROUND = 3
RESULT_CHARS = 1024
CALL_TIMEOUT_S = 8.0
MIN_FINAL_S = 1.5       # below this remaining time: give up (final=None)
MIN_ROUND_S = 3.0       # below this remaining time: no more tool rounds, ask for the final directly
MAX_TOKENS = 400
FINAL_ASK = ('Now answer with ONLY one JSON object {"a": "<action>", "c": "<chat, max 200 chars>"} '
             "and nothing else.")


@dataclass
class LoopResult:
    final: dict = None
    trace: list = field(default_factory=list)
    mode: str = "none"
    model_calls: int = 0
    ms: int = 0


def _log(msg):
    try:
        print("[toolloop] " + msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def _first_json(text):
    """First JSON object in text (code fences and extra prose tolerated), else None."""
    if not isinstance(text, str):
        return None
    dec = json.JSONDecoder()
    i = text.find("{")
    tries = 0
    while i != -1 and tries < 20:
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:  # noqa: BLE001
            pass
        i = text.find("{", i + 1)
        tries += 1
    return None


def _final_from(obj):
    """Normalise a parsed object to {"a": str, "c": str} or None."""
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get("final"), dict):
        obj = obj["final"]
    a = obj.get("a", obj.get("action"))
    if a is None or isinstance(a, (dict, list)):
        return None
    c = obj.get("c", obj.get("chat", ""))
    return {"a": str(a).strip(), "c": (c if isinstance(c, str) else str(c))[:200]}


def _trim(result):
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        text = str(result)
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS - 12] + "...[cut]"


def _ask(llm_call, messages, tools, timeout, max_tokens):
    """Call the model in a daemon thread so a hung stub cannot outlive the deadline. Returns a response dict."""
    box = {}

    def run():
        try:
            box["r"] = llm_call(messages, tools, timeout, max_tokens)
        except BaseException as exc:  # noqa: BLE001
            box["r"] = {"content": None, "tool_calls": [], "error": "%s: %s" % (type(exc).__name__, exc)}

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(max(0.05, timeout))
    r = box.get("r")
    if t.is_alive() or not isinstance(r, dict):
        return {"content": None, "tool_calls": [], "error": "model call timed out or returned junk"}
    tcs = r.get("tool_calls")
    return {"content": r.get("content") if isinstance(r.get("content"), str) else None,
            "tool_calls": [c for c in tcs if isinstance(c, dict)] if isinstance(tcs, list) else [],
            "error": r.get("error") if isinstance(r.get("error"), str) else None}


def _tool_lines(names):
    out = []
    for spec in catalog.list_tools(model_callable=True):
        if spec.name in names:
            props = ", ".join(sorted((spec.params or {}).get("properties", {}) or {}))
            out.append("- %s(%s): %s" % (spec.name, props, spec.summary[:120]))
    return "\n".join(out)


def run_tool_loop(llm_call, system, user, tool_names, deadline, max_rounds=2, native=True):
    t0 = time.monotonic()
    res = LoopResult()
    try:
        _run(res, llm_call, str(system), str(user), list(tool_names or []), float(deadline),
             max(0, min(int(max_rounds), 4)), bool(native))
    except BaseException as exc:  # noqa: BLE001
        _log("failed: %s: %s" % (type(exc).__name__, exc))
        res.final = None
    res.ms = int((time.monotonic() - t0) * 1000)
    return res


def _exec_tool(res, rnd, name, args, deadline):
    t = time.monotonic()
    if not isinstance(name, str) or name not in {s.name for s in catalog.list_tools(model_callable=True)}:
        out = {"ok": False, "tool": str(name)[:60], "error": "unknown tool"}
    else:
        out = catalog.call(name, args, min(deadline - MIN_FINAL_S, t + 2.0))
    res.trace.append({"round": rnd, "tool": str(name)[:60], "args": _trim(args)[:200], "ok": bool(out.get("ok")),
                      "ms": int((time.monotonic() - t) * 1000)})
    return out


def _run(res, llm_call, system, user, tool_names, deadline, max_rounds, native):
    allowed = [n for n in tool_names if isinstance(n, str)]
    tools = catalog.openai_tools(allowed) if allowed else []
    use_native = native and bool(tools)
    use_text = (not native) and bool(allowed)
    res.mode = "native" if use_native else ("text" if use_text else "none")
    sys_text = system
    if use_text:
        sys_text += ("\nTools you may call (at most %d calls per turn):\n%s\nTo call one reply ONLY "
                     '{"tool": "<name>", "args": {...}}. To answer reply ONLY {"final": {"a": "<action>", "c": "<chat>"}}.'
                     % (MAX_CALLS_PER_ROUND, _tool_lines(allowed)))
    messages = [{"role": "system", "content": sys_text}, {"role": "user", "content": user}]

    def remaining():
        return deadline - time.monotonic()

    def call(tools_arg):
        rem = remaining()
        if rem < MIN_FINAL_S:
            return None
        res.model_calls += 1
        return _ask(llm_call, messages, tools_arg, min(CALL_TIMEOUT_S, rem - MIN_FINAL_S), MAX_TOKENS)

    rounds = max_rounds if (use_native or use_text) else 0
    for rnd in range(1, rounds + 1):
        if remaining() < MIN_ROUND_S:
            break
        r = call(tools if use_native else None)
        if r is None:
            return
        if r["error"] and not r["tool_calls"] and not r["content"]:
            _log("round %d error: %s" % (rnd, r["error"]))
            if use_native and rnd == 1:  # gateway may reject tools: retry once in text mode
                use_native, use_text, res.mode = False, True, "text"
                messages[0]["content"] = system + (
                    "\nTools you may call (at most %d calls per turn):\n%s\nTo call one reply ONLY "
                    '{"tool": "<name>", "args": {...}}. To answer reply ONLY {"final": {"a": "<action>", "c": "<chat>"}}.'
                    % (MAX_CALLS_PER_ROUND, _tool_lines(allowed)))
                continue
            break
        if use_native and r["tool_calls"]:
            calls = r["tool_calls"][:MAX_CALLS_PER_ROUND]
            messages.append({"role": "assistant", "content": r["content"] or None, "tool_calls": [
                {"id": str(c.get("id") or "call_%d_%d" % (rnd, i)), "type": "function",
                 "function": {"name": str(c.get("name")), "arguments": str(c.get("arguments") or "{}")}}
                for i, c in enumerate(calls)]})
            for i, c in enumerate(calls):
                out = _exec_tool(res, rnd, c.get("name"), c.get("arguments") or "{}", deadline)
                messages.append({"role": "tool", "tool_call_id": str(c.get("id") or "call_%d_%d" % (rnd, i)),
                                 "content": _trim(out)})
            continue
        obj = _first_json(r["content"])
        fin = _final_from(obj)
        if fin is not None and not (isinstance(obj, dict) and "tool" in obj and "final" not in obj
                                    and "a" not in obj):
            res.final = fin
            return
        if use_text and isinstance(obj, dict) and "tool" in obj:
            name = obj.get("tool")
            out = _exec_tool(res, rnd, name, obj.get("args") if isinstance(obj.get("args"), dict) else {}, deadline)
            messages.append({"role": "assistant", "content": (r["content"] or "")[:500]})
            messages.append({"role": "user", "content": "Tool result (data): " + _trim(out)})
            continue
        break  # model gave neither a tool call nor a usable final: ask for the final below

    # final call, tools disabled
    if remaining() < MIN_FINAL_S:
        return
    messages.append({"role": "user", "content": FINAL_ASK})
    r = call(None)
    if r is None:
        return
    res.final = _final_from(_first_json(r["content"]))


def make_openai_llm_call(client, model):
    """Adapter for an openai.OpenAI client (thinking disabled, rule 7.3). openai is imported lazily."""
    def llm_call(messages, tools, timeout_s, max_tokens):
        try:
            kw = {"model": model, "messages": messages, "max_tokens": max_tokens, "timeout": timeout_s,
                  "extra_body": {"thinking": {"type": "disabled"}}}
            if tools:
                kw["tools"] = tools
            resp = client.chat.completions.create(**kw)
            msg = resp.choices[0].message
            tcs = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                   for tc in (getattr(msg, "tool_calls", None) or [])]
            return {"content": msg.content, "tool_calls": tcs, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"content": None, "tool_calls": [], "error": "%s: %s" % (type(exc).__name__, exc)}
    return llm_call
