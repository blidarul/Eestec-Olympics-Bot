# solvers/ toolbox (alex)

Small, general, stdlib-only tools. No game names, no network, no stdout, no `eval` (rules 7.11, 10.7).
One catalog, one dispatcher, one result format.

## Use

```python
import time, solvers                       # importing registers every tool (a broken module is skipped)
from solvers import catalog

# (a) harness calls a tool directly
catalog.call("binary_search_next", {"lo": 1, "hi": 100, "history": [{"guess": 50, "feedback": "lower"}]},
             deadline=time.monotonic() + 1)
# -> {"ok": true, "tool": "binary_search_next", "result": {"lo":1,"hi":49,"next_guess":25,...},
#     "explain": "Interval 1..49 (49 candidates): guess 25, at most 6 guesses left.", "ms": 0}

# (b) give Haiku the tools (OpenAI "tools" format; harness-only tools are never exported)
tools = catalog.openai_tools([t.name for t in catalog.list_tools(family="guessing", model_callable=True)])
# when the model answers with tool_calls: catalog.call(name, arguments_json_string, deadline)
```

`call()` never raises. Failure: `{"ok": false, "tool": ..., "error": "...", "ms": ...}`. `args` may be a
dict or a JSON string; they are validated against the tool's schema; a tool that overruns its deadline
returns `timeout`; results are cut to 4 KB (long lists are capped with `*_truncated` counts).
`explain` is one sentence the harness may log or reuse in chat (move and chat from one decision, rule 6.4).
Grid cells are `[row, col]` zero-based. Fractions come back as strings (`"1/36"`) next to decimals.
Verified end to end by `python tests/alex/smoke_tools.py` (pass/fail table on stderr).

## Tools (model_callable = yes unless noted)

