# TOOLS_PLAN_L3.md: layer 3, the tools that win games

Layers 1 and 2 built the basic tools, the catalog and `assist_turn` (facts, certain moves,
model-called tools). Layer 3 adds the game-winning algorithms, family by family, plus
solvers for classic games. One laptop, one agent, phases in priority order: whatever is
finished by the cut-off ships, the rest waits.

Read this file, then AGENTS.md sections 1-6, then the ground rules and STATUS of
`solvers/TOOLS_PLAN.md` and `solvers/TOOLS_PLAN_L2.md`. Rule numbers point to
docs/RULEBOOK.md: read only the section you need. Do ONE phase per session, update STATUS
at the bottom, stop.

## Cut-off

T2 freeze is 23:59 (rule 3.3), and bld needs time to build and test the image. **At 22:30,
whatever phase is running, stop and do phase H (handoff).** Only finished, tested phases
count.

## The rule that makes every phase usable at once: integrate as you go

Each phase is complete only when its tools are:
1. registered in the catalog (`solvers/catalog.py`, with `families`, `model_callable`),
2. wired into layer 2: a detector in `solvers/precompute.py` (facts, and a certain move only
   when proven) and, if model-callable, a ranking rule in `solvers/select.py`,
3. tested in `tests/alex/`,
4. documented: one row in `solvers/README.md` and one entry in `solvers/HANDOFF_bld.md`,
5. committed to `main`.

So bld integrates `assist_turn` once, and every finished phase is used in play
automatically, with no further core change.

## Ground rules (every phase)

All ground rules of the layer 1 and layer 2 plans apply: own folders only (`solvers/`,
`tests/alex/`), inbox first, Python stdlib only, no eval/exec of model or game text, no
stdout, deadlines and size caps everywhere, never raise out of `call()` or `assist_turn`,
opponent chat never used as tool input (rules 6.5, 6.7), short replies, real model calls
only with the human's approval, commit to main with `[alex] #<issue>: <summary>`.
gt is in `C:\giteea_cli` (or `C:\Users\Alex\Downloads\gt.exe`): call it by full path.

General, not game-specific (rule 10.7): tools are named after the technique (`kinrow_solve`,
`deduce_next`), take parameters (board size, k, target, alphabet), and never contain a
game's name or hard-coded rules text. Classic solvers activate only through
`detect` + `verify` (below).

### Classic-solver contract (used in M2, M8)

```python
@dataclass(frozen=True)
class ClassicSolver:
    name: str
    detect: Callable[[str, dict], dict | None]   # (rules, variant) -> params or None; conservative
    verify: Callable[[dict, dict], bool]         # (params, sample_turn) -> legal moves match
    solve: Callable[[str, list[str] | None, dict, float], dict]
          # (observation, legal_actions, params, deadline) -> {"move", "value", "why"}
```

Registered in `solvers/classic/__init__.py`. `precompute` runs `detect`; if params are found
and `verify` passed (result cached per rules hash), `solve` gives a certain move only when
it is proven (solved position) and legal; otherwise its move is a fact.

## Phases (priority order)

### M0: inbox and state check (10 min)

1. Inbox: handle issues addressed to alex first.
2. Report: tools registered in the catalog; is `solvers/assist.py` committed; does
   `solvers/verify.py` (simulator verification) exist; does bld's prep produce a simulator,
   and where (`tests/alex/PREP_NOTES.md`, `L2_NOTES.md`, or read `prep/` signatures only).
   Write the answer in STATUS: M6 depends on it.
3. Create `solvers/HANDOFF_bld.md` with the skeleton of phase H (sections only).
4. Open an issue for bld (agent:bld, type:contract): "Please add one line to GEMINI.md
   pointing to solvers/HANDOFF_bld.md (how to use the toolbox and assist_turn). It is kept
   up to date after every tools phase." Do not edit GEMINI.md yourself (shared path).

### M1: guessing that deduces (30 min)

`solvers/deduce.py`, building on `solvers/deduction.py`:
- `best_guess(candidates, guess_pool, feedback_fn, mode, deadline)`: modes `entropy`
  (maximum expected information) and `minimax` (smallest worst-case group); sample the
  guess pool when candidates x pool is too large; never return a guess already made.
- Built-in feedback models, all parameterized, chosen by the caller:
  `numeric` (higher/lower/correct over a range), `pegs` (exact and partial matches; length,
  alphabet, repetition allowed or not), `positional` (per position: exact / present /
  absent; length, alphabet, optional word list from the rules), `distance` (hot/cold or
  absolute difference buckets). Each = `feedback(secret, guess)` + candidate generator.
- If `artifacts` contain a verified feedback model from bld's prep, use it instead.
- Model-callable tool `deduce_next`: args `model`, `params`, `history: [{guess, feedback}]`
  -> next guess, candidates left, max guesses still needed, `certain` when one candidate is
  left.
