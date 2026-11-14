# PHASES (T2 plan, who does what)

| Phase | Content | Owner | Status |
|---|---|---|---|
| 0 | protocol safety, per-game fallback, validator, router | alex (issue opened) | [ ] |
| 1 | Wordle Duel specialist | bld (issue opened) | [ ] |
| 2 | Mini Poker Kuhn + Leduc: precomputed CFR table, limited exploitation | mbappe (strategies/bluff/poker) | [x] done (see strategies/bluff/poker/PROGRESS.md) |
| 3 | Connect Four C engine | bld (issue opened) | [ ] |
| 4 | Colonel Blotto: predictor, best response, mixed fallback | mbappe (strategies/read_opponent/blotto) | [x] done (see strategies/read_opponent/PROGRESS_blotto.md) |
| 5 | integration, Docker, 14.7 checklist, report, t2 freeze | alex (issue opened) | [ ] |

Decisions and next steps
- The repo keeps its layout (core/, strategies/, prep/, chat/); the plan's `harness/` and `specialists/` folders are not created (they are alex's files).
- Chat: human persona, a bit more talkative (1-3 sentences), still behind the same walls.
- Phases 2 and 4 are done; 0, 1, 3, 5 wait for alex and bld (issues #38, #39).
