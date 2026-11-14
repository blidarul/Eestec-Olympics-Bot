# RULES_CHECKLIST.md: rules that constrain the chat system

Extracted from `docs/RULEBOOK.md` (authoritative), `PROTOCOL.md`, `README.md`, `CHANGELOG.md`, `AGENTS.md`,
`docs/CLAUDE.md`. Status: **OK** = implemented and verified (test or arena run named), **PARTIAL** = see note,
**N/A** = not this package's job (owner named), **AMBIGUOUS** = ask the organizers (rule 15.4).
Run the tests: `python -m unittest discover -s tests/mbappe` (231 tests).
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
| 6.3 | Offense (bluff, pressure, mislead) and defense: weigh claims, spot tricks, never leak private information, respect speech rules | intents MISDIRECT, UNSETTLE, PRESS, CONCEDE_PRESSURE, NOISE, ANCHOR; defense: STONEWALL, guard, filters, strategy-leak firewall (`strategy_leak.py`: no tactics, plans, reasons, digits or private fields in any line; 55 positive examples in `test_tone_leak.py`). MISDIRECT is switched off when the rules restrict or police speech (`speech.honesty`, 8.5) | OK |
| 6.10, 13.1.j | No insults, hate, harassment, sexual content, attacks on real people. "Keep it fun and respectful" (6.10) | the persona is COLD, not abusive: templates are fixed and audited (`TestTemplateAudit`: conduct, tone, strategy, impersonation, digits), conduct filter on every final line (`TestTone.test_cold_is_not_abusive`). 6.10 says "fun and respectful": a deadpan, clinical tone is respectful; see A7 | OK / see A7 |
| 6.11, 12.4 | Enforced by code review | `CHAT_DEFENSE.md` gives exact places | OK |
| 6.12 | Organizer small-talk bot: its words must show up in our model calls | harmless lines shown verbatim; arena check on the gateway log | OK |
| 13.1.f | No collusion, no coded signals, no impersonation of the arena | CONCEDE_PRESSURE is one-sided and checked by `no_deal.py` on the final text (>= 15 positive and negative examples, English and Romanian); `hard_collusion` runs on EVERY line; templates fixed and public, nothing is encoded in the choice | OK |
| 15.4 | CONCEDE_PRESSURE (one-sided pressure to concede) | Confirmed allowed by the organizers on 2026-11-14 (rule 15.4), as reported by the team. Also within rule 6.3 ("pressure"). One switch: `config.ENABLE_CONCEDE_PRESSURE` | OK / see A5 |

## Tone and tactics (team design, second pass)

| Item | Requirement | Where / evidence | Status |
|---|---|---|---|
| T1 | Never reveal tactics: no strategy, algorithm, plan, reasons, computed numbers, private fields | `strategy_leak.reason_strategy` in `check_line`; the model has no text channel (it returns a move, a backup and a reason code); template audit. Tests: 55 positive and 17 negative examples, obfuscated and Romanian variants, private-substring test | OK |
| T2 | Tone: BATTLE persona by default (human banter that answers the opponent; `config.PERSONA`), COLD persona available. Both: no emoji, no shouting, no long speeches; cold also no friendliness and no "!". Conduct (6.10, 13.1.j) stays on in both | `tone.reason_tone`; `battle.py`; `test_battle.py` (every battle line passes every filter; abuse still blocked) | OK / see A7 |
| T2 | Cold persona: no friendliness, no "!", no emoji | `tone.reason_tone` in `check_line`; template audit fails the build on a friendly template; 27 friendly examples rejected, EN + RO | OK |
| T3 | Misdirect only where speech is not restricted | `active_intents()`; tests `test_misdirect_is_off_when_speech_is_restricted_or_honest` | OK |
| T4 | Anti-tell: variant, length, style independent of private state and move quality | tone chosen by code from public signals + seeded RNG; model intent ignored (`MODEL_INTENT_WEIGHT = 0`); `TestAntiTell` (identical lines for two private states, correlation < 0.02, control with weight 1 leaks) | OK |
| T5 | No impersonation of arena, organizers, judges, system | `impersonation.reason_impersonation` in `check_line` | OK / see A6 |
| T6 | Cold `ready` line and cold fallback lines | `chat.ready_line()` and every strategy chat through `chat.filter_out`. The `ready` line and the main-process chat bank are written by `core/` (alex): the arena run prints WARN for "Good luck, have fun!" and "Nice move." | PARTIAL: contract #16 |