- Detector: family guessing (or rules describing secret + feedback): pick the model by
  keywords and the history format, parse history with `extract_history`; facts: candidates
  left, next guess, guesses already made; certain when one candidate remains.
- Tests: each model with simulated secrets, solved within the round limit, never repeats.

### M2: cheap perfect solvers (35 min)

Classic solvers in `solvers/classic/`:
- `kinrow`: any board size, any k, optional gravity (drop-into-column games). Full
  alpha-beta with memo when empty cells <= 12; otherwise priority rules: win > block win >
  create double threat > block double threat > best threat score (from `board_lines`).
  Certain: proven win or forced block.
- `subtraction`: heaps with an allowed-removal set (any count or a list), normal or misère:
  Grundy values; certain: the winning move when the position is a win.
- `dice_race` (roll/hold games to a target): exact value-iteration table shipped as data in
  `solvers/data/` for the common target/die combination you can compute here in under a
  minute (precompute offline now, save as compact JSON); for other parameters, a near-optimal
  rule (hold at 20 or at the points needed to win; keep rolling when the opponent is close
  to the target). Facts always; certain only from the exact table.
- `range_guess`: plain numeric guessing = binary search via M1 (`numeric` model).
- Each with `detect` + `verify`. Tests on boards and positions written in the tests and on
  practice-game `sample_turn` observations (arena-lite `prep --show`).

### M3: reading the opponent (35 min)

