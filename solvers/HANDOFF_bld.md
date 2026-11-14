# HANDOFF_bld.md: how to use the solvers toolbox (for bld's agent)

Kept up to date after every tools phase. Skeleton: sections are filled in phase H.

## 1. What to call (`assist_turn`)
## 2. Fallback rule
## 3. Certain moves
## 4. Tools table
- `deduce_next` (families: guessing, model_callable: yes; M1). Args: `model` numeric|pegs|positional|distance, `params`, `history [{guess, feedback}]`, `mode` entropy|minimax. Detector fires for pegs/positional rules (positional needs `artifacts["words"]`); numeric stays with `binary_search_next`. `artifacts["feedback_model"]` (object with `space()`, `feedback(secret, guess)`) overrides the built-ins. Certain move only when one candidate is left and it matches a legal action.
## 5. Limits
## 6. Log fields
## 7. Not done yet
- `kinrow_solve`, `subtraction_solve`, `dice_race_solve`, `range_guess_solve` (classic solvers, M2; harness-only, model_callable: no). They run inside `precompute` (detector `_classic`): `classic.run(obs, legal, rules, artifacts, deadline)` detects the game from the rules text, verifies the model against the real legal actions, then solves. Facts always; certain move only when proven (exact search, exact table, forced block, Grundy win). Direct call: `catalog.call("kinrow_solve", {"rules": ..., "observation": ..., "legal_actions": [...]}, deadline)` -> `{params, move, value, why, proven}`. Needs no core change.

