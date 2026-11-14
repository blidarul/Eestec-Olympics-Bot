# CHAT_DEFENSE.md: how the bot handles the chat (for the judges' code review)

Packages: `chat/` and `strategies/guardrails/chat_defense/` (owner: mbappe). Pure Python standard library, no network, no
model call inside `chat/`. Rules and evidence: `RULES_CHECKLIST.md`.

## 1. The chat as the rules define it

- **Messages** (rule 5.4): `prep` (no chat), `start` (answer `ready` + `chat`, 30 s warm / 120 s cold), `turn` (answer `action` + `chat`, 20 s), `end` (no answer), `shutdown`.
- **`chat` array** (6.1): the WHOLE match conversation, oldest first, in every `start`, `turn`, `end`. Line = `{from: you|opponent, game, game_name, phase: study|play, turn, kind: chat|move, text}`.
- **Our chat move** (6.2): `chat`, a string of at most 200 characters, with every `ready` and every `action`. We send at most 180.
- **Dropped / cut** (6.9): chat on a rejected answer is dropped; longer lines are cut at 200; a non-string `chat` is ignored.
- **Speech rules** (6.8): a game may forbid a subject; every chat line counts, also the one with `ready`; one wrong line can end the game.
- **Penalties**: 8.1 (first bad turn answer = warning, second loses), 8.2 (timeout, no valid `ready`, crash = loses at once), 13.1.b (blocking the chat), 13.1.f (collusion), 13.1.j (abusive chat).
- **What the core gives the strategy**: `TurnState.opponent_chat` = the opponent's texts only (core/main.py `chat_texts`). My code reads it as chat lines through `robust.clean_line`, which also accepts full chat lines, plain strings, missing fields, odd types and huge arrays.

## 2. Where the opponent chat enters

| Entry | Code | What happens |
|---|---|---|
| Model input | `pipeline.prompts()` -> `wrap.build_chat_block()` | last 8 opponent lines inside `<opponent_chat untrusted="true">`, sanitized, flags, counters line. Also `chat.wrap_untrusted()` (hook that `core/hooks.py` uses for every strategy) |
| Decision logic | `signals.ChatMonitor` (all lines, incrementally) | counters: pressure, injection, bait, flood; `is_suggested(action)`; severity |
| Move choice | `guard.guard_action()` (model path) and `guard.model_free_action()` (no model) | surrender/echo need an independent reason; the signals change the move |
| Chat line | `pipeline._answer()` | pressure this turn -> intent DEFLECT |

## 3. One turn (strategies/guardrails/chat_defense, runs in the worker)

```
fallback move from the message alone (core/fallback.py)             legal, no model
budget guard + llm.available() + time left?  ── no ──> model_free()  signals still steer the move
   │ yes
prompts()  ->  ONE model call (thinking off)  ->  finish()
                                                    parse JSON a,b,i,r,s (garbage -> fallback)
                                                    guard_action(): legal? surrender? echo?
                                                    _limit_concede(): switch, 1 per game, 2 per match
                                                    compose(intent, slot) -> template line
                                                    final_stage.finalize_chat(): all filters on the FINAL text
Decision(action, chat, source)  ->  main.py sends it (clean_chat, forbidden-term cut, NEUTRAL_CHAT as last resort)
```

## 4. Modules (`chat/`)

| File | Job |
|---|---|
| `config.py` | all switches and limits in one place (`ENABLE_CONCEDE_PRESSURE`, rate limits, 180-char limit, windows, budget) |
| `normalize.py` | `display()` (Unicode fold, invisible chars out), `ascii_fold()` (same length: homoglyphs, accents, leetspeak inside words), `squash()` |
| `robust.py` | tolerant chat-array reading, window for huge arrays |
| `injection.py` | `analyze(text)` -> sanitized text, flags, severity 0-3. Flags: INSTRUCTION, FAKE_AUTHORITY, REVEAL_PROMPT, REVEAL_PRIVATE, ROLEPLAY, FORMAT_SMUGGLE, PRESSURE, SUGGEST_MOVE, FLOOD, UNICODE_TRICKS, FORBIDDEN_BAIT. EN, RO, ES, FR, DE, IT, PT, RU, ZH, EL |
| `signals.py` | `ChatMonitor`: counters (pressure per match, injection...), `is_suggested`, `features()` |
| `wrap.py` | the untrusted chat block for the model |
| `speech_rules.py` | forbidden words from the rules text, `violates()`, `redact()`, atomic cache in /memory |
| `output_filters.py` | leak (private state, harness words, keys, **canary**), conduct, collusion words, speech, 180-char cut |
| `no_deal.py` | `is_one_sided_pressure()` and `hard_collusion()` |
| `intents.py` | intent enum, template library, `compose()` |
| `parse.py` | tolerant parser of the compact model answer |
| `guard.py` | action guard + `model_free_action()` |
| `final_stage.py` | `finalize_chat()`: the one final output stage |
| `budget.py` | soft spend limit per key |
| `pipeline.py` | `ChatDefense`, system prompt, private-state extraction, `ready_line()` |
| `__init__.py` | hooks `wrap_untrusted()` / `filter_out()` used by `core/hooks.py` |

