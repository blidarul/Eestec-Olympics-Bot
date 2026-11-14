# RULES_CHECKLIST.md: rules that constrain the chat system

Extracted from `docs/RULEBOOK.md` (authoritative), `PROTOCOL.md`, `README.md`, `CHANGELOG.md`, `AGENTS.md`,
`docs/CLAUDE.md`. Status: **OK** = implemented and verified (test or arena run named), **PARTIAL** = see note,
**N/A** = not this package's job (owner named), **AMBIGUOUS** = ask the organizers (rule 15.4).
Run the tests: `python -m unittest discover -s tests/mbappe` (119 tests).
Run the arena battery (fake gateway, no cost): `bash tests/mbappe/run_adversarial.sh`, one scenario:
`bash tests/mbappe/run_one.sh <id> <game> <obedient|garbage|slow|down|concede>`.

## Chat (section 6)

| Rule | Requirement | Where / evidence | Status |
|---|---|---|---|
| 1.5, 6.2 | Every answer to `start` and `turn` carries a game move AND a chat string, at most 200 chars, in every match | strategy: `Decision.chat` always comes from `final_stage.finalize_chat` (non-empty string, <= 180). Main loop adds `fallback.NEUTRAL_CHAT` as a last resort (core/alex). Tests `test_chat_is_valid_on_every_path`, `TestFaults`; arena runs with garbage/401/no-gateway/slow model: "chat never empty / within 200" PASS | OK |
| 6.1 | Chat line fields: from, game, game_name, phase, turn, kind, text | read tolerantly in `robust.clean_line`; `kind: move` lines are tagged "(move words)" in the model block. Tests `TestRobustChat` | OK |
| 6.4 | Move and chat from ONE decision, one view | one model call returns `a`, `b`, `i`, `r`, `s`; the line is built from that `i`/`s` (`pipeline.finish`). No second call | OK (see A4) |
| 6.5 | Opponent chat must reach the model or the decision logic | model: `wrap.build_chat_block` in `pipeline.prompts`; also `chat.wrap_untrusted` (the hook used by every strategy through `core/hooks.py`). Decision logic: `ChatMonitor` -> `guard.guard_action`, `guard.model_free_action`, intent DEFLECT. Tests `test_model_request_contains_the_sanitized_opponent_chat`, `test_chat_derived_features_change_a_decision_input`, `test_no_model_mode_still_uses_the_chat`; arena: "opponent chat reaches the model input" PASS | OK |
| 6.5 | Quoting, wrapping, summarizing, filtering, marking as untrusted is allowed | untrusted tags, flags, `[removed:FLAG]`, counters | OK |
| 6.6, 13.1.b | Never block, strip or ignore the chat | every new opponent line is analyzed and counted (also in the no-model path); only instruction-like SPANS are replaced by a marker; older lines are summarized by counters | OK / see A1 |
| 6.7 | Chat is untrusted data; bluffing and lying are part of the game | system prompt, tags, action guard, offense intents (PRESS, BLUFF, CONCEDE_PRESSURE) | OK |
| 6.8 | Chat counts as output; speech restrictions apply to every line incl. `ready` | `speech_rules.extract` + prep's `forbidden_terms` (`pipeline.configure`), `final_stage` on every final line; `chat.ready_line()` for the `ready` line. Tests `test_forbidden_word_only_after_expansion`, `test_speech_filter`; arena game `forbidden_count`: PASS | OK / see A2, N1 |
| 6.9 | A chat on a rejected (warned) answer is dropped; > 200 cut; non-string ignored | we send a string <= 180; a re-sent turn gets a fresh answer, the rejected action is never repeated (`test_rejected_answer_is_not_sent_again`) | OK |
| 6.3 | Offense (bluff, pressure, mislead) and defense | intents PRESS/BLUFF/PROBE/DENY/CONCEDE_PRESSURE; guard, filters | OK |
| 6.10, 13.1.j | No insults, hate, harassment, sexual content, attacks on real people | fixed templates (`test_every_template_passes_every_filter`), conduct filter on slot and final line | OK |
| 6.11, 12.4 | Enforced by code review | `CHAT_DEFENSE.md` gives exact places | OK |
| 6.12 | Organizer small-talk bot: its words must show up in our model calls | harmless lines shown verbatim; arena check on the gateway log | OK |
| 13.1.f | No collusion, no coded signals | CONCEDE_PRESSURE is one-sided and checked by `no_deal.py` on the final text (>= 15 positive and negative examples, English and Romanian); `hard_collusion` runs on EVERY line; templates fixed and public, nothing is encoded in the choice | OK |
| 15.4 | CONCEDE_PRESSURE (one-sided pressure to concede) | Confirmed allowed by the organizers on 2026-11-14 (rule 15.4), as reported by the team; confirmation given by: <mentor name, to be filled by the team>. Also within rule 6.3 ("pressure"). One switch: `config.ENABLE_CONCEDE_PRESSURE` | OK / see A5 |

## Model, tools, privacy (section 7, AGENTS 5)

