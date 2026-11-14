# BLOCKERS (found by the audit; owner decides)

## B1 [F2] strict-format `legal_actions: null` fallback sends illegal moves (rules 8.1, 9.4, 5.x action format)
- Evidence (image, 8/8 runs each): `audit_claim` (format `CLAIM R<row>-C<col>`): turn 1 `CLAIM R12-C12` ok, turn 2 `F6`, warning retry `G6`: second bad answer, game lost. `audit_qa` (`answer <text>`): `guess 50` (stub) then fallback `pass`: lost.
- Cause: `core/fallback.py:114-166`: format examples are used once, then numeric/word/grid-like/`pass` emergency list; the format in the rules is not reused. `action_format.regex` is None for every game.
- Owner: bld (core). Suggested fix: derive a template from the rules' ACTION FORMAT line at prep and let the fallback fill it (or keep re-using the example with the next unused parameters); verify with `python tests/alex/audit/f2_all.py games`.
- Draft: `issues/B1_strict_format_fallback.md`.

## B2 [F2] nim winning move lost when the observation layout is unusual (not a rule break)
- `solvers/precompute.py:460-472` regex miss on `Heaps: h1=3 h2=4 h3=5`. Owner alex. Draft: `issues/B2_nim_parse.md`.
