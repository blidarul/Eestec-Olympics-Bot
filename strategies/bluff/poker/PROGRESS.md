# Phase 2: Mini Poker (Kuhn + Leduc): done

Files: `cfr.py` (CFR+ solver, build time), `exploit.py` (value and exploitability, independent check), `build_table.py`,
`table_kuhn.json`, `table_leduc.json` (baked tables), `player.py` (observation -> history key -> table lookup, limited
exploitation), `strategies/bluff/__init__.py` (poker branch). Tests: `tests/mbappe/test_poker.py` (19), `poker_sim.py`,
`poker_report.py` (numbers below).

Verified (numbers from `python tests/mbappe/poker_report.py`, 10,000 hands each, 95 percent half-width):
- Kuhn table: value of the first actor -0.0556 (theory -1/18), exploitability 0.0011 chips/hand; J bets alpha, K bets 3 alpha, Q calls 1/3 + alpha (test).
- Leduc table: value -0.0852 (literature -0.0856), exploitability 0.0073 chips/hand, 288 infosets, 12,000 CFR+ iterations (~2.5 min at build).
- Kuhn chips/hand: random +0.153, always-call +0.194, always-raise +0.142, bluffer +0.119, folder +0.190, equilibrium copy +0.013 (+-0.026).
- Leduc chips/hand: random +0.67, always-call +0.62, always-raise +0.50, bluffer +0.57, folder +0.59, equilibrium copy -0.052 (+-0.068).
- 0 illegal actions (the simulator raises on any), table lookup < 10 ms per decision (measured), chat never carries a card (test).

Decisions
- The history key includes round 1 when playing round 2 (perfect recall). The task text quotes a Leduc value of about -0.118 from `poker_cfr.py`:
  that code merges the round-2 infosets across different round-1 histories, so it is not an exact equilibrium. Ours is checked by an
  independent best-response computation (exploit.py) and matches the literature (-0.0856).
- The observation format of the arena is not known to us: the history is read from an action log when there is one, otherwise deduced from
  our legal actions, the pot and who acts first (seat 0 in odd hands); if several histories fit, their strategies are averaged.
- Exploitation (rule: limited): only fold/call mixes in MIXED spots move, by at most 0.04, only after 30 observed openings of the
  opponent, only when its opening rate is extreme (>= 0.6 or <= 0.15); worst case +0.10 chips/hand exploitability in Leduc (measured).

Not verified / risks
- No real arena observations were available: the parsing is tested on our own plausible format (with and without an action log).
- The "reduce variance when ahead" end-of-match idea and the "busted" stack rules are not implemented (they need the match score, which we do not parse).
- Opponent statistics only use what our own legal actions reveal (how often it opens with a bet); showdown statistics from "Previous hands" are not parsed.
