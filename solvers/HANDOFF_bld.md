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

- `opponent_predictor`, `reciprocity_policy` (families: read_opponent/any, model_callable: yes) and `profile_store` (harness-only) (M3, `solvers/opponent.py`). Detector `_opponent` in `precompute`: facts only (predicted opponent move + best response, cooperation rate + suggested action, profile line); never a certain move. Input is action histories only, never chat. Pass `artifacts["opponent"]` (the `opponent` field of `start`) so the profile line appears. After a game, optional: `from solvers.opponent import update_profile; update_profile(team, {"games": 1, "rounds": n, "coop_rounds": c}, family)` (atomic, merges with other containers; returns None on failure, never raises). Example: `catalog.call("opponent_predictor", {"actions": ["rock","paper","scissors"], "beats": {"rock":["scissors"],"paper":["rock"],"scissors":["paper"]}, "opponent_history": [...], "my_history": [...]}, deadline)` -> `{action, probs, predictor, confidence, predicted_opponent}`.

- `call_ev`, `bluff_frequency`, `claim_probability`, `card_equity` (family bluff/any, model_callable: yes; M4, `solvers/chance.py`). Detector `_chance` in `precompute`: facts only, never a certain move (win probability, required equity, call/fold EV, bluff ratio with a code-sampled bluff decision, dice claim probability). Deterministic seed per observation. Optional artifacts: `pot`, `to_call`, `win_prob`, `bet_size`, `n_opponents`, `dice`, `total_dice`, `claim`. Inputs are numbers and cards from the engine, never chat. Example: `catalog.call("call_ev", {"pot": 100, "to_call": 50, "win_prob": 0.4}, deadline)` -> `{ev_call: 10.0, required_equity: 0.3333, decision: "call"}`.