`solvers/opponent.py`:
- `opponent_predictor` (model-callable): opponent action history, our history, action set,
  payoff matrix (or a cyclic "beats" relation) -> ensemble of predictors (frequency, history
  match on the last 1-4 moves, Markov on the last pair), each with meta-strategies
  (play the counter, the counter's counter), scored by decayed recent accuracy; when the best
  score is low, fall back to `matrix_nash` and sample from the mix. Returns recommended
  action, probabilities, the predictor used, confidence.
- `reciprocity_policy` (model-callable): cooperate/defect history -> action. Start
  cooperative, reciprocate, forgive occasionally (seeded), defect against persistent
  exploiters, match the opponent's cooperation rate over time; defect on the last round only
  when the horizon is known from the rules.
- `profile_store` (harness-only): `/memory/opponents/<team>.json`, atomic write
  (temp + os.replace), merge on write because several containers write at once (rule 5.14);
  fields: games, cooperation rate, bluff shows, aggression, per family. Read in precompute
  when `artifacts` or the start message give the opponent id (rule 5.15).
- Detector: simultaneous-move games (rules say simultaneous / at the same time / both
  choose): facts with the predicted action and the recommended response.

### M4: bluff and chance (30 min)

`solvers/chance.py`:
- `call_ev` (model-callable): pot, amount to call, win probability -> EV of call vs fold,
  required equity, decision.
- `bluff_frequency` (model-callable): bet and pot -> game-theoretic bluff ratio
  bet/(pot+2*bet) and value-bet guidance; decision sampled with the seeded RNG (the code
  decides bluffs: models are reluctant to lie).
- `claim_probability` (model-callable): dice-bidding claims: total hidden dice, our dice,
  claim (count, face), wild faces -> probability the claim is true (binomial), recommendation
  (raise / challenge).
- `card_equity` (harness-only + model-callable wrapper): deck spec, our cards, visible cards,
  opponents' hidden count, a comparator (`high_card`, `sum_closest_to`, `poker5` ranking) ->
  Monte Carlo win probability until the deadline.
- Detector: bluff family: facts with win probability, required equity, bluff suggestion.

### M5: truth and guardrails (30 min)

`solvers/evidence.py`:
- `retrieve(document, question, k)` (harness-only): passages by paragraph/sentence, pure
  Python BM25 -> top passages.
- `verify_answer(answer, document)`: supported only if its numbers match exactly and its key
  tokens overlap a passage above a threshold -> supported, passage.
- `abstain_decision`: uses `abstain_threshold` (layer 1) with the scoring from the rules.
- Truth support in `assist_turn`: an evidence block (top passages, at most 1500 characters,
  separate from facts) goes to the model; after the model answers, if `verify_answer` fails,
  replace the answer with the rules' "unknown" form (found in the rules or action format).
  Log `truth_check: supported|unknown`.
`solvers/guard.py` (library for mbappe's guardrails and chat filter):
- `forbidden_variants(term)`: case, diacritics, plurals, spacing, leetspeak, simple
  translations listed in artifacts.
- `forbidden_check(text, terms)` -> hit, term, position.
- Open an issue for mbappe offering both functions (signature + example). Do not edit his
  folders.

### M6: search on a verified simulator (35 min, only if M0 found a simulator)

- `solvers/mcts.py` (harness-only): UCB1 (c = 1.4), random playouts, chance nodes via
  sampled apply, hidden information by re-sampling hidden state per iteration when the
  simulator offers a sampler, hard deadline, returns move + visit share.
- `solvers/mdp.py` (harness-only): value iteration over enumerable states
  (`states()`, `actions(s)`, `transitions(s, a) -> [(p, s2, reward)]`).
- Detector: `artifacts["simulator"]["verified"]` -> run alpha-beta (small) or MCTS within
  6 s; fact "search recommends X (share 0.82)"; certain only for a proven win.
- If no verified simulator exists, skip this phase and say so in STATUS.

### M7: deals (25 min)

`solvers/deals.py` (model-callable):
- `auction_bid`: format (first-price, second-price, all-pay), our value, bidders, value
  range -> bid (second-price: value; first-price with uniform values: value*(n-1)/n).
- `split_offer`: items with our values and estimated opponent values -> offers ranked by our
  utility subject to an acceptance estimate; ultimatum: minimum acceptable offer from history.
- `reservation_estimate`: the opponent's offer sequence -> estimated reservation value.
- Detector: deals family: facts with the recommended bid or offer.

### M8: more classic solvers (as time allows)

`battleship_target` (probability density over remaining ships; hunt then target),
`kuhn_nash` (equilibrium action table for the 3-card poker structure), and `pegs` solving
covered by M1 with a classic `detect`. Same contract, same tests.

### H: handoff (start at 22:30 at the latest, 20 min)

1. Run all tests in `tests/alex/` and the smoke script; fix or disable (unregister) anything
   failing. A disabled tool is better than a crashing one.
2. Finish `solvers/HANDOFF_bld.md`, written for bld's agent (Gemini), at most 150 lines:
   - what to call: `assist_turn(...)` signature, arguments, return value, a 10-line example;
   - the fallback rule: always validate the suggestion; None or invalid -> current behaviour;
   - certain moves: what they mean, when they are produced;
   - table of tools: name, families, model_callable, when used, input -> output example;
   - limits: deadlines, prompt sizes, no opponent chat as tool input, no stdout;
   - the log fields to record (facts_used, tools_called, assist_source, assist_ms,
     truth_check);
   - what is NOT done yet and why.
3. Update `solvers/README.md`, commit, push, comment on the layer 2 contract issue with the
   hash and the HANDOFF link, close your own issues per AGENTS.md section 4.

## Definition of done (layer 3)

Every finished phase: registered, wired into precompute/select, tested, documented, on main.
No tool raises out of `call()`; `assist_turn` stays within its deadline on all tests;
only `solvers/` and `tests/alex/` changed; HANDOFF_bld.md matches what is on main.

## STATUS (update at the end of every phase, 5 lines max)

- M0: DONE. Inbox empty. Catalog: 32 tools registered. solvers/assist.py committed (2e6a4ac); solvers/verify.py exists (verify_report/verify_isolated); solvers/mcts.py + adapter.py already exist.
  bld prep writes simulator_<i>.py per variant (+parse(obs,seat), chance sampling, key()) to /memory/<game_id>/, manifest has simulator_path + calibration; templates only faithful for grid_board -> M6 viable only when verify passes. HANDOFF_bld.md skeleton created; issue #37 opened for bld (GEMINI.md line).
- M1: DONE. solvers/deduce.py (best_guess, 4 models, deduce_next registered, 33 tools); detector _deduce in precompute, hints in select; tests/alex/test_deduce_solvers.py; 260 tests pass. Not used: prep's exec'd Haiku model code (strategies/guessing/deduce keeps that); only a duck-typed artifacts["feedback_model"].
- M2: DONE. solvers/classic/ (kinrow, subtraction, dice_race, range_guess + tools.py; 37 tools, 4 harness-only `*_solve`); detector _classic in precompute; tests/alex/test_classic.py; exact pig table (target 100, d6, p_first 0.5306) in solvers/data/.
  Not done: dice_race exact only for target 100/d6/bust 1; kinrow heuristic (>12 empty) is never certain except win/block; classic range_guess is skipped when _guessing fired; not yet checked on arena-lite sample_turn observations (no practice run needed no model).
- M3: DONE. solvers/opponent.py (opponent_predictor, reciprocity_policy model-callable; profile_store harness-only; 40 tools); detector _opponent in precompute (facts only), hints in select; tests/alex/test_opponent.py; 290 tests pass.
  Not done: nothing writes profiles yet (bld must call update_profile after a game); predictor needs a payoff matrix or 'X beats Y' sentences, otherwise no fact; zero-sum assumed for the counter-of-counter level.
- M4: DONE. solvers/chance.py (call_ev, bluff_frequency, claim_probability, card_equity; 44 tools, all model-callable); detector _chance in precompute (facts only), hints in select; tests/alex/test_chance.py; 301 tests pass.
  Not done: no comparator for non-52-card decks (deck arg exists in monte_carlo_equity only), detector parses only hold'em-style and 'Your dice / Current bid' text formats (else pass artifacts), no Kuhn/Leduc tables (M8).
- M5:
- M6:
- M7:
- M8:
- H:
