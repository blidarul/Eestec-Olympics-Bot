# PHASES (T2 plan, who does what)

| Phase | Content | Owner | Status |
|---|---|---|---|
| 0 | protocol safety, per-game fallback, validator, router | alex (issue opened) | [ ] |
| 1 | Wordle Duel specialist | bld (issue opened) | [ ] |
| 2 | Mini Poker Kuhn + Leduc: precomputed CFR table, limited exploitation | mbappe (strategies/bluff/poker) | [ ] next |
| 3 | Connect Four C engine | bld (issue opened) | [ ] |
| 4 | Colonel Blotto: predictor, best response, mixed fallback | mbappe (strategies/read_opponent/blotto) | [ ] |
| 5 | integration, Docker, 14.7 checklist, report, t2 freeze | alex (issue opened) | [ ] |

Decisions and next steps
- The repo keeps its layout (core/, strategies/, prep/, chat/); the plan's `harness/` and `specialists/` folders are not created (they are alex's files).
- Chat: human persona, a bit more talkative (1-3 sentences), still behind the same walls.
- Next: Phase 2, one phase per session (CFR solver in numpy at build, table in strategies/bluff/poker/, opponent frequencies, tests).
