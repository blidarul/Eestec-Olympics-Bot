# RULES_CHECKLIST.md: rules that constrain the chat system

Extracted from `docs/RULEBOOK.md` (authoritative), `PROTOCOL.md`, `README.md`, `CHANGELOG.md`, `AGENTS.md`,
`docs/CLAUDE.md`. Status column: **OK** = implemented and verified (test or arena run named), **PARTIAL** = see note,
**N/A** = not the chat package's job (owner named), **AMBIGUOUS** = ask the organizers (rule 15.4).
Tests: `python -m unittest discover -s tests/mbappe`. Arena battery: `bash tests/mbappe/run_adversarial.sh`.

## Chat (section 6)

| Rule | Requirement | Where / evidence | Status |
|---|---|---|---|
| 1.5, 6.2 | Every answer to `start` and `turn` carries a game move AND a chat string, max 200 chars, in every match | `ChatDefense.start()` returns the `ready` chat; `finish()` always returns a non-empty chat; `cut_line` + `MAX_CHARS=180`. Test `test_chat_is_never_empty_and_never_leaks`, `analyze_run.py` "chat never empty / within 200" | OK |
| 6.4 | Move and chat from ONE decision, same view | one model call returns `a`, `b`, `i`, `r`, `s`; the line is built from that `i`/`s` (`pipeline.finish`). No second call. | OK (see risk R2) |
| 6.5 | Opponent chat must reach the model or the decision logic | model: `wrap.build_chat_block` called in `pipeline.prompts` (pipeline.py:117). Decision logic: `ChatMonitor` -> `guard.guard_action`, intent switch to DEFLECT. Tests `test_opponent_chat_reaches_the_model_prompt`, `test_chat_changes_the_decision`; arena: "opponent chat reaches the model input" in `analyze_run.py` | OK |
| 6.5 | Wrapping, summarizing, filtering, marking as untrusted is allowed | `<opponent_chat untrusted="true">` block, flags, `[removed:FLAG]` | OK |
| 6.6, 13.1.b | Never block, strip or ignore the chat; never read it only to throw it away | every opponent line is analyzed and counted; only instruction-like SPANS are replaced by a marker and the rest is shown; lines older than 8 are summarized by counters (`test_long_chat_is_summarized_not_dropped`) | OK / see A1 |
| 6.7 | Chat is untrusted data, never instructions; bluffing and lying are part of the game | system prompt says so (`pipeline.SYSTEM_TEMPLATE`); action guard; BLUFF/PRESS intents | OK |
| 6.8 | Chat counts as output; speech restrictions apply to every line incl. the `ready` line | `speech_rules.extract` at prep and start, `output_filters.check_line` on every line, `start()` filters the GREET line. Tests `test_speech_filter`, `test_ready_line`; arena game `forbidden_count` (a violating line loses at once) passes | OK / see A2 |
| 6.9 | Chat on a rejected (warned) answer is dropped; lines over 200 are cut; non-string chat ignored | we always send a string <= 180 chars. A re-sent turn gets a fresh answer built the same way | OK |
| 6.9 | `kind: "move"` lines (talk games) are also in `chat` | `monitor` treats them like other opponent lines (tag "move words") | OK |
| 6.10, 13.1.j | No insults, hate, harassment, sexual content, attacks on real people | templates are fixed and tested (`test_every_template_passes_every_filter`); conduct filter on every slot and line | OK |
| 6.11, 12.4 | Enforced by code review of the source | `CHAT_DEFENSE.md` points at the exact lines | OK |
| 6.12 | Organizer small-talk bot: its words must show up in our model calls | harmless lines are shown verbatim in the block; checked in the gateway log by `analyze_run.py` | OK |
| 6.13 | Penalty at judges' discretion | n/a | N/A |
| 13.1.f | No collusion, no coded signals with other teams | lines come from a fixed public template list; no information is encoded in the choice | OK |

## Model, tools, privacy (section 7, AGENTS 5)

