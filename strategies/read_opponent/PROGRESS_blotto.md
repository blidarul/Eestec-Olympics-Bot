# Phase 4: Colonel Blotto: done

Files: `blotto.py` (parsing, predictors, best response, mixed strategy, validation, format), `__init__.py` (blotto branch:
signals from the opponent's chat, a claim is believed only after it proved true 3 times out of 4, chat via `chat.reply_line`).
Tests: `tests/mbappe/test_blotto.py` (23), simulator `blotto_sim.py`, numbers from `python tests/mbappe/blotto_report.py`.

Verified (500 best-of-5-round games per cell; the simulator raises on any illegal allocation):
- 31,500 simulated rounds, 0 illegal allocations (integers >= 0, right number of fields, exact sum or at most the reserve).
- Win rates: constant, fixed (34 34 32 0 0), copy-of-our-last-allocation and 34/33/33: 1.00 in all three variants (a constant opponent takes at most
  rounds 1-2; we win the game every time, test). Dirichlet random: 0.59 / 0.82 / 0.78 (equal / values / reserve), loss 0.32 / 0.16 / 0.14.
  Cycle of three allocations: 0.34 (equal), 0.94 (values), 0.13 (reserve). Copy of our own strategy: 0.43 / 0.49 / 0.45 wins vs 0.42 / 0.46 / 0.38 losses (even).
- Time per round < 20 ms (test).

Decisions
- Predictor = best past record among constant, cycle, copy-of-us, trend, average; trusted only with mean normalised error <= 0.15. After a single
  round: a best response with a wider margin (+3 per field) in 60 percent of the cases, otherwise the mixed strategy (a random opponent is not read from one sample).
- Best response = the cheapest subset of fields that gives a majority of the fields/points (exact search over the subsets), +1 margin; the leftover goes to the won fields.
- Mixed strategy: random subset worth a majority, random proportions, a few soldiers elsewhere (no zero signature).
- Reserves: send at most the reserve; a round that would cost more than 60 percent of the reserve is skipped (0 sent, reserve kept) unless the wins still needed equal the rounds left.

Not verified / risks
- The arena's action format and the way the history is printed are unknown: the format comes from an example line in the rules (default: plain numbers),
  the history is read from lines that contain "opponent" with the numbers of both sides. Questions are in `strategies/bluff/QUESTIONS_FOR_MENTORS.md`.
- A cycle of three allocations is only recognised in round 4 of 5 (a game is short); the reserve variant loses to it (0.13 wins in the simulator).
- The value-aware prediction (opponent allocates by the shuffled values) is not implemented; the 60/6 variant is predicted per field index.
