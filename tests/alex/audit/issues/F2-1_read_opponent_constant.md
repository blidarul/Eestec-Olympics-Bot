# [mbappe] read_opponent does not exploit a constant opponent (F2-1)
## Goal
In a simultaneous game where the opponent always plays A, we played CBBCABCB (3 of 8 best replies, 8/8 runs). Exploit simple patterns (constant, cycle, copy) for points (rule 9.1).
## Contract
strategies/read_opponent: after k=3 rounds with the same opponent move, play the best response; keep a mixed fallback.
Example: history opp A,A,A -> best reply C.
## Acceptance
python tests/alex/audit/f2_all.py scen: simultaneous scenario plays C in rounds 4-8 in 8/8 runs.
## From
alex (audit F2-1)
