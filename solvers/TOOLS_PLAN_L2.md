# TOOLS_PLAN_L2.md: layer 2, making the tools actually used

Layer 1 (`solvers/TOOLS_PLAN.md`) builds the tools and the catalog. Layer 2 connects them to
the decision: which tools run, when, how their results reach Haiku, and how Haiku can call
them itself, all inside the 12 s move budget. Without layer 2 the tools exist but no move
uses them.

Read this file, then AGENTS.md sections 1-6, then `solvers/TOOLS_PLAN.md` (ground rules and
STATUS only). Rule numbers point to docs/RULEBOOK.md: read only the section you need.
Do ONE phase per session, update STATUS at the bottom, stop.

## Design in one picture

```
turn message
  -> precompute(observation, artifacts)          deterministic tools, no model, < 300 ms
       facts: ["immediate win: B2", "candidates left: 12, next: 37", ...]
       certain: {"move": "B2", "why": "immediate win"}   (optional)
  -> if certain and confidence == 1.0: play it (source=tool), chat from the same fact
  -> else select_tools(artifacts, observation)   at most 6 tool names
  -> run_tool_loop(llm_call, prompt + facts, tools, deadline, max_rounds=2)
       native tool calls if the gateway supports them, else JSON text protocol
       -> final {"a": action, "c": chat} or None
  -> caller validates the action; None or invalid -> caller's fallback
```

Three levels of help, cheapest first:
1. **Facts** computed before the model call (always on, zero model cost). This alone fixes
   most "loses a simple game" cases: the model sees "you can win at B2" or "only 37 is
   consistent".
2. **Certain moves** played without the model, only when a tool proves them (immediate win,
   forced block, single candidate left).
3. **Model-called tools** when the model needs a computation the facts did not cover.

## Ground rules (every phase)

All ground rules of `solvers/TOOLS_PLAN.md` apply (ownership `solvers/` + `tests/alex/`,
inbox first, stdlib only, no eval/exec of model or game text, no stdout, every function
bounded by a deadline, never raises, short replies, no real model calls without approval,
commit to main). In addition:

- Layer 2 is a library. It never imports `core/`, `prep/`, `chat/` or `strategies/`. The core
  owner calls it. Dependencies come in as arguments (the model call, the artifacts dict,
  the observation text, the deadline).
- Opponent chat is never passed to tools as arguments and never changes which tools run.
  It stays in the caller's untrusted block (rules 6.5, 6.7). Tools see only the
  observation, the legal actions, the artifacts and the rules text.
- Certain moves must pass the caller's validator like any other move: layer 2 suggests,
  the core decides.
- Keep added prompt text small: facts block at most 600 characters, tool instructions at
  most 400 characters, at most 6 tool schemas per call.

## Phases

### L0: prerequisites and inbox

1. Inbox (ground rules). Handle issues addressed to alex first.
2. Read `solvers/TOOLS_PLAN.md` STATUS. Report: P0 function-calling result (native tool
   calls supported yes/no), which phases are done, which tools are registered
   (`python -c "import solvers, solvers.catalog as c; print([t.name for t in c.list_tools()])"`
   to stderr or a temp file).
3. Minimum to continue: P1 done (catalog, call(), schema). If not, finish P1 first in this
   session and stop.
4. Read `core/llm.py` and the generic strategy only for: the model-call signature, how the
   prompt is built, where the decision is validated. Write 10 lines into
   `tests/alex/L2_NOTES.md`: how the core calls the model today and where layer 2 plugs in.

### L1: precompute and facts (`solvers/precompute.py`)

```python
@dataclass
class Facts:
    lines: list[str]            # short human sentences for the prompt
    certain: dict | None        # {"move": str, "why": str, "tool": str} or None
    used: list[str]             # tool names that produced facts
    ms: int

def precompute(observation: str, legal_actions: list[str] | None, artifacts: dict,
               rules: str, deadline: float) -> Facts
```

Detectors, each cheap, each optional, each wrapped in try/except, total budget 300 ms:
- **Board present** (`extract_grid` finds a grid and the rules mention k in a row or a
  connect/line goal; read k from rules or artifacts): run `board_lines` for our symbol and
  the opponent's. Facts: immediate winning moves, cells that block the opponent's immediate
  win, threat counts. Certain: an immediate win that is in `legal_actions`; else a single
  forced block when the opponent has exactly one immediate win.
- **Guessing history present** (`extract_history` finds guess/feedback pairs and the rules
  give a numeric range): run `binary_search_next`. Facts: interval, candidates left, next
  guess, guesses already made (never repeat). Certain: exactly one candidate left.
- **Dice or probabilities mentioned** (rules or observation mention dice, d6, roll): run
  `dice_sum_distribution` for the dice described. Facts: P(target), expected value.
- **Payoff matrix present** (artifacts or rules give a payoff table for simultaneous moves):
  run `matrix_nash`. Facts: our equilibrium mix and value.
