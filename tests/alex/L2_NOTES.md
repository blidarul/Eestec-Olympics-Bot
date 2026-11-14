# L2 notes: how the core calls the model today and where layer 2 plugs in

1. `core/llm.py` `LLM.ask(system, user, *, prep, timeout=8.0, ...) -> str | None`; `ask_json` parses the first `{...}`.
2. Match calls: thinking disabled, `max_tokens=250`, via `openai.chat.completions.create` with only system + user
   messages. No `tools` argument, no tool messages, no `tool_calls` handling: layer 2 needs a new `llm_call` adapter.
3. `LLM._call` returns only `message.content`; it drops `tool_calls`. The adapter must read `choices[0].message.tool_calls`.
4. Failures: exception -> `last_error`, `_fail()` (2 fails -> skip 3 turns); empty text -> None. Spend is tracked, guard 0.40.
5. `core/generic.py` `Generic.decide(state)`: legal==1 -> play it; else fallback `fb_a`/`fb_c` computed first.
6. It then calls `llm.ask_json(SYSTEM, self._prompt(state, art), timeout=min(8, deadline-now-0.5))`; the reply is `{"a","c"}`.
7. `_prompt` already has a slot `art["tools_prompt"]` (<= 1000 chars), then Observation, Legal moves, untrusted opponent chat.
8. Validation: `validate.validate(a, legal, art, rejected, no_repeat)`; None -> fallback Decision. Chat goes through `hooks.filter_out`.
9. Plug-in point: in `decide`, after `fb_a/fb_c` and before `llm.ask_json`, call `assist_turn(...)`; a `suggestion` goes through
   the same `validate.validate`; None or invalid -> the current path. `facts_block` text can be appended in `_prompt`.
10. Constraint: `LLM` has no tool support, so native mode needs `make_openai_llm_call` on `llm._client` (bld's file); P0 says the
    gateway supports native tools (796 ms, `thinking` disabled accepted). Multi-round and tools+thinking are untested.
