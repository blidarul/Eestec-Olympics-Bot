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
