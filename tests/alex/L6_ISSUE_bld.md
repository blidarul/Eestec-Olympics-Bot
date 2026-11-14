Title: Use solvers.assist.assist_turn in the generic strategy
Labels: agent:bld, status:todo, type:contract   (to be created with gt: it is missing on alex's laptop)

## Goal
Make the generic strategy use layer 2 (facts, certain moves, model-called tools) so moves use the tools.

## Contract
```python
from solvers.assist import assist_turn   # -> Assist(facts, tools, loop, suggestion)
assist_turn(observation, legal_actions, artifacts, rules, llm_call, base_system, base_user,
            deadline, native=True)
# suggestion: {"action": str, "chat": str (<=200), "source": "tool"|"model", "why": str} or None
```
Example in Generic.decide, before llm.ask_json:
```python
a = assist_turn(state.observation, state.legal_actions, self.artifacts, self.rules,
                llm_call, system, user, deadline=time.monotonic() + 12, native=True)
s = a.suggestion
if s and validate(s["action"], state.legal_actions):
    return Decision(s["action"], s["chat"], source="assist_" + s["source"])
# None or invalid -> current behaviour (llm.ask_json, then fallback move)
```
`llm_call(messages, tools_or_None, timeout_s, max_tokens) -> {"content","tool_calls","error"}`;
`solvers.toolloop.make_openai_llm_call(client, model)` builds one (thinking disabled, rule 7.3).
Deadline is a time.monotonic() value; it must leave room for the 20 s turn clock.
Opponent chat stays in your untrusted block; never pass it to assist_turn (6.5, 6.7).
Log fields to add: `facts_used` (a.facts.used), `tools_called` (a.loop.trace tools), `assist_source`, `assist_ms`.
`native=True`: P0 showed native tool calls work on the gateway (796 ms, thinking disabled); multi-round untested.
Limits: no network except via llm_call, no stdout, never raises, returns within the deadline.

## Acceptance
- `tests/alex/test_assist.py` passes; a practice game with `--prep` runs without warnings.
- Logs show the four fields above.
- A certain move (immediate win) is played with zero model calls.

## From
alex