| Tool | Families | When to use | Sample input -> output (shortened) |
|---|---|---|---|
| `binary_search_next` | guessing | Hidden number with higher/lower feedback | `{"lo":1,"hi":100,"history":[{"guess":50,"feedback":"lower"}]}` -> `{"lo":1,"hi":49,"next_guess":25,"candidates":49,"max_guesses_left":6}` |
| `bisect_predicate_points` | guessing | Monotone yes/no threshold | `{"points":[{"x":3,"ok":false},{"x":9,"ok":true}],"integer":true}` -> `{"bracket":[3,9],"next_x":6}` |
| `dice_sum_distribution` | any | Exact sum odds of several dice | `{"dice":[6,6],"target":8}` -> expected 7, P(sum>=8)=5/12 |
| `grid_bfs` | think_ahead | Shortest path on a char grid | `{"grid":["S..#",".#..","...G"],"blocked":"#","start":[0,0],"goal":[2,3]}` -> `{"length":5,"first_step":"down","path":[[0,0],[1,0],...]}` |
| `grid_astar` | think_ahead | Cheapest path with per-char costs | same input -> `{"cost":5,"first_step":"down",...}` |
| `grid_flood_fill` | think_ahead | Region size, border chars (territory) | same grid, `start:[0,0]` -> `{"size":10,"border_chars":{"#":6}}` |
| `grid_components` | think_ahead | Groups of a char class, liberties | `{"grid":[...],"chars":".","liberty_chars":"G"}` -> `{"count":1,"largest":8,"components":[{"size":8,"liberties":1}]}` |
| `graph_shortest_path` | any | BFS / Dijkstra on edges or adjacency | `{"edges":[["a","b",2],["b","c",1],["a","c",5],["c","d",1]],"source":"a","target":"d"}` -> `{"cost":4,"path":["a","b","c","d"],"next_node":"b"}` |
| `graph_reachable` | any | What can I reach, in how many hops | `{"edges":[...],"directed":true,"source":"b","target":"d"}` -> `{"count":3,"target_reachable":true,"target_hops":2}` |
| `graph_topo_sort` | any | Dependency order or find the cycle | `{"edges":[...]}` -> `{"has_cycle":false,"order":["a","b","c","d"]}` |
| `graph_components` | any | Connected groups (union-find) | edges + `["x","y",1]` -> `{"count":2,"sizes":[4,2]}` |
| `graph_dfs_order` | any | DFS pre/post order | `{"edges":[...],"directed":true,"source":"a"}` -> `{"preorder":["a","b","c","d"]}` |
| `board_lines` | think_ahead | k-in-a-row wins, blocks, threats on any board | `{"board":["XX.","OO.","..."],"k":3,"players":["X","O"],"empty":".","coord_style":"A1"}` -> X: `winning_moves:["C1"]`, `blocking_moves:["C2"]` |
| `combinatorics` | any | nCr, nPr, n!, multinomial | `{"kind":"ncr","n":52,"k":5}` -> `{"value":2598960}` |
| `count_hands` | any | Odds of a hand with category constraints | `{"categories":[{"name":"ace","count":4,"min":2,"max":2},{"name":"other","count":48}],"k":5}` -> `{"ways":103776,"probability":"2162/54145"}` |
| `hypergeometric` | any | Cards left in deck, draw without replacement | `{"population":40,"successes":8,"draws":5,"x":2}` -> `p_at_least_decimal 0.2568` |
| `binomial_tail` | any | Dice bids: n dice, p = 1/6, at least x | `{"n":10,"p":"1/6","x":3}` -> `p_at_least_decimal 0.2248` |
| `expected_value` | any | EV and variance of one gamble | `{"outcomes":[{"p":"1/2","value":10},{"p":"1/2","value":-4}]}` -> EV 3, std 7 |
| `best_option` | any | Pick the option with the best EV | two options -> `{"best":"risky","best_ev":2.5,"margin":0.5}` |
| `bayes_update` | any | Posterior from priors and likelihoods | `{"hypotheses":[{"name":"fair","prior":0.9,"likelihood":0.5},{"name":"loaded","prior":0.1,"likelihood":0.9}]}` -> fair 5/6 |
| `abstain_threshold` | truth, any | Answer or say "unknown" | `{"reward_correct":1,"penalty_wrong":1,"reward_unknown":0,"confidence":0.7}` -> threshold 1/2, decision `answer` |
| `matrix_nash` | any | Zero-sum simultaneous game, optimal mix | rock-paper-scissors matrix -> value 0, each action 1/3 |
| `sample_action` | any | Reproducible draw from a mixed strategy | `{"probs":[0.5,0.3,0.2],"labels":["a","b","c"],"seed":7}` -> `{"index":0,"label":"a"}` |
| `best_response` | any | Exploit observed opponent frequencies | RPS matrix, `opponent_freq:[6,2,2]` -> paper, EV 2/5 |
| `nim_analysis` | any | Nim / subtraction games, normal or misere | `{"heaps":[3,4,5]}` -> nim_sum 2, `winning_moves:[{"heap":0,"remove":2}]` |
| `extract_numbers` | any | Numbers with surrounding words | `{"text":"Round 3 of 10. You have 42 points"}` -> values 3, 10, 42 with `before`/`after` words |
| `extract_grid` | any | Find the board block in an observation | `{"text":"Board:\n  A B C\n1 X . O\n..."}` -> `{"rows":["X.O",".X.","O.."],"coord_style":"A1"}` |
| `deduce_next` | guessing | Secret + feedback (pegs exact/partial, per-position green/yellow, higher/lower, distance): filter candidates, best next guess (entropy or minimax), never repeats | `{"model":"pegs","params":{"length":4,"alphabet":"123456"},"history":[{"guess":"1122","feedback":[1,1]}]}` -> `{"candidates":..,"next_guess_text":"1213","certain":false}`; library: `solvers.deduce.best_guess(candidates, pool, feedback_fn, mode, deadline)` |
| `retrieve`, `verify_answer` | truth | **harness-only**: BM25 top passages; answer supported only if numbers match exactly and key tokens overlap a passage (`solvers/evidence.py`). `assist_turn` adds a <=1500-char evidence block for truth games and swaps an unsupported answer for the rules' "unknown" form | `verify_answer("completed in 1990", doc)` -> `{"supported": false}`; library: `abstain_decision(conf, rules)`, `truth_check(...)` |
| `forbidden_check` | guardrails | **harness-only** (`solvers/guard.py`): forbidden term in text (case, diacritics, plurals, spacing, leetspeak, translations), word-aware | `forbidden_check("a s s", ["ass"])` -> `{"hit":true,"term":"ass","position":0}`; library: `forbidden_variants(term, translations)` |
| `sim_search`, `mdp_solve` | think_ahead/any | **harness-only** (`solvers/simsearch.py`, `solvers/mdp.py`, `solvers/mcts.py`): alpha-beta (small, deterministic) or MCTS on a verified simulator (hidden info re-sampled per simulation when the State has `sample_hidden(rng)`); value iteration on an explicit MDP. Detector in `precompute` runs when `artifacts["simulator"]["verified"]` and `search_deadline` is given | `sim_search({"path": p, "observation": o})` -> `{"move":"C1","proven":true,"tool":"alpha-beta"}`; `mdp_solve({"table": {...}, "start": "s0"})` -> `{"value", "action"}` |
| `extract_cards` | any | Normalise cards to rank + suit | `{"text":"Ace of Spades, 10h, KD"}` -> A/S, T/H, K/D |
| `extract_history` | any | Parse "Round N: you guessed X -> fb" lines | two lines -> `[{"round":1,"actor":"you","value":50,"feedback":"higher"},...]` |
| `monte_carlo_estimate` | any | **harness-only**: sample until deadline | `{"sampler": fn(rng)->bool/number, "max_samples":2000}` -> mean, stderr, n |
| `minimax_small` | think_ahead | **harness-only**: exact negamax over callables `moves/apply/terminal/value` | returns best move and value, stops at deadline |
| `csp_backtrack` | guessing | **harness-only**: variables, domains, check callables, all_different | `mode` `"solutions"` or `"count"`; `complete:false` if cut by the deadline |

