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
