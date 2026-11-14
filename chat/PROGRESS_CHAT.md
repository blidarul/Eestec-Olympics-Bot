# PROGRESS_CHAT.md: chat-rule compliance fixes (owner: mbappe)

Kept in `chat/` (my folder): AGENTS.md says the repo root is a shared path. Rulebook: `docs/RULEBOOK.md`.
Rule: where the rulebook is ambiguous the strictest compliant reading is used and recorded here.

## Phase 1: code fixes

### Verified (run)
- Baseline before any change: `python -m unittest discover -s tests/mbappe` = **341 tests, OK** (the docs said 174: wrong).
- After the changes: see "Final numbers" at the end of this file.
- New tests: `tests/mbappe/test_decision_chat.py` = 20 tests, OK. Old tests adapted (not weakened): test_concede, test_no_deal,
  test_tone_leak, test_battle (they now allow the action sentence after a reply, or switch `ACTION_LINES` off to test the bank line itself;
  the NOISE expectations now assert that decoys are gone).
- The broader speech patterns flag none of the 3 arena-lite practice games (tic_tac_toe, pig, guess_number) and none of the docs text
  blocks I scanned (7 texts only: a small sample).

### Changes
| Item | Rule | What | Files |
|---|---|---|---|
| 2 | 6.4 | `DecisionInfo` (action, action type from public words, game id, source) built from the move actually chosen; the line comes from it: action sentences per type, a reply to probes/pressure keeps its first sentence and gets the action sentence second. The seeded RNG only picks among variants of one type. `finish()` and `model_free()` use their own chosen action. | `chat/decision.py`, `chat/actionlines.py`, `chat/pipeline.py` (`_with_action`, `chat_only`), `chat/__init__.py` (`reply_line(..., decision=, chat_full=, game=)`) |
| 2 | 6.4 | `NOISE` decoys off for good (`ENABLE_NOISE=False`, `NOISE_PROBABILITY=0`; `compose("NOISE")` returns a MINIMAL line; `read_opponent` no longer asks for it). | `chat/config.py`, `chat/intents.py`, `chat/pipeline.py`, `strategies/read_opponent/__init__.py` |
| 3 | 6.5/6.6 | `pick_among_equal(candidates, opponent_chat)`: the untrusted chat breaks ties among moves the solver values equally (suggested move last, surrender last), never moves a non-tie move, logs one stderr line. Solver wiring is alex's: issue #43. | `chat/influence.py` |
| 4 | 6.1 | Pressure caps (8 per match, 4 per game), spacing, no-repeat memory are recomputed from `chat_full` (our lines are `from: "you"`, matched to the banks by normalized text, a bank line followed by an action sentence still matches). Test: two simulated containers in one match respect the caps. Core wiring: issue #42. | `chat/history.py`, `chat/pipeline.py` |
| 5 | 6.8 | Broader detection of speech rules (described, not named). `SpeechRules.unconfident` = a restriction was found but no term, or only a described subject (3+ words): the game then gets minimal safe chat (MINIMAL neutral lines only, no pressure, no model-written line, no action sentence), also in `ready`. Prep's extra terms (`speech_extra_<hash>.json`) are read add-only. The optional `haiku` call lives in `prep/` (bld): issue #42. | `chat/speech_rules.py`, `chat/pipeline.py` |

### Decisions (strict reading)
- **6.4**: a chat line unrelated to the game is a caption bolted on after the move; decoys removed. The line is built from the chosen action.
  Anti-tell note: the line depends on the action type only, never on the hand or the move's quality; the action is public once the opponent
  reads the chat (the move is revealed in the same or the next message). `TestAntiTell` still passes.
- **6.8**: when unsure what is forbidden, say almost nothing (a wrong line can end the game; a neutral line costs nothing).
- **6.7/13.1.f**: unchanged: the chat never decides a surrender or an echo; no offers in concede-pressure lines.

### Unverified / open
- `core/worker.py` still overwrites `d.chat` with `reply_line(opponent_chat only)` until bld applies #42: until then the chat does not see the move in the real protocol loop, only in `chat_defense` (`finish`/`model_free`) and in tests.
- `chat_full` in `main.py` has no `game` field: per-game pressure cap falls back to per-match (stricter).
- The solver path does not call `pick_among_equal` until alex applies #43. The 6.12 scenario is only tested on the helper (tests/mbappe/test_decision_chat.py), not through a real tic-tac-toe run.
- The action classifier is a word list: unknown action formats become `neutral` (a generic line, still related: "Move made.").
- No real model run was made (the dev key is limited; ask the human first).

## Final numbers (Phase 1)
- `python -m unittest discover -s tests/mbappe`: **361 tests, OK** (341 before + 20 new), 246 s. Fuzz test `TestFuzzChatNeverChangesTheAction` is inside this run and passes.