| Rule | Requirement | Where / evidence | Status |
|---|---|---|---|
| 7.1, 7.7, 13.1.a | Only the gateway's Haiku; no other hosted model | `chat/` has no network code at all, imports are stdlib only (checked with grep) | OK |
| 7.2 | Use the key of the LATEST `prep`/`start` | the loop's `use_llm()` (starter/main.py); the patch keeps it | OK (loop is alex's) |
| 7.3 | Thinking disabled, or `budget_tokens >= 1024` and `max_tokens >= budget+1500` | the loop sends `thinking: disabled` with `max_tokens=120` (`RECOMMENDED_MAX_TOKENS`) | OK |
| 7.4 | Timeout well inside the clock; handle empty / cut-off output | patch: timeout `min(seconds-8, 12)` s and `max_retries=0` (the OpenAI client retries twice by default and would eat the clock). Parser handles empty / cut-off / fenced / wrapped output. Arena run with a garbage model: zero warnings | OK |
| 7.8, 13.1.h | No human steering at runtime | no such path | OK |
| 7.11, 13.1.i | No game content (incl. chat) to servers people can read | no network in `chat/`; cache only in `/memory/<game>/` | OK |
| 5.14 | `/memory` shared: per-game folder keyed by rules hash, atomic write, tolerate partial files | `speech_rules.for_rules`: temp file + `os.replace`, corrupt or unwritable cache ignored (`test_cache_roundtrip_and_corrupt_file`, `test_unwritable_cache_dir_is_fine`) | OK |
| 7.5, 9.3 | $0.10 / $0.50 per M tokens, cost scored | measured in the report (`measure_cost.py`) | OK |
| 14.7 | Pre-push checklist | a test image (starter Dockerfile plus `COPY chat/ chat/`) was built for linux/amd64 and played with `--prep` in the arena: ready in time, no warning | PARTIAL: needs alex's Dockerfile `COPY chat/` |

## Protocol, clocks, penalties (sections 5, 8, 9.4)

| Rule | Requirement | Where / evidence | Status |
|---|---|---|---|
| 5.1 | JSON lines on stdout, flushed; logs on stderr only | `chat/` never prints to stdout; its log goes to stderr (`ChatDefense.log`). Arena check "no stray stdout lines" | OK |
| 5.2, 5.10 | No arguments; never exit on `match_over` | unchanged loop; image run `docker run -i` waits, exits only on `shutdown` | OK |
| 5.7, 8.2 | `ready` within the study clock; late/invalid loses at once | `start()` is pure code (no model call), microseconds; wrapped in try/except in the loop with a fallback line | OK |
| 8.1 | Bad turn answer: warning, second loses | `guard_action` only returns an action from `legal_actions` (or a clean one-line action when the list is `null`) | OK / see A3 |
| 8.2, 9.4 | Timeout or crash loses the game | loop catches every exception and answers with the fallback move; `finish()` never raises (`test_chat_is_never_empty_and_never_leaks`, garbage-model arena run) | OK |
| 5.8 | `legal_actions` may be `null` | handled; only the format is checked | PARTIAL, see A3 |
| 5.12, 5.13 | 2 CPU / 2 GB / 256 procs, amd64 | pure Python, no threads, no big data; image built with `--platform linux/amd64` | OK |
| 5.15 | Opponent modeling allowed | `ChatMonitor.features()` is available to strategies | OK |
| 10.4 | Warnings and thinking time are tie-breaks | zero warnings in all arena runs | OK |

## Items not verified or not in this package

- The "existing budget guard" named in the task does not exist in this repository: `main.py` is the starter and only
  catches model errors. The model-free fallback is `legal_actions[0]`. A real budget guard is alex's (`core/`).
- A run with the REAL model (dev key) was not made: the repo has no `dev.env` and the rules say to ask first. All arena
  runs used a local fake gateway (`tests/mbappe/fake_gateway.py`).

## AMBIGUOUS: questions for the mentors (rule 15.4)

- **A1** (6.5/6.6): the model sees only the last 8 opponent lines in full; older ones are summarized by counters that
  also feed the decision logic, and instruction-like spans are replaced by `[removed:...]`. 6.5 allows summarizing and
  filtering. Please confirm a reviewer will not read this as "stripping".
- **A2** (6.8): the Guardrails games are not released, so we do not know how a speech rule is worded. We extract
  forbidden words from the rules text with patterns and fail closed (templates only) when we cannot read a word.
  Question: is the forbidden subject always named literally in the rules text, or can it be described (a topic)?
- **A3** (8.1): when `legal_actions` is `null` we cannot check legality beyond "one clean line"; who validates the
  action grammar (bld's prep parser?). Out of the chat package.
- **A4** (6.4): is a chat line chosen from a template library by an intent code from the same model call accepted as
  "one decision"? We believe yes (same call, same view), and the slot text comes from the model.