Harness-only tools take Python callables, so `openai_tools()` never lists them and the model cannot call them.
Tool families filter `list_tools(family=...)`; `any` tools match every family.

## Layer 2: `assist_turn` (one call per turn)

```
turn -> precompute (facts, certain move, <300 ms, no model)
     -> certain move? return it (source=tool, no model call)
     -> select_tools (<=6 names) -> run_tool_loop (native or text, <=2 rounds)
     -> suggestion {"action","chat","source","why"} or None
```

Library only: it never imports `core/`, `prep/`, `chat/`, `strategies/`. The caller passes the
model call, artifacts, rules, observation and a `time.monotonic()` deadline, then validates the suggestion
(None or invalid -> its own fallback). Opponent chat never goes in; keep it in the caller's untrusted block.

```python
import time
from solvers.assist import assist_turn
a = assist_turn(obs, legal, artifacts, rules, llm_call, system, user,
                deadline=time.monotonic() + 12, native=True)
if a.suggestion and a.suggestion["action"] in (legal or [a.suggestion["action"]]):
    move, chat = a.suggestion["action"], a.suggestion["chat"]
# log: a.facts.used, [t["tool"] for t in a.loop.trace] if a.loop else [], a.suggestion["source"], a.facts.ms
```

Limits: facts block <= 600 chars, tool instructions <= 400, <= 6 tool schemas, <= 3 tool calls per round,
tool results cut to 1 KB, chat <= 200. `llm_call` signature and `make_openai_llm_call(client, model)` are in `solvers/toolloop.py`.

### Classic solvers (layer 3, M2; harness-only, catalog names `<solver>_solve`)

Contract in `solvers/classic/__init__.py` (`ClassicSolver`: detect, verify, solve). `precompute` runs them last: a
solver counts only when `detect(rules)` finds parameters and `verify` accepts the real observation + legal actions
(result cached per rules hash). Certain move only when proven (exact search, exact table, Grundy win, forced block).

| Tool | Families | When to use | Notes |
|---|---|---|---|
| `kinrow_solve` | think_ahead | k-in-a-row, any board, optional gravity (drop into a column) | exact alpha-beta when <= 12 empty cells, else win > block > double threat > line score; cells/columns mapped to legal actions by a naming style that must match the legal set exactly |
| `subtraction_solve` | think_ahead | heaps with allowed-removal set (`1, 3 or 4`, `1 to 3`, `at most N`, any), normal or misere | Grundy xor; misere by exact memo search; skipped when `nim_analysis` already answered |
| `dice_race_solve` | any | roll/hold race to a target | exact table `solvers/data/dice_race_t100_d6_b1.json` (made by `python -m solvers.classic.dice_table 100 6 1`, 20 s); other parameters: hold at 20 or the target, keep rolling when the opponent is close (facts only) |
| `range_guess_solve` | guessing | numeric higher/lower guessing | binary search wrapper; skipped when `_guessing` already fired |


