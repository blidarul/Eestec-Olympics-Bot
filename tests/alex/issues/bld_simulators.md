Title: [alex] contract: simulator verification results and MDP table for mdp_solve
Labels: agent:bld, status:todo, type:contract   (DRAFT, not filed: alex decides when to send)

## Goal
Tell prep what verification checks on a simulator, which simulators failed on the practice games (none, see below),
and the table format that would let `mdp_solve` use a prep-built model of a small chance game.

## Findings (arena-lite, --prep, stub model, 2026-11-14)
| game | variants | simulator verified | notes |
|---|---|---|---|
| tic_tac_toe | 3x3 classic, 5x5 four in a row | both: yes ("ok") | decisions use alpha-beta (3x3) / MCTS (5x5) |
| guess_number | 1-100, 1-1000 | both: yes | hidden secret: Generic does not use the simulator ("hidden information"), so no search |
| pig | one die to 50, two dice to 60 | both: yes (has_chance) | MCTS, 3 s per move |
No simulator failed verification on these three games, so there is no failure list yet. Two things to check on your side:
- `calibration.is_terminal_verified` is false for every game: terminal detection was never checked against a real end state.
- tic_tac_toe 5x5 decisions took 6.0 s (MCTS to its budget on a position alpha-beta cannot solve). Fine for the 20 s clock, but
  the think_ahead/search strategy and `assist_turn` each spend their own budget; use only one of them per turn.

## verify() criteria (solvers/verify.py: all must hold on the variant's sample_turn)
1. `parse(sample.observation, seat)` does not raise and the state is not terminal (a sample_turn is required).
2. When `sample.legal_actions` is a list: `set(legal(state)) == set(legal_actions)` (strings, exact).
3. 200 random playouts from that state end within 500 steps, no exception, only legal moves.
4. If the simulator has `to_move(state)`: it returns the sample's seat (0 unless the sample says otherwise).
A simulator without `parse(observation, seat)` is rejected ("simulator has no parse"). Verification runs per variant;
`simulator.py` is the first variant only, so write `simulator_<i>.py` per variant (hooks already look for it).
Chance: a simulator with chance nodes must set `has_chance` (search then uses MCTS and never reports a proven win).

## mdp_solve table format (harness-only tool `mdp_solve`, solvers/mdp.py)
```json
{"table": {"s0": {"roll": [[0.1667, "s1", 0.0], [0.8333, "s2", 0.0]], "hold": [[1.0, "end", 1.0]]},
           "s1": {...}, "end": {}},
 "start": "s0", "discount": 1.0}
```
`table[state][action] = [[probability, next_state, reward], ...]`; states are strings; a terminal state has `{}` (no actions,
value 0); probabilities of one action sum to 1; at most 5000 states. Result: `{value, action, iterations, converged, states}`.
Reward is from the point of view of the player to move at `state`; for alternating games encode the opponent's turn as part
of the transition (next_state after the opponent's reply), or negate rewards on a hand-over.

## Acceptance
- prep writes `simulator_<i>.py` for every variant and `verify_isolated` returns verified for the practice games.
- (optional) prep writes `mdp_<i>.json` in the format above for chance games with < 5000 states; alex wires it into `_search`.

## From
alex
