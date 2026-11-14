"""Haiku client (the only hosted model allowed, 7.7) built from the latest `llm` block (7.2).

Used only inside the worker process. Every call has a timeout; empty or cut-off output -> None.
BOT_STUB_LLM=1 (BOT_* reaches the container; legacy STUB_LLM=1 still works) returns canned JSON (tests, no network).
BOT_STUB_LLM_REPLY (legacy STUB_LLM_REPLY) sets the canned reply.
"""
import json
import os
import re
import sys

PRICE_IN = 0.10 / 1e6   # 7.5
PRICE_OUT = 0.50 / 1e6
SKIP_AFTER_FAILS = 2
SKIP_TURNS = 3
BUDGET_GUARD = 0.40  # per match (9.3): above this, no more model calls


def _env(new, old, default=None):
    v = os.environ.get(new)
    return v if v is not None else os.environ.get(old, default)


def _log(*a):
    print(*a, file=sys.stderr, flush=True)


class LLM:
    def __init__(self, info: dict | None):
        self.raw = info
        self.info = dict(info) if isinstance(info, dict) else {}
        # safety net (5.12): fill gaps from the environment; the llm block always wins (7.2)
        for k, env in (("base_url", "LLM_BASE_URL"), ("api_key", "LLM_API_KEY"), ("model", "LLM_MODEL")):
            if not self.info.get(k) and os.environ.get(env):
                self.info[k] = os.environ[env]
        self.model = self.info.get("model") or "haiku"
        self.spend = 0.0
        self.fails = 0
        self.skip = 0
        self._client = None
        self.stub = _env("BOT_STUB_LLM", "STUB_LLM") == "1"
        self.last_error = None  # reason the last call of this turn produced nothing (None = ok / no call)

    def available(self) -> bool:
        if self.skip > 0:
            return False
        return self.stub or bool(self.info.get("api_key") and self.info.get("base_url"))

    def over_budget(self) -> bool:
        return self.spend > BUDGET_GUARD

    def tick_turn(self):
        """Call once per turn: counts down the post-failure pause."""
        self.last_error = None
        if self.skip > 0:
            self.skip -= 1
            self.last_error = "skipped"

    def _fail(self):
        self.fails += 1
        if self.fails >= SKIP_AFTER_FAILS:
            self.skip, self.fails = SKIP_TURNS, 0

    def _call(self, system, user, thinking_budget, max_tokens, timeout):
        if self.stub:
            return _env("BOT_STUB_LLM_REPLY", "STUB_LLM_REPLY", '{"a": "", "c": "Good game."}')
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.info["base_url"], api_key=self.info["api_key"], max_retries=0)
        thinking = ({"type": "disabled"} if not thinking_budget
                    else {"type": "enabled", "budget_tokens": max(1024, int(thinking_budget))})
        resp = self._client.chat.completions.create(
            model=self.model, max_tokens=max_tokens, timeout=timeout,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body={"thinking": thinking})
        u = getattr(resp, "usage", None)
        if u:
            self.spend += (getattr(u, "prompt_tokens", 0) or 0) * PRICE_IN + \
                          (getattr(u, "completion_tokens", 0) or 0) * PRICE_OUT
        ch = resp.choices[0]
        if getattr(ch, "finish_reason", None) == "length":
            return None  # cut off
        return ch.message.content or ""

    def ask(self, system: str, user: str, *, prep: bool = False, timeout: float = 8.0) -> str | None:
        """Match call: thinking off, 250 tokens. Prep call: thinking 2000, max 4000. None on any failure."""
        if not self.available():
            self.last_error = "skipped" if self.skip > 0 else "unavailable"
            return None
        try:
            text = (self._call(system, user, 2000, 4000, timeout) if prep
                    else self._call(system, user, 0, 250, timeout))
        except Exception as e:  # network, auth, timeout...
            _log("llm error:", type(e).__name__, str(e)[:120])
            self.last_error = f"{type(e).__name__}: {str(e)[:80]}"
            self._fail()
            return None
        if not text or not text.strip():
            self.last_error = "empty_or_cut_off"
            self._fail()
            return None
        self.fails = 0
        return text

    def ask_json(self, system, user, **kw) -> dict | None:
        text = self.ask(system, user, **kw)
        return parse_json(text) if text else None


def parse_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None
