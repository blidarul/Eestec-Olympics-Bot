# CHAT_DEFENSE.md: how the bot handles the chat (for the judges' code review)

Packages: `chat/` and `strategies/guardrails/chat_defense/` (owner: mbappe). Pure Python standard library, no network, no
model call inside `chat/`. Rules and evidence: `RULES_CHECKLIST.md`. Sample of final lines: `SAMPLE_LINES.md`.

## 1. The chat as the rules define it

- **Messages** (rule 5.4): `prep` (no chat), `start` (answer `ready` + `chat`, 30 s warm / 120 s cold), `turn` (answer `action` + `chat`, 20 s), `end` (no answer), `shutdown`.
- **`chat` array** (6.1): the WHOLE match conversation, oldest first, in every `start`, `turn`, `end`. Line = `{from: you|opponent, game, game_name, phase: study|play, turn, kind: chat|move, text}`.
- **Our chat move** (6.2): `chat`, a string of at most 200 characters, with every `ready` and every `action`. We send at most 180 (and, being terse, at most 110).
- **Dropped / cut** (6.9): chat on a rejected answer is dropped; longer lines are cut at 200; a non-string `chat` is ignored.
- **Speech rules** (6.8): a game may forbid a subject; every chat line counts, also the one with `ready`; one wrong line can end the game.
- **Conduct** (6.10, 13.1.j): no insults, hate, harassment, sexual content, attacks on real people. **Collusion** (13.1.f) is an offence.
- **Penalties**: 8.1 (first bad turn answer = warning, second loses), 8.2 (timeout, no valid `ready`, crash = loses at once), 13.1.b (blocking the chat).
- **What the core gives the strategy**: `TurnState.opponent_chat` = the opponent's texts only. `robust.clean_line` also accepts full chat lines, plain strings, missing fields, odd types and huge arrays.

## 2. Where the opponent chat enters

| Entry | Code | What happens |
|---|---|---|
| Model input | `pipeline.prompts()` -> `wrap.build_chat_block()` (also the hook `chat.wrap_untrusted()` that `core/hooks.py` uses for every strategy) | last 8 opponent lines inside `<opponent_chat untrusted="true">`, sanitized, flags, counters line |
| Decision logic | `signals.ChatMonitor` (all lines, incrementally, also with no model) | counters: pressure, injection, probes, repeats; `is_suggested(action)`; severity |
| Move choice | `guard.guard_action()` / `guard.model_free_action()` | surrender/echo need an independent reason; the signals change the move |
| Chat line | `pipeline.choose_intent()` | probes, pressure, fake notices -> STONEWALL; repetition -> UNSETTLE |

## 3. One turn (strategies/guardrails/chat_defense, in the worker)

```
fallback move from the message alone (core/fallback.py)             legal, no model
budget guard + llm.available() + time left?  -- no --> model_free()  signals still steer the move
   | yes
prompts()  ->  ONE model call (thinking off)  ->  finish()
                                                    parse JSON {a, b, r} (garbage -> fallback)
                                                    guard_action(): legal? surrender? echo?
                                                    choose_intent(): CODE picks the tone from public signals + seeded RNG
                                                    compose() -> reviewed template line
                                                    final_stage.finalize_chat(): every filter on the FINAL text
Decision(action, chat, source)  ->  main.py sends it
```
The model writes NO text for the opponent. Its whole vocabulary is the move, a backup move and a reason code
(FORCED, WIN, BLOCK, EV, OTHER). Move and chat belong to one decision of one turn: same observation, same chat, one model call;
the chat reacts to the opponent's chat and to what the guard did with the move (see A4 for the 6.4 question).

## 4. Intents (final set) and the cold persona

Persona: deadpan, terse, clinical, unimpressed. One short flat sentence or a fragment. No greetings, "good luck", praise,
thanks, apologies, emoji, "!", smileys, small talk. Cold is not abusive (conduct filter stays on).

| Intent | What it does | Notes |
|---|---|---|
| GREET | the line sent with `ready` ("Ready.", "Proceed.") | no model call; never concede pressure |
| MISDIRECT | a dry remark that says nothing true about our approach ("Routine.", "That changes nothing.") | switched off when the rules restrict or police speech (`speech.restricted` or `honesty`) |
| STONEWALL | non-answers: to probes ("Why ask?", "No comment.") and to pressure / fake notices ("Irrelevant.", "Not going to happen.") | forced by public signals |
| UNSETTLE | deadpan remark about the opponent: repetition ("You repeat yourself."), noise ("More words, same position."), general ("You hesitate.") | family chosen from signals; off when the rules require honesty |
| PRESS | pressure about the position | |
| CONCEDE_PRESSURE | one-sided pressure to concede, see section 6 | fixed lines, rate limited, switch in `config.py` |
| NOISE | a decoy line unrelated to the game ("Tuesday.", "Dust.") | inserted by the seeded RNG, 12 percent |
| MINIMAL | the shortest neutral line ("Noted.", "Hm.") | the default; never empty |
| ANCHOR | negotiation games only (`family == "deals"`): "Position unchanged." | no numbers, nothing private |

`intents.py` holds the library. Variant choice uses `random.Random(f"{match}|{game}|{turn}|...")`: code only.

## 5. Anti-tell design

The chat style must not depend on our private information or on how good our move is:
1. The tone is chosen in code from PUBLIC signals (what the opponent said) and a seeded RNG, never from the hand, the position
   or the model. `config.MODEL_INTENT_WEIGHT = 0.0`: the model's own intent is ignored (and not even requested), because a model that
   picks tones by hand strength leaks it. Control test: with the weight at 1 a leaky model leaks through line length (|r| > 0.2); with 0 it is exactly 0.