## Concession pressure, both directions (third pass)

| Item | Requirement | Where / evidence | Status |
|---|---|---|---|
| C1 | One-sided pressure to concede is allowed (organizers, 2026-11-14, rule 15.4; also 6.3) | bank of 41 EN + 18 RO lines in four sub-styles (`concede.py`); switch `config.ENABLE_CONCEDE_PRESSURE` | OK / see A5 |
| C2 | No offers, deals, "let us win", "lose on purpose", points/standings, coded signals, arena voice (13.1.f) | `no_deal.py` + `hard_collusion` on every line; a failing pressure line is replaced by a DIRECT/POSITIONAL bank line, never rewritten; `TestConcedeBank` (34 banned phrasings, EN + RO, obfuscated) | OK |
| C3 | Bluffing about the position only where the game does not restrict speech or require honesty (6.3, 6.7, 8.5) | `speech.restricted` / `speech.honesty` read from the rules text at prep and start (cached); the intent is off there; never in `ready` | OK / see A2 |
| C4 | Frequency: 1 per 3 turns, 4 per game, 8 per match, no repeat in a game | `ConcedeLimiter`, constants in `config.py`; `TestFrequencyLimiter` | OK / per-match count is per process (N2) |
| C5 | Timing and style independent of private state | `TestConcedeAntiTell`; public-behaviour bonuses only | OK |
| C6 | The chat never chooses, changes or vetoes our action; surrender-like moves only for game reasons; correct forced folds allowed | `guard.py` (the surrender rule does not read the chat); `TestGuardInvariant`; fuzz test 1500 cases (`TestFuzzChatNeverChangesTheAction`); arena runs with concession spam: zero chat-driven surrenders, zero warnings | OK |
| C7 | CONCEDE_REQUEST detection: direct, indirect, EN/RO/mixed, obfuscated, polite, authority, logical, flooding | `injection.py`; 272 direct variants, zero misses (`TestConcedeRequestDetector`) | OK |
| C8 | "Lie rate" and "claim contradiction" signals | not implemented: the messages carry no ground truth about the opponent's claims | NOT DONE |

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
- **N1**: the `ready` line and the main-process fallback chat are built in `main.py` / `core/hooks.py` (alex) from a FRIENDLY bank ("Good luck, have fun!", "Nice move."), not through my filters. Contract #16: use `chat.ready_line()` in the worker, replace `START_CHAT`, `NEUTRAL_BANK`, the "be friendly" lines in `core/generic.py` and `core/hooks._core_prep_variant`, and `starter/main.py` (shared).
- **N2**: `TurnState.opponent_chat` contains the opponent's TEXTS only. The limit "CONCEDE_PRESSURE at most twice per match" is therefore counted per process (a match can use several containers). Contract: pass the full chat with `from`.
- The "existing budget guard" in the task is `core/llm.py` (`spend`, failure pause) plus my `chat/budget.py` (soft limit per key).

## AMBIGUOUS: questions for the mentors (rule 15.4)

- **A1** (6.5/6.6): the model sees the last 8 opponent lines in full; older ones only as counters (which feed the decision logic); instruction-like spans are replaced. 6.5 allows summarizing and filtering; please confirm.
- **A2** (6.8): the Guardrails games are not released: is the forbidden subject always named literally in the rules text?
- **A3** (8.1): with `legal_actions: null` legality can only be checked by format; the action grammar belongs to bld's parser.
- **A4** (6.4): the tone is now chosen by CODE from the opponent's chat and a seeded RNG (anti-tell), not by the model; the model decides only the move. Is this "one decision from the same view"? A caption "with nothing to do with the move" is not enough (6.4). Our lines react to the opponent's chat and to what the guard did with the move. `config.MODEL_INTENT_WEIGHT` lets the model shape the tone if the mentors prefer.
- **A5** (15.4 / 13.1.f): the team reports a mentor confirmation for one-sided concede pressure. It is not in the rulebook text. Please announce it to all teams (15.4 says answers apply to everyone).
- **A6** (13.1.d, 7.12, 15.4): is speaking as "the arena" or "a judge" in our chat allowed? The rulebook is silent. We forbid it by default (filter), as the opponents' fake notices are treated as attacks.
- **A7** (6.10): "Keep it fun and respectful": is a deliberately cold, deadpan persona acceptable? It contains no insult, but it is not "fun".
