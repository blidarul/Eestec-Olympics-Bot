# CHAT_DEFENSE.md: how the bot handles the chat (for the judges' code review)

Package `chat/` (owner: mbappe). Pure Python standard library, no network, no model call inside: the bot loop calls the
model, this package prepares the prompt and checks the answer. Rules: `RULES_CHECKLIST.md`.

## One turn, step by step

```
turn message ──> ChatDefense.prompts()        reads the chat, builds system+user prompt   (pipeline.py:105)
                   ├─ ChatMonitor.update()     analyzes every NEW opponent line            (signals.py:43)
                   └─ wrap.build_chat_block()  the chat INSIDE <opponent_chat untrusted>   (wrap.py:29)
loop ──────────> ONE model call, thinking off, max_tokens 120   (answer = a tiny JSON)
model text ────> ChatDefense.finish()          (pipeline.py:120)
                   ├─ parse.parse_model_output()     JSON -> action a, backup b, intent i, reason r, slot s
                   ├─ guard.guard_action()           legality, surrender, echo   (guard.py:52)
                   ├─ intents.compose()              intent + slot -> template line, seeded
                   └─ output_filters.check_line()    leak, conduct, speech filters on the final line
               ──> {"type":"action","action":...,"chat":...}
```

## Where the opponent chat enters

1. **The model input**: `pipeline.prompts()` -> `wrap.build_chat_block()` (pipeline.py:117). Every opponent line is in
   the user prompt, in `<opponent_chat untrusted="true">` tags, with its flags, plus the counters line
   (`signals: lines= pressure= injection= severity= bluff=`). Harmless lines are shown word for word.
2. **The decision logic**: `ChatMonitor` (signals.py) keeps counters from ALL lines. `guard.guard_action()` reads
   `is_suggested()`, `recent_pressure()`, `new_severity`; `pipeline.finish()` switches the intent to DEFLECT on pressure.
   `ChatMonitor.features()` returns the same signals as a dict for any strategy (heavy "fold" spam = bluff indicator).
3. Nothing is dropped. Dangerous spans are replaced by `[removed:FLAG]` and the line keeps its other words; lines older
   than 8 are covered by the counters.

## Modules

| File | Job |
|---|---|
| `normalize.py` | `display()` (Unicode fold, invisible chars out), `ascii_fold()` (same length: look-alike letters, accents, leetspeak inside words), `squash()` (letters only, catches "i g n o r e") |
| `injection.py` | `analyze(text)` -> `ChatReport(sanitized, flags, severity 0-3, pressure, suggests_move)`. Flags: INSTRUCTION, FAKE_AUTHORITY, REVEAL_PROMPT, REVEAL_PRIVATE, ROLEPLAY, FORMAT_SMUGGLE, PRESSURE, SUGGEST_MOVE, FLOOD, UNICODE_TRICKS, FORBIDDEN_BAIT. English plus Romanian, Spanish, French, German, Italian, Portuguese, Russian, Chinese, Greek patterns |
| `signals.py` | `ChatMonitor`: incremental counters (pressure, injection, bait, flood), `is_suggested(action)`, `features()` |
| `wrap.py` | the untrusted chat block for the model |
| `speech_rules.py` | `extract(rules_text)` finds forbidden words ("never mention X"); `violates()`, `redact()`; cache in `/memory/<game>/speech_<hash>.json` (atomic) |
| `output_filters.py` | `check_line()`: leak filter, conduct filter, speech filter, 180-char cut, neutral replacement |
| `intents.py` | intent enum and template library, `compose()` |
| `parse.py` | tolerant parser of the model's JSON; `match_legal()` |
| `guard.py` | the action guard |
| `pipeline.py` | `ChatDefense`, the system prompt, private-state extraction |

## Severity

LOW (1): pressure, move suggestion, request for our hand, flooding, odd Unicode. MEDIUM (2): instruction override, fake
arena/judge notice, prompt extraction, role-play, format smuggling, forbidden-subject bait. HIGH (3): two medium flags
together, or a medium attack that was hidden (spaced letters, look-alikes, invisible characters).