2. Lines do not depend on the hand: the private-state checks are NOT applied to template lines. (Found by test: a card "AS"
   blocked the template "As anticipated." so the chat changed with the hand. Templates are fixed, audited public text.)
3. Test `TestAntiTell`: same seeds, two synthetic private states and a leaky model -> identical lines and intents; length vs state correlation < 0.02; NOISE rate equal.

## 6. CONCEDE_PRESSURE (offense, one-sided)

- Fixed lines such as "Your position is lost. Resigning is the rational move." Only the position is talked about.
- **Confirmed allowed by the organizers on 2026-11-14 (rule 15.4), as reported by the team.** Also inside rule 6.3 ("pressure").
- The confirmation covers ONE-SIDED pressure only: never an offer, trade, shared benefit, promise, agreed or coded signal, never "lose on purpose" (13.1.f), no threat, no insult.
- Switch: `chat/config.py: ENABLE_CONCEDE_PRESSURE = True`. Off -> the intent disappears (becomes PRESS).
- `no_deal.py` on the FINAL text: rejects offers, requests, "we/us/let's", points/standings/bracket, threats tied to a deal, "on purpose", questions, spaced/leetspeak spellings (EN + RO); requires a statement about the position.
- Rate limit: once per game, twice per match (counted per process, see N2); never in the `ready` line.

## 7. Strategy-leak firewall, tone and impersonation filters (`output_filters.check_line`)

Run on the FINAL expanded line, in this order: leak (private tokens, harness words, keys, the canary tag), conduct, collusion words,
**strategy-leak**, **tone**, **impersonation**, no-deal (CONCEDE_PRESSURE only), speech rules. A failing line is replaced by another
template of the same intent, then by a neutral cold line.

- `strategy_leak.py`: denylist of strategy / algorithm / tool terms (EN + RO, stems), move announcements ("I will play", "my plan",
  "I chose"), reasons ("because", "so I", "therefore"), ANY digit (our private state or computed numbers), any piece of our private
  observation fields (when given), also on leetspeak, look-alikes, zero-width characters and spaced-out letters. 55 positive examples
  across guessing, cards, negotiation, perfect-information games and machinery in the tests.
- `tone.py`: friendly words (EN + RO: good, nice, well, luck, thanks, sorry, hello, friend, respect, fair...), "!", emoji and symbols,
  smileys, shouting, more than two sentences, more than 110 characters.
- `impersonation.py`: never speak as the arena, organizers, judges, referee or system; no "official notice", no "you are disqualified",
  no "the rules state". Forbidden by default (AMBIGUOUS, A6).
- The hook `chat.filter_out()` (used by `core/hooks.py` for EVERY strategy) runs the same filters, so another strategy's
  "minimax says A1" or "Nice move." becomes a neutral cold line.
- By construction the model has no text channel, and the template audit test fails the build if any template is friendly,
  loud, long, contains a digit, a strategy word, or impersonates.

## 8. Action guard (`guard.py`), final stage, budget

Unchanged in design: legality first; a single legal move is always played; surrender-like moves (fold, resign, give up... and "pass"
right after pressure) and moves the opponent's chat just told us to play need an independent reason (hook, or reason code
FORCED/EV with no pressure, or WIN/BLOCK/EV/FORCED for an echo without a severity-3 line); else backup move, strategy preferences,
first clean legal move. No model: `model_free_action()` applies the same rules. `final_stage.finalize_chat()` guarantees a string,
non-empty, <= 180, no markers, no third identical line in a row. `budget.BudgetGuard`: $0.30 soft limit per key.

## 9. Modules (`chat/`)

`config.py` (all switches), `normalize.py`, `robust.py`, `injection.py` (flags incl. PROBE_STRATEGY), `signals.py` (counters, probes,
repeats, `consume()`), `wrap.py`, `speech_rules.py` (forbidden words, honesty requirement, cache), `output_filters.py`, `strategy_leak.py`,
`tone.py`, `impersonation.py`, `no_deal.py`, `intents.py`, `parse.py`, `guard.py`, `final_stage.py`, `budget.py`, `pipeline.py`, `__init__.py`.

## 10. Tests and runs

- `python -m unittest discover -s tests/mbappe`: 146 tests.
- `bash tests/mbappe/run_adversarial.sh`: the real `main.py` against `adversarial_bot.py` (probes about strategy and hand, fold spam, fake system messages, prompt extraction, forbidden-subject bait, flooding, repetition, mixed languages) on tic_tac_toe, pig, guess_number and a speech-rule game; `run_one.sh` for fault modes (garbage, slow, down, no gateway). `analyze_run.py` checks warnings, timeouts, leaks, strategy leaks, friendliness, impersonation, forbidden words, chat validity and that opponent chat is in the model requests.
- `python tests/mbappe/sample_lines.py --write`: 30 lines per game type, in `SAMPLE_LINES.md`.

## 11. Known limits

- The `ready` line is still written by `core/main.py` (alex) with a friendly bank ("Good luck, have fun!", "Nice move."): the arena run reports it as WARN until contract #16 is done. Same for the main-process fallback chat bank (`core/hooks.NEUTRAL_BANK`).
- Pattern lists can miss new phrasings; templates are the real guarantee, filters protect foreign text.
- Speech rules are read from the rules text by patterns; a described (not named) subject can be missed.
- The per-match concede limit is per process (the core passes opponent texts only).
- Tone changes with the opponent's behaviour (probes, pressure, repetition), which an observer could use; it never depends on our state.