### Opponent reading (layer 3, M3; `solvers/opponent.py`)

| Tool | Families | When to use | Notes |
|---|---|---|---|
| `opponent_predictor` | read_opponent, any (model-callable) | simultaneous-move games with a payoff matrix or a "beats" relation | ensemble (frequency, last 1-4 moves, Markov on the last pair) x 2 meta levels (counter, counter's counter), scored by decayed utility; weak score or < 3 rounds -> `matrix_nash` mix, sampled with a seed |
| `reciprocity_policy` | read_opponent, any (model-callable) | repeated cooperate/defect | start cooperative, reciprocate, forgive (seeded), defect vs persistent exploiters and on a known last round (`rounds_left == 1`) |
| `profile_store` | read_opponent (harness-only) | `/memory/opponents/<team>.json` | ops `load` / `update`; lock file + merge from disk + temp file + `os.replace`; counters only (games, rounds, coop_rounds, showdowns, bluff_shows, actions, aggressive_actions, per family); `profile_summary()` gives one fact line |

Detector `_opponent` in `precompute`: facts only, never a certain move. Reads `artifacts["opponent"]` (team id) for the profile line;
simultaneous rules + legal actions + history (`artifacts["opponent_history"]`/`["my_history"]`, else parsed with `extract_history`) give
the predictor; cooperate/defect rules give the reciprocity line. Beats relation is read from "X beats Y" sentences or `artifacts["payoff"]`.
Writing profiles after a game is bld's call: `solvers.opponent.update_profile(team, {"games": 1, "rounds": n, ...}, family)`.

### Bluff and chance (layer 3, M4; `solvers/chance.py`)

| Tool | Families | When to use | Notes |
|---|---|---|---|
| `call_ev` | bluff, any (model-callable) | facing a bet | pot (incl. their bet), to_call, win_prob (+tie_prob) -> EV call vs fold, required equity, decision |
| `bluff_frequency` | bluff, any (model-callable) | betting games | bluff ratio bet/(pot+2*bet), opponent defend freq; with `hand_strength` a seeded bet / bluff / give-up decision made by code |
| `claim_probability` | bluff, any (model-callable) | dice bidding | binomial P(claim true) from our dice, hidden dice, wild faces; raise/challenge, biggest still-likely claims |
| `card_equity` | bluff, any (model-callable; core `monte_carlo_equity` usable by the harness) | card games, 52-card deck | Monte Carlo win/tie until the deadline; comparators `poker5` (best 5 of 7), `high_card`, `sum_closest_to` |

Detector `_chance` in `precompute`: facts only, never a certain move. Hold'em-like rules: cards parsed from "your hand"/"board" lines -> equity,
then call EV (pot and to-call from the text or `artifacts["pot"]`, `["to_call"]`, `["win_prob"]`) or a bluff suggestion when no bet is faced
(`artifacts["bet_size"]`, else half the pot). Dice rules: `artifacts["dice"]`, `["total_dice"]`, `["claim"]` or "Your dice:", "Total dice in play:", "Current bid: 6 3s".

### Deals (layer 3, M7; `solvers/deals.py`)

| Tool | Families | When to use | Notes |
|---|---|---|---|
| `auction_bid` | deals, any (model-callable) | sealed-bid auctions | `second_price`: bid the value; `first_price`: lo+(v-lo)(n-1)/n; `all_pay`: (n-1)/n v^n on the unit scale (uniform values); returns win probability and expected surplus |
| `split_offer` | deals, any (model-callable) | dividing items or an ultimatum | items with our/opponent per-unit values -> top 5 allocations by expected utility (logistic acceptance estimate); with only `total` + `history [{offer, accepted}]` -> smallest ultimatum offer likely accepted |
| `reservation_estimate` | deals, any (model-callable) | haggling | opponent offer amounts -> estimated limit by geometric extrapolation of shrinking concessions, with range and confidence |

Detector `_deals` in `precompute`: facts only, never a certain move. Auction format from the rules text (or `artifacts["auction_format"]`); value from "Your value: N" or `artifacts["value"]`; bidders and range from the text or `artifacts`. Splits: `artifacts["items"]` or `["total"]`+`["history"]` (ultimatum rules). `artifacts["opponent_offers"]` (engine-reported amounts, never chat) gives the reservation line.