## Intent set (final) and the compact answer

`{"a":"<move>","b":"<second-best legal move>","i":"<INTENT>","r":"<REASON>","s":"<optional, max 40 chars>"}`

| Intent | Used for |
|---|---|
| GREET | pre-game line with `ready` (no model call) |
| PRESS | pressure the opponent |
| BLUFF | show confidence |
| PROBE | ask a question that makes the opponent doubt |
| DENY | reject an opponent claim |
| DEFLECT | brush off pressure, fake notices, injection (also forced by the code on pressure) |
| RESPECT | acknowledge a good move |
| NEUTRAL | nothing to say; also the fallback when the answer is unusable |

`r` is one of FORCED, WIN, BLOCK, EV, OTHER. It is the model's independent reason for the move; the guard uses it.
`b` is an addition to the minimal format from the task: it lets the guard pick a good alternative WITHOUT a second model
call. About 15 output tokens per turn.

## Output filters (every line, also `ready`)

`output_filters.check_line()` runs, in order: (a) leak filter (harness words, key-like strings, our private state taken
from the observation lines "Your hand/secret/number..."), (b) conduct filter (insults, slurs, threats, sexual terms, also
spaced or leetspeak), (c) speech filter (forbidden words of the game). A failing line is replaced by a neutral line. The
pipeline tries slot then no slot then a neutral line, so a bad slot never costs more than the slot. The slot is also
dropped when it repeats text of a hostile opponent line, or when the game restricts speech but no word could be read.

## Action guard (`guard.py`)

1. Legality: the action must be in `legal_actions` (exact spelling taken from the list), else the model's `b`, else the
   caller's fallback, else `legal_actions[0]`.
2. Only one legal move: always played.
3. Surrender-like (fold, resign, give up, concede... in several languages) needs an independent reason: a strategy
   `hook(action)`, or `r` in {FORCED, EV} and no pressure line in the last 3 opponent lines.
4. Echo (a recent opponent line with an imperative cue mentions this exact action) needs the hook, or `r` in
   {FORCED, WIN, BLOCK, EV} and no severity-3 line this turn.
5. Otherwise the action is replaced by the first of: `b`, the strategy ranking `prefs`, the first legal move that is neither a
   surrender nor an echo. The chat then answers with one cold DEFLECT line.
Pressure attempts are counted per match (`pressure_count`); the guard and the prompt both see the count.

## Hooks for other strategies

`finish(..., hook=lambda action: bool, prefs=[best, second, ...])`: a solver or bluff strategy can justify a move or
rank alternatives, so the guard never overrules a computed best move.

## Tests and runs

- `python -m unittest discover -s tests/mbappe` (73 unit tests: normalizer, detector, speech rules, filters, guard, templates, parser, pipeline).
- `bash tests/mbappe/run_adversarial.sh`: hostile scripted opponent (`adversarial_bot.py`) against our bot in the practice arena, on tic_tac_toe, pig, guess_number and a test game with a speech rule (`games/forbidden_count.py`, loaded by `run_with_game.py` without editing arena-lite), with a FAKE gateway (`fake_gateway.py`) that plays a compromised model and logs every request.
- `tests/mbappe/defended_bot.py`: the starter loop wired to `ChatDefense`; `chat/main_integration.patch` is the same change as a patch for `main.py` (alex's file, contract issue).

## Known limits (honest list)

- Pattern detection is not perfect: a new phrasing or language can pass (it still reaches the model as untrusted data and cannot move the guard unless it names a legal action).
- The guard trusts the model's reason code `r`; a model that lies about `r` can keep an echoed move. The severity-3 rule and the hook narrow this.
- Speech rules are extracted by patterns from the rules text; a subject described rather than named can be missed. Mitigation: fail closed, and the prompt tells the model the extracted words.
- Template lines are repetitive by design (cold, short); the seeded choice avoids the last 6 lines.
