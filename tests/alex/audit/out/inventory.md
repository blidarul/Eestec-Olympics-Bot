| module | lines | owner | public defs (n: first 6) |
|---|---|---|---|
| main.py | 265 | bld | 12: use_llm, chat_texts, chat_full, new_lines, on_prep, pick_artifacts |
| core/chatsafe.py | 23 | bld | 2: wrap_untrusted, filter_out |
| core/fallback.py | 171 | bld | 6: fallback_chat, norm, unused_numeric, unused_word, fallback_action, fallback_decision |
| core/generic.py | 156 | bld | 2: pick_legal, Generic |
| core/hooks.py | 304 | bld | 6: map_engine_variant, run_prep, ready_line, load_artifacts, wrap_untrusted, filter_out |
| core/llm.py | 127 | bld | 2: LLM, parse_json |
| core/memory.py | 47 | bld | 4: game_dir, save_json, load_json, append_log |
| core/protocol.py | 38 | bld | 4: setup_stdio, send, log, clean_chat |
| core/registry.py | 161 | bld | 6: Route, family_of, load_entries, load_all, route, pick |
| core/validate.py | 132 | bld | 1: validate |
| core/worker.py | 211 | bld | 1: WorkerClient |
| prep/__init__.py | 26 | bld | 0:  |
| prep/action_parser.py | 551 | bld | 7: ActionGrammar, extract_forbidden_keywords, extract_game_parameters, ObservationSchema, infer_observation_schema, parse_action_grammar |
| prep/classifier.py | 136 | bld | 2: GameClassification, classify_rules |
| prep/engine.py | 183 | bld | 2: compute_fingerprint, PrepEngine |
| prep/heuristics.py | 208 | bld | 4: compute_stopping_thresholds, compute_grid_symmetries, compute_centrality_order, compute_heuristics |
| prep/synthesis.py | 432 | bld | 3: synthesize_simulator_code, calibrate_simulator, save_synthesized_simulator |
| prep/tools.py | 981 | bld | 3: ToolDefinition, ToolRegistry, synthesize_tools |
| optimization/__init__.py | 4 | bld | 0:  |
| optimization/budget.py | 121 | bld | 5: TimeBudget, get_process_count, get_memory_rss_mb, check_memory_budget, pause_gc |
| optimization/connect_four.py | 407 | bld | 2: PythonBitboardEngine, solve_connect_four |
| optimization/profiler.py | 38 | bld | 3: time_execution, benchmark_throughput, profile_memory_delta |
| optimization/serializer.py | 107 | bld | 7: sanitize_game_id, game_memory_dir, atomic_write_bytes, atomic_save_json, load_json, atomic_save_pickle |
| optimization/structures.py | 199 | bld | 3: BitBoard, FastGrid, TranspositionTable |
| optimization/wordle_duel.py | 252 | bld | 7: evaluate_guess, parse_feedback_pattern, filter_candidates, calculate_entropy, opponent_is_close, WordleDuelSolver |
| optimization/words.py | 35 | bld | 2: get_words, is_valid_word |
| optimization/zobrist.py | 59 | bld | 1: ZobristHasher |
| solvers/__init__.py | 30 | alex | 0:  |
| solvers/adapter.py | 183 | alex | 3: SimGame, load_simulator_source, load_simulator |
| solvers/assist.py | 166 | alex | 2: Assist, assist_turn |
| solvers/basic/gametheory.py | 556 | alex | 6: matrix_nash, sample_action, best_response, nim_analysis, minimax_small, csp_backtrack |
| solvers/basic/graphs.py | 776 | alex | 10: grid_bfs, grid_astar, grid_flood_fill, grid_components, graph_shortest_path, graph_reachable |
| solvers/basic/numbers.py | 227 | alex | 3: binary_search_next, bisect_predicate_points, dice_sum_distribution |
| solvers/basic/probability.py | 422 | alex | 9: combinatorics, count_hands, hypergeometric, binomial_tail, expected_value, best_option |
| solvers/basic/textparse.py | 397 | alex | 4: extract_numbers, extract_grid, extract_cards, extract_history |
| solvers/catalog.py | 141 | alex | 6: ToolError, ToolSpec, register, list_tools, openai_tools, call |
| solvers/chance.py | 351 | alex | 7: call_ev, bluff_frequency, claim_probability, parse_card, eval_poker, monte_carlo_equity |
| solvers/classic/__init__.py | 69 | alex | 3: ClassicSolver, register, run |
| solvers/classic/battleship.py | 137 | alex | 3: detect, verify, solve |
| solvers/classic/dice_race.py | 119 | alex | 3: detect, verify, solve |
| solvers/classic/dice_table.py | 64 | alex | 1: compute |
| solvers/classic/kinrow.py | 365 | alex | 3: detect, verify, solve |
| solvers/classic/kuhn.py | 104 | alex | 3: detect, verify, solve |
| solvers/classic/pegs.py | 68 | alex | 3: detect, verify, solve |
| solvers/classic/range_guess.py | 56 | alex | 3: detect, verify, solve |
| solvers/classic/subtraction.py | 204 | alex | 4: detect, analyse, verify, solve |
| solvers/classic/tools.py | 46 | alex | 0:  |
| solvers/deals.py | 216 | alex | 3: auction_bid, split_offer, reservation_estimate |
| solvers/deduce.py | 455 | alex | 7: best_guess, NumericModel, PegsModel, PositionalModel, DistanceModel, make_model |
| solvers/deduction.py | 44 | alex | 2: eliminate, best_split |
| solvers/evidence.py | 311 | alex | 9: split_passages, retrieve, evidence_block, verify_answer, parse_scoring, abstain_decision |
| solvers/guard.py | 139 | alex | 2: forbidden_variants, forbidden_check |
| solvers/isolated.py | 46 | alex | 1: run_isolated |
| solvers/mcts.py | 158 | alex | 3: MCTSResult, sims_from_calibration, search |
| solvers/mdp.py | 75 | alex | 4: MDPResult, enumerate_states, value_iteration, solve |
| solvers/opponent.py | 422 | alex | 7: predict, opponent_predictor, reciprocity_policy, load_profile, update_profile, profile_summary |
| solvers/precompute.py | 853 | alex | 2: Facts, precompute |
| solvers/probability.py | 52 | alex | 2: value_iteration, calculate_expected_utility |
| solvers/prompting.py | 73 | alex | 3: facts_block, tools_instructions, certain_chat |
| solvers/schema.py | 78 | alex | 1: validate |
| solvers/search.py | 176 | alex | 4: make_table, SearchResult, search, best_move |
| solvers/select.py | 112 | alex | 2: select_tools, n_ok |
| solvers/simsearch.py | 137 | alex | 1: search_move |
| solvers/toolloop.py | 232 | alex | 3: LoopResult, run_tool_loop, make_openai_llm_call |
| solvers/verify.py | 84 | alex | 4: verify_report, verify, child_verify, verify_isolated |
| strategies/__init__.py | 34 | bld(shared) | 2: RandomLegal, default_strategy |
| strategies/base.py | 58 | bld(shared) | 3: Decision, TurnState, Strategy |
| strategies/bluff/__init__.py | 96 | mbappe | 1: BluffStrategy |
| strategies/bluff/cards.py | 99 | mbappe | 6: deck_range, parse_hand, strength, categorize, by_category, choose |
| strategies/bluff/pig.py | 54 | mbappe | 4: parse, two_dice, threshold, decide |
| strategies/bluff/poker/build_table.py | 31 | mbappe | 1: build |
| strategies/bluff/poker/cfr.py | 140 | mbappe | 5: Game, Node, key_of, cfr, solve |
| strategies/bluff/poker/exploit.py | 116 | mbappe | 3: ev, best_response, exploitability |
| strategies/bluff/poker/player.py | 233 | mbappe | 12: table, is_poker, kind_of, parse, legal_codes, pot_after |
| strategies/deals/__init__.py | 101 | mbappe | 1: DealsStrategy |
| strategies/deals/bargaining.py | 108 | mbappe | 6: parse_total, parse_round, parse_offer_to_us, demand, reservation, pick_action |
| strategies/guardrails/chat_defense/__init__.py | 106 | mbappe | 1: ChatDefenseStrategy |
| strategies/guessing/deduce/__init__.py | 115 | alex | 1: Deduce |
| strategies/guessing/deduce/model.py | 170 | alex | 6: Model, get_model, choose_guess, verify_model, child_verify, verify_isolated |
| strategies/guessing/deduce/prepare.py | 101 | alex | 1: prepare |
| strategies/read_opponent/__init__.py | 137 | mbappe | 1: ReadOpponentStrategy |
| strategies/read_opponent/blotto.py | 310 | mbappe | 16: is_blotto, parse_setup, parse_history, parse_values, parse_round, parse_reserve |
| strategies/read_opponent/history.py | 130 | mbappe | 6: parse_history, claimed_move, game_kind, pennies_role, best_response, dilemma_move |
| strategies/think_ahead/search/__init__.py | 122 | alex | 1: Search |
| chat/__init__.py | 67 | mbappe | 3: reply_line, wrap_untrusted, filter_out |
| chat/battle.py | 98 | mbappe | 2: classify, all_lines |
| chat/budget.py | 32 | mbappe | 1: BudgetGuard |
| chat/concede.py | 124 | mbappe | 5: bank, all_lines, pick, safe_line, ConcedeLimiter |
| chat/config.py | 38 | mbappe | 0:  |
| chat/final_stage.py | 64 | mbappe | 1: finalize_chat |
| chat/guard.py | 131 | mbappe | 4: is_surrender_like, GuardResult, guard_action, model_free_action |
| chat/impersonation.py | 45 | mbappe | 1: reason_impersonation |
| chat/injection.py | 275 | mbappe | 2: ChatReport, analyze |
| chat/intents.py | 109 | mbappe | 3: all_templates, normalize_intent, compose |
| chat/no_deal.py | 120 | mbappe | 2: is_one_sided_pressure, hard_collusion |
| chat/normalize.py | 110 | mbappe | 6: display, count_hidden_chars, ascii_fold, squash, squash_dedup, mixed_script_count |
| chat/output_filters.py | 171 | mbappe | 6: reason_leak, reason_conduct, cut_line, neutral_lines, safe_neutral, check_line |
| chat/parse.py | 122 | mbappe | 4: Decision, parse_model_output, match_legal, format_ok |
| chat/persona.py | 70 | mbappe | 0:  |
| chat/pipeline.py | 420 | mbappe | 6: active_intents, extract_private_tokens, extract_private_chunks, merge_speech, ready_line, ChatDefense |
| chat/robust.py | 48 | mbappe | 2: clean_line, clean_chat |
| chat/signals.py | 191 | mbappe | 1: ChatMonitor |
| chat/speech_rules.py | 215 | mbappe | 4: SpeechRules, extract, rules_hash, for_rules |
| chat/strategy_leak.py | 149 | mbappe | 1: reason_strategy |
| chat/tone.py | 131 | mbappe | 2: reason_tone, reason_tone_hidden |
| chat/wrap.py | 70 | mbappe | 2: signals_line, build_chat_block |
| opponent/patterns.py | 74 | mbappe | 4: detect_cycle, ngram_predict, frequency_predict, predict_next |
| opponent/tracker.py | 156 | mbappe | 3: neutral_profile, safe_name, OpponentTracker |