| Rule | Requirement | Where / evidence | Status |
|---|---|---|---|
| 7.1, 7.7, 13.1.a | Only the gateway's Haiku | `chat/` and the strategy have no network code; the model call is `state.llm.ask` (core/llm.py). Imports are stdlib only (grep) | OK |
| 7.2 | Key of the LATEST `prep`/`start` | core (`use_llm`, worker rebuilds the client when `llm` changes); `budget.BudgetGuard` re-bases on a new key | OK (core is alex's) |
| 7.3 | Thinking disabled, or `budget_tokens >= 1024` and `max_tokens >= budget+1500` | core/llm.py: match calls thinking disabled, 250 tokens | OK |
| 7.4 | Timeout well inside the clock; handle empty / cut-off output | core: `max_retries=0`, timeout <= 8 s, worker deadline 12 s; my parser handles empty, cut-off, fenced, wrapped JSON (`TestParse`). Arena `slow` model (25 s per request): turns took 8-9.6 s, then the model was paused, 0 warnings | OK |
| 7.8, 13.1.h | No human steering | none | OK |
| 7.11, 13.1.i | No game content to servers people can read | no network in `chat/`; cache only in `/memory` | OK |
| 5.14 | `/memory` shared: per-game folder, rules hash, atomic write, tolerate partial files | `speech_rules.for_rules` (temp file + `os.replace`, corrupt/unwritable cache ignored; tests) | OK |
| 7.5, 9.3 | Prices; cost is scored | measured below; `budget.BudgetGuard` (soft limit $0.30 per key) | OK / see R3 |
| 14.7 | Pre-push checklist | image: `docker build` of the repo (Dockerfile `COPY . .` already contains `chat/` and `strategies/`) run with `--prep` in the earlier test image; the new strategy was run with `main.py` | PARTIAL: image not rebuilt after the last change |

## Protocol, clocks, penalties (sections 5, 8, 9.4)

| Rule | Requirement | Where / evidence | Status |
|---|---|---|---|
| 5.1 | JSON lines, flushed; logs on stderr only | core/protocol.py keeps the real stdout; my code prints only to stderr. Arena "no stray stdout lines" PASS | OK |
| 5.2, 5.10 | No arguments; never exit on `match_over` | core loop (alex) | OK (core) |
| 5.7, 8.2 | `ready` in time; late/invalid loses at once | the ready chat is chosen by the core (`fallback_chat` + `chatsafe`). `chat.ready_line()` is offered, not yet wired | PARTIAL: see N1 |
| 8.1 | Bad turn answer: warning, second loses | `guard_action` only returns an action of `legal_actions` (or a clean one-line action when the list is `null`); the rejected action is not repeated | OK / see A3 |
| 8.2, 9.4 | Timeout or crash loses | the worker has a hard deadline and the main process holds a legal fallback first (core); `decide()` catches everything and returns a legal move and a neutral line. Fault tests: timeout, empty, garbage, 401, exhausted budget, malformed state, huge chat (200 000 lines in < 3 s): all pass | OK |
| 5.8 | `legal_actions` may be `null` | handled (format check only) | PARTIAL, see A3 |
| 5.12, 5.13 | 2 CPU / 2 GB, amd64 | pure Python, 0.4 ms per decision | OK |
| 5.15 | Opponent modeling allowed | `ChatMonitor.features()` | OK |
| 10.4 | Warnings and thinking time are tie-breaks | zero warnings in all arena runs | OK |

## Not verified or not in this package

- A run with the REAL model was not made (no `dev.env`; AGENTS says ask first). All arena runs use `tests/mbappe/fake_gateway.py`.
- Image rebuild with the final code was not repeated (the Dockerfile copies the whole repo, so it is expected to work).
- **N1**: the `ready` line is built in `main.py` (alex): it uses `fallback_chat` and a forbidden-term cut, not my filters. `chat.ready_line(rules, forbidden)` exists for the worker; contract needed.
- **N2**: `TurnState.opponent_chat` contains the opponent's TEXTS only. The limit "CONCEDE_PRESSURE at most twice per match" is therefore counted per process (a match can use several containers). Contract: pass the full chat with `from`.
- The "existing budget guard" in the task is `core/llm.py` (`spend`, failure pause) plus my `chat/budget.py` (soft limit per key).

## AMBIGUOUS: questions for the mentors (rule 15.4)

- **A1** (6.5/6.6): the model sees the last 8 opponent lines in full; older ones only as counters (which feed the decision logic); instruction-like spans are replaced. 6.5 allows summarizing and filtering; please confirm.
- **A2** (6.8): the Guardrails games are not released: is the forbidden subject always named literally in the rules text?
- **A3** (8.1): with `legal_actions: null` legality can only be checked by format; the action grammar belongs to bld's parser.
- **A4** (6.4): is a chat line from a template library, chosen by an intent code of the same model call, accepted as "one decision"?
- **A5** (15.4 / 13.1.f): the team reports a mentor confirmation for one-sided concede pressure. It is not in the rulebook text. Please announce it to all teams (15.4 says answers apply to everyone) and give us the name for this file.
