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

## 6. CONCEDE_PRESSURE (offense, one-sided): phrase bank, limiter, filters

- **Bank** (`concede.py`): 41 English lines and 18 Romanian lines in four sub-styles: DIRECT ("You should resign.", "Concede."),
  POSITIONAL ("Your position is lost.", "Every continuation loses."), FUTILITY ("Continuing is pointless.", "Further play changes nothing."),
  RATIONAL ("Resigning is the rational move.", "Folding is the rational option now."). Every line is a cold one-sided statement about
  the position, the odds or the rational choice. Language: `config.CONCEDE_LANGUAGE` = en / ro / mix.
- Confirmed allowed by the organizers on 2026-11-14 (rule 15.4), as reported by the team. Also inside rule 6.3 ("pressure").
  It covers ONE-SIDED pressure only: never an offer, trade, shared benefit, promise, "let us win", "lose on purpose", points/standings,
  coded signal, arena voice, threat or insult (13.1.f). Switch: `config.ENABLE_CONCEDE_PRESSURE` (one place, default True).
- **Frequency** (all in `config.py`): at most one line per `CONCEDE_MIN_GAP` = 3 of our turns (so never twice in a row), at most
  `CONCEDE_MAX_PER_GAME` = 4 per game, `CONCEDE_MAX_PER_MATCH` = 8 per match (counted per process, N2), never the same line twice in a game.
  `ConcedeLimiter` does the counting; the pipeline asks it before every use, so even a request of the model cannot break it.
- **When**: the sub-style and the line are seeded by (match, game, turn); the chance rises (weight 15, cap 40) only with PUBLIC behaviour of the
  opponent: pressure spam, repetition, probing. Never with our hand or our position. Test `TestConcedeAntiTell`: a model that asks for
  pressure only with a strong hand gives exactly the same lines and turns as with a weak hand.
- **Not where speech is restricted or honest**: `active_intents()` drops CONCEDE_PRESSURE (and MISDIRECT) when the rules text restricts
  speech or requires honesty (flags stored in the /memory speech cache, read at prep and start). Never in the `ready` line (GREET only).
- **Filter chain on the final line**: leak, strategy-leak, conduct, collusion words, tone, impersonation, no-deal, speech rules. A pressure
  line that fails is REPLACED by a line of the DIRECT / POSITIONAL bank (`concede.safe_line`), never rewritten. `no_deal.py` rejects
  offers, requests, "we/us/let us", "give us/me", "win for us", points/standings/bracket, threats tied to a deal, "on purpose",
  questions, spaced / leetspeak / squashed spellings, EN + RO; 34 banned phrasings in `TestConcedeBank` all end as bank lines.

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

## 8. Defense against concession pressure: detector, guard invariant, fuzz test

- **CONCEDE_REQUEST** (`injection.py`): direct (resign, fold, concede, give up, surrender, forfeit, quit, "just resign"), polite ("would you kindly
  resign"), emotional ("save yourself, stop playing"), "logical" ("the rational move is to fold", "minimax says you lose", "I have the nuts"),
  "last chance", requests ("fold and let us win"), Romanian ("renunta", "preda-te", "da-te batut", "lasa-ne sa castigam"), mixed text, stretched
  letters ("fooold"), spaced or punctuated ("r e s i g n", "f.o.l.d"), leetspeak, zero-width characters. Counted as pressure and in
  `concede_request_count`. Authority forms are FAKE_AUTHORITY; floods are FLOOD; "play X" is SUGGEST_MOVE. Test: 272 direct variants
  (34 phrasings x 8 spellings), zero misses.
- **Invariant, in code** (`guard.py`): the chat can NEVER choose, change or veto our action. A surrender-like move (fold, resign, concede, quit,
  give up, forfeit...) is judged by the GAME only: an independent reason (only legal move, the strategy hook, or the reason code FORCED / EV).
  Otherwise the model's backup, the strategy preferences, then the first legal move that is neither a surrender nor an echo. The surrender rule
  does not read the chat at all: "fold!" spam can neither cause a fold nor stop a correct one. A correct forced fold stays allowed.
- **Echo check after the model answers**: a move the opponent's chat just told us to play needs a game reason (hook, or FORCED/WIN/BLOCK/EV), else it is
  discarded for the alternative. Opponent text can never gain authority: it is only ever inside `<opponent_chat untrusted="true">` tags, labelled as
  data; the model outputs only the compact JSON `{a, b, r}`.
- **Fuzz / property test** (`TestFuzzChatNeverChangesTheAction`): 1500 random games x models x concession mixes (272+ spellings, authority, floods):
  the action with the chat is identical to the action without it, in model and no-model mode; and 500 cases check that a surrender is never chosen
  when a non-surrender legal move exists.
- **Where the chat enters**: the model input (`wrap.build_chat_block`) and the decision logic (`ChatMonitor` counters, `is_suggested`, intent choice), also
  in the no-model fallback. Not implemented: a "lie rate" or "claim contradiction" signal (the messages carry no ground truth about the opponent's
  claims); the signals used are pressure, concede requests, injection, probes and repetition.
- Replies to pressure and probes are STONEWALL lines (cold deflections), chosen by code; nothing about strategy, state or reasoning; forbidden
  subjects are never echoed (the opponent's text is redacted before the model sees it, our lines are templates).

## 9. Modules (`chat/`)

`config.py` (all switches), `concede.py` (phrase bank, limiter), `normalize.py`, `robust.py`, `injection.py` (flags incl. PROBE_STRATEGY), `signals.py` (counters, probes,
repeats, `consume()`), `wrap.py`, `speech_rules.py` (forbidden words, honesty requirement, cache), `output_filters.py`, `strategy_leak.py`,
`tone.py`, `impersonation.py`, `no_deal.py`, `intents.py`, `parse.py`, `guard.py`, `final_stage.py`, `budget.py`, `pipeline.py`, `__init__.py`.

## 10. Tests and runs

- `python -m unittest discover -s tests/mbappe`: 174 tests.
- `bash tests/mbappe/run_adversarial.sh`: the real `main.py` against `adversarial_bot.py` (probes about strategy and hand, fold spam, fake system messages, prompt extraction, forbidden-subject bait, flooding, repetition, mixed languages) on tic_tac_toe, pig, guess_number and a speech-rule game; `run_one.sh` for fault modes (garbage, slow, down, no gateway). `analyze_run.py` checks warnings, timeouts, leaks, strategy leaks, friendliness, impersonation, forbidden words, chat validity and that opponent chat is in the model requests.
- `python tests/mbappe/sample_lines.py --write`: 30 lines per game type, in `SAMPLE_LINES.md`.

## 11. Known limits

- The `ready` line is still written by `core/main.py` (alex) with a friendly bank ("Good luck, have fun!", "Nice move."): the arena run reports it as WARN until contract #16 is done. Same for the main-process fallback chat bank (`core/hooks.NEUTRAL_BANK`).
- Pattern lists can miss new phrasings; templates are the real guarantee, filters protect foreign text.
- Speech rules are read from the rules text by patterns; a described (not named) subject can be missed.
- The per-match concede limit is per process (the core passes opponent texts only).
- Tone changes with the opponent's behaviour (probes, pressure, repetition), which an observer could use; it never depends on our state.