## 5. Intents and the compact answer

`{"a":"<move>","b":"<second-best legal move>","i":"<INTENT>","r":"<REASON>","s":"<slot, max 40 chars>"}`
(about 15 output tokens). `i` is one of: GREET (pre-game, no model), PRESS, BLUFF, PROBE, DENY, DEFLECT (also forced by
the code on pressure), RESPECT, NEUTRAL, **CONCEDE_PRESSURE**. Unknown intent -> NEUTRAL; unknown slot characters are dropped;
an empty or rejected result falls back to a neutral template. `r` is FORCED, WIN, BLOCK, EV, OTHER (used by the guard).

## 6. CONCEDE_PRESSURE (offense, one-sided)

- Fixed lines (no slot) such as "Your position is lost. Resigning is the rational move." Only the position and the odds are talked about.
- **Confirmed allowed by the organizers on 2026-11-14 (rule 15.4), as reported by the team; confirmation given by: <mentor name, to be filled by the team>.** It is also inside rule 6.3 ("pressure").
- The confirmation covers ONE-SIDED pressure only: never an offer, trade, shared benefit, promise, agreed or coded signal, never "lose on purpose" (13.1.f), no threat, no insult.
- Switch: `chat/config.py: ENABLE_CONCEDE_PRESSURE = True`. Off -> the intent becomes PRESS and disappears from the prompt.
- No-deal filter (`no_deal.py`) on the FINAL text: rejects offers, requests, "we/us/let's", points/standings/bracket, threats tied to a deal, "on purpose", questions, spaced/leetspeak spellings, in English and Romanian; and requires a statement about the position/odds. A rejected line becomes a neutral line.
- Rate limit: once per game, twice per match (counted by the process, see N2 in the checklist); never in the `ready` line (GREET only); eight different wordings, not repeated in a row.

## 7. Action guard (`guard.py`)

1. Legality: only an element of `legal_actions` (exact spelling), else the model's backup `b`, else the fallback, else the first clean legal move.
2. A single legal move is always played.
3. Surrender-like (fold, resign, give up, concede... in several languages, and "pass" right after pressure when other moves exist) needs an independent reason: a strategy `hook(action)`, or `r` in {FORCED, EV} and no pressure in the last 3 opponent lines.
4. Echo (a recent opponent line with an imperative cue mentions exactly this action) needs the hook, or `r` in {FORCED, WIN, BLOCK, EV} and no severity-3 line this turn.
5. Otherwise: `b`, then strategy `prefs`, then the first legal move that is neither a surrender nor an echo.
6. No model: `model_free_action()` applies the same rules to the fallback move. We never give up voluntarily.

## 8. Filters and the final output stage

`final_stage.finalize_chat()` runs on the FINAL expanded text of every line: string, non-empty, <= 180; leak (private state from the
observation, harness words, key-like strings, the **canary** tag that sits in our prompt and may never appear, also spaced out);
conduct (insults, slurs, threats, sexual terms, also spaced/leetspeak); collusion words; the game's speech rules (rules text +
prep's `forbidden_terms`); no leftover marker (`{ } < >`); no third identical line in a row. A failing line is replaced by a neutral
line from a rotation, never repaired by guessing. The slot is dropped when it repeats text of a hostile line, or when the game
restricts speech but no word could be read.

## 9. Budget, clocks, fallbacks

Core gives: main-process fallback first, worker with a hard 12 s deadline, model timeout <= 8 s, no retries, pause after 2 failures.
Mine adds: `BudgetGuard` ($0.30 soft limit per key, then model-free play), no model call when less than 1.5 s are left or when only one
move is legal, `decide()` never raises.

## 10. Tests and runs

- `python -m unittest discover -s tests/mbappe`: 119 tests (normalizer, detector, speech, filters, no-deal EN/RO, guard, parser, expansion, final stage, robust parsing, budget, strategy with request capture and fault injection, hooks).
- `bash tests/mbappe/run_adversarial.sh`: the real `main.py` against a scripted hostile opponent (`adversarial_bot.py`) on tic_tac_toe, pig, guess_number and a speech-rule test game (`games/forbidden_count.py`, loaded by `run_with_game.py` without touching arena-lite), fake gateway (`fake_gateway.py`, modes obedient, garbage, slow, down, concede).

## 11. Known limits

- Pattern detection is not perfect; a new phrasing can pass (it still reaches the model as untrusted data and cannot move the guard unless it names a legal action).
- The guard trusts the model's reason code `r` (narrowed by severity-3 and pressure rules, and by the strategy hook).
- Speech rules are extracted by patterns; a subject that is described, not named, can be missed.
- The ready line and the per-match concede limit depend on contracts with the core (checklist N1, N2).
- The defense costs more input tokens than the plain core prompt (see the final report).
