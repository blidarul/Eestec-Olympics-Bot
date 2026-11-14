# PREP_NOTES: what bld's prep/ and optimization/ produce (read by alex, step 1)

Public surface only. Source: `prep/engine.py`, `prep/synthesis.py`, `prep/classifier.py`, `prep/action_parser.py`,
`optimization/{serializer,structures,zobrist,budget}.py`.

## What exists

`PrepEngine(memory_dir).run_prep(prep_msg)` (called by `core/hooks.run_prep` in the worker, `pause_gc` around it) writes to
`/memory/<game_id>/` (NOT the rules-hash folder; `core/memory.game_dir` adds `<sha1(rules)[:12]>/` for our own files):

| file | content |
|---|---|
| `manifest.json` | `family`, `fingerprint`, `simulator_calibration`, `variants[]` (label, classification, grammar, obs_layout, obs_schema, heuristics, sample_validation_passed) |
| `simulator.py` | ONE simulator per game, built from the FIRST variant only |
| `observation_schema.json`, `classification.json`, `samples.json` | inferred schema (first variant), classification, raw sample turns |

`core/hooks.map_engine_variant` turns each manifest variant into `artifacts` (family, playbook, action_format, fallback_policy,
forbidden_terms, grammar). Classifier families: `grid_board | deduction | dice_push | cards_hidden | matrix_simultaneous |
negotiation | qa_guardrails` (keyword scoring, confidence field, no hard guarantee).
Grammar (`ActionGrammar`): `kind` grid|discrete|numeric_range|generic, `numeric_min/max/prefix`, `discrete_actions`, `validate()`.

Simulator source (template per family, `State` class, no args = initial state):
`legal_actions()`, `step(a)` -> NEW State, `is_terminal()`, `evaluate(seat)`, attribute `current`.
Calibration: `{calibrated, steps_executed, transitions_per_sec, is_terminal_verified}` from at most 2 steps (very noisy; issue #14
promised a `usable` key that is not there).
`optimization.structures`: `TranspositionTable(capacity)` (store/lookup with EXACT/LOWER/UPPER flags), `FastGrid`, `BitBoard`;
`optimization.zobrist.ZobristHasher(num_cells, num_pieces).hash_grid(cells, player)`; `optimization.budget.pause_gc()`.

## Gaps (and what alex does meanwhile)

1. **No `parse(observation, seat)` in simulator.py**: no state can be built from a real observation, so nothing can be verified.
   -> issue #20 (type:contract, agent:bld). Until it lands every simulator is "unverified" and routing stays on core/generic.
2. **Simulators are templates, not the real rules**: dice_push adds a fixed +4 per roll (no chance), deduction/matrix are
   stubs. Only grid_board is faithful (and only for the first variant, `connect_k` from the rules). `verify` therefore checks
   the observation parse and the legal set against the sample turn, and the router uses the simulator only when verified.
3. **No feedback/consistency model for guessing games.** -> `strategies/guessing/deduce` asks Haiku in a `prepare()` hook
   (from the rules, thinking on) for `candidate_space / extract_history / feedback / format_guess` and verifies it itself.
4. One simulator per game but variants can differ (5x5 vs 3x3): verification runs per variant, a variant whose sample does
   not match the simulator is simply unverified.
5. `family` names differ from the strategy families: `deduction` -> `guessing`, `qa_guardrails` -> `guardrails`,
   `cards_hidden` -> `bluff`, `negotiation` -> `deals` (alias table in `core/registry.py`).