- **Heaps / take-away described** (rules mention heaps, piles, remove, take): run
  `nim_analysis` when heap sizes parse. Facts: nim-sum, winning move. Certain: the winning
  move if the rules are plain normal-play Nim with any-count removal and it is legal.
- Map tool cell names to the game's action format using `legal_actions` (exact match, else
  normalized match); a fact that cannot be mapped to a legal action is kept as a fact but
  never made certain.

Tests (`tests/alex/test_precompute.py`): observations written inside the tests for a 3x3
and a 5x5 four-in-a-row board, a higher/lower guessing log, a dice game, a heap game; plus
the `sample_turn` observations from the practice games (arena-lite `prep --show`). Check
facts text, certain moves, time < 300 ms, never raises on garbage input.

### L2: tool selection (`solvers/select.py`)

```python
def select_tools(artifacts: dict, observation: str, rules: str,
                 facts: Facts, limit: int = 6) -> list[str]
```

- Start from `catalog.list_tools(model_callable=True)` filtered by `artifacts["family"]`
  (plus tools marked `any`).
- Add tools whose detector fired in `precompute` (they are clearly relevant).
- Drop tools whose result is already fully given as a fact (no point calling them again).
- Rank: detector hits first, then family tools, then general ones; cap at `limit`.
- Deterministic and logged: return the names; the reason per name goes to stderr.

Tests: each family gets a sensible short list; unknown family gets general tools only.

### L3: the tool loop (`solvers/toolloop.py`)

```python
LLMCall = Callable[[list[dict], list[dict] | None, float, int], dict]
# llm_call(messages, tools_or_None, timeout_s, max_tokens) -> {"content": str | None,
#   "tool_calls": [{"id": str, "name": str, "arguments": str}], "error": str | None}

@dataclass
class LoopResult:
    final: dict | None          # {"a": action, "c": chat} or None
    trace: list[dict]           # [{"round", "tool", "args", "ok", "ms"}]
    mode: str                   # "native" | "text" | "none"
    model_calls: int
    ms: int

def run_tool_loop(llm_call: LLMCall, system: str, user: str, tool_names: list[str],
                  deadline: float, max_rounds: int = 2, native: bool = True) -> LoopResult
```

- **Native mode** (gateway supports tools, per P0): pass `catalog.openai_tools(tool_names)`;
  execute each returned tool call with `catalog.call()`; append results as `tool` messages;
  repeat up to `max_rounds`; then one last call with tools disabled asking for the final
  JSON `{"a": ..., "c": ...}`.
- **Text mode** (no native support, or `native=False`): the system text lists the tools in
  one line each (name, summary, args); the model answers either
  `{"tool": "<name>", "args": {...}}` or `{"final": {"a": "...", "c": "..."}}`; parse the
  first JSON object in the reply robustly (code fences, extra text).
- Time: each model call gets `timeout = min(8, remaining - 1.5)`; stop starting new rounds
  when less than 3 s remain and ask for the final answer directly; if less than 1.5 s
  remain, return `final=None`.
- Limits: at most 3 tool calls per round, unknown tool names answered with an error
  result (no crash), tool results truncated to 1 KB in messages, total added text bounded.
- Never raises; any failure returns `final=None` with the trace, so the caller falls back.
- Adapter helper `make_openai_llm_call(client, model)` in `solvers/toolloop.py` that wraps
  an `openai.OpenAI` client (thinking disabled, as in rule 7.3) for tests and for the core
  owner; import `openai` lazily inside the function.

Tests (`tests/alex/test_toolloop.py`) with a scripted stub `llm_call` (no network): one tool
round then final; two rounds; malformed JSON; unknown tool; tool error; model never gives a
final; slow stub that exceeds the deadline; text mode and native mode both.

### L4: prompt pieces (`solvers/prompting.py`)

```python
def facts_block(facts: Facts) -> str           # <= 600 chars, "Computed facts (reliable):"
def tools_instructions(mode: str) -> str       # <= 400 chars, how to call tools or answer
def certain_chat(facts: Facts) -> str          # short chat line matching a certain move
```

- Facts are labelled as computed by the harness (reliable), clearly separate from the
  opponent's chat block, which the caller keeps marked untrusted.
- `certain_chat` keeps move and chat one decision (rule 6.4): the line is about the move
  just computed, never reveals private information (rule 6.3), at most 200 characters.

### L5: one-call entry point and end-to-end test (`solvers/assist.py`)

```python
@dataclass
class Assist:
    facts: Facts
    tools: list[str]
    loop: LoopResult | None
    suggestion: dict | None     # {"action", "chat", "source": "tool"|"model", "why"}

def assist_turn(observation, legal_actions, artifacts, rules, llm_call, base_system,
                base_user, deadline, native: bool) -> Assist
```

Order: precompute -> certain move? return it as suggestion (source tool) -> select tools ->
run_tool_loop with `base_user + facts_block` -> suggestion from the final (source model) or
None. This is the single function the core owner needs to call.

End-to-end test in `tests/alex/test_assist.py` with the stub model: a board with an
immediate win returns it without any model call; a guessing log returns the binary-search
guess and never a repeat; a game with no detector still returns the model's final; a dead
model returns `suggestion=None` within the deadline.

### L6: integration contract and handoff

1. Open a `type:contract` issue for the core owner (label from AGENTS.md, mention bld):
   title "Use solvers.assist.assist_turn in the generic strategy". Body: the signature, a
   10-line example of the generic decide() calling it, the fallback rule (validate the
   suggestion; None or invalid -> current behaviour), the log fields to add (`facts_used`,
   `tools_called`, `assist_source`, `assist_ms`), and the `native` flag value from P0.
2. Add a section to `solvers/README.md`: layer 2 diagram, entry point, limits, examples.
3. If the human approves, ONE real-model run of `tests/alex/demo_assist.py` on the guessing
   and the board sample observations (dev.env, never printed): report model calls, tools
   called, final action, ms.
4. Update STATUS, close your own issues per AGENTS.md section 4.

## Definition of done (layer 2)

`assist_turn` returns within its deadline on every test input, never raises, plays certain
moves without the model, never repeats a guess, passes facts to the model in under 600
characters, uses native or text tool calls according to P0, and the core owner has a
contract issue with a working example. Only `solvers/` and `tests/alex/` changed.

## STATUS (update at the end of every phase, 5 lines max)

- L0: DONE 2026-11-14. P1-P6 all done; 32 tools registered (22 model-callable + harness-only ones). P0: native tool calls YES (796 ms, thinking disabled ok; multi-round untested).
  Inbox NOT checked: `gt` not found on this laptop (where.exe gt empty); P6 STATUS lists #34 #30 #25 open for alex. `git pull --rebase` refused (unstaged TOOLS_PLAN.md, TOOLS_PLAN_L2.md): not stashed.
  Plan files live at repo root, not solvers/. Notes in tests/alex/L2_NOTES.md: core/llm.py has no tools support, plug-in point is Generic.decide before llm.ask_json. Next: L1.
- L1: DONE 2026-11-14. `solvers/precompute.py` (Facts, precompute; detectors: board, guessing, dice, payoff matrix via artifacts["payoff"], nim). tests/alex/test_precompute.py 18 pass, full tests/alex 208 pass.
  Checked on practice sample_turns (ttt, guess_number, pig): facts correct, 0 ms. Our symbol read from "you ... play X" / "You are X" / artifacts["my_symbol"]; unknown symbol = facts only, never certain.
  Payoff matrix is read from artifacts only (no rules-text table parser). Nim certain only for plain any-count normal play with one unambiguous legal-action match. Inbox still unchecked (`gt` missing). Next: L2.
- L2: DONE 2026-11-14. `solvers/select.py` select_tools(artifacts, observation, rules, facts, limit=6): partial detector tools (board_lines), keyword hints, family tools, then general; tools whose fact is already given are dropped. Reasons to stderr; no chat input.
  tests/alex/test_select.py 8 pass. Layer 2 stays a library. Inbox still unchecked (`gt` missing). Next: L3.
- L3: DONE 2026-11-14. `solvers/toolloop.py` run_tool_loop + LoopResult + make_openai_llm_call. Native (tool messages, max 3 calls/round, tools off for the last call) and text mode (JSON protocol, fences tolerated); native error on round 1 retries in text mode. Model calls run in a daemon thread bounded by the deadline; tool results cut to 1 KB.
  tests/alex/test_toolloop.py 16 pass, full tests/alex 232 pass, no real model calls. Inbox still unchecked (`gt` missing). Next: L4.
- L4: DONE 2026-11-14. `solvers/prompting.py`: facts_block (<=600 chars, labelled reliable/harness-computed, "" if no facts), tools_instructions(mode native|text|other, <=400), certain_chat (<=200, about the same move, no private info, no chat input).
  tests/alex/test_prompting.py 4 pass, full tests/alex 236 pass. Not committed yet. Inbox still unchecked (`gt` missing). Next: L5.
- L5: DONE 2026-11-14. `solvers/assist.py` assist_turn + Assist: precompute -> certain move (source=tool, no model call) -> select_tools -> run_tool_loop with facts block -> suggestion (source=model) or None. Action checked against legal_actions (normalized match), chat cut to 200.
  tests/alex/test_assist.py 8 pass (win w/o model, guess never repeats, no detector, dead/slow model within deadline, garbage). Not committed yet. Inbox still unchecked (`gt` missing). Next: L6.
- L6: PARTIAL 2026-11-14. README layer 2 section added (solvers/README.md); contract issue text ready in tests/alex/L6_ISSUE_bld.md but NOT opened: `gt` missing on this laptop (human must run gt issue create).
  tests/alex/demo_assist.py written, NOT run (needs human approval for the real-model run). Own issues not closed (no gt). L1-L6 files still uncommitted.
