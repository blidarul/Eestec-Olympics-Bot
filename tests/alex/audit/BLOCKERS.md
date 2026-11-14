# BLOCKERS (found by the audit; owner decides)

## B1 [FIXED in 532b019] strict-format `legal_actions: null` fallback sends illegal moves (rules 8.1, 9.4, 5.x action format)
- Evidence (image, 8/8 runs each): `audit_claim` (format `CLAIM R<row>-C<col>`): turn 1 `CLAIM R12-C12` ok, turn 2 `F6`, warning retry `G6`: second bad answer, game lost. `audit_qa` (`answer <text>`): `guess 50` (stub) then fallback `pass`: lost.
- Cause: `core/fallback.py:114-166`: format examples are used once, then numeric/word/grid-like/`pass` emergency list; the format in the rules is not reused. `action_format.regex` is None for every game.
- Owner: bld (core). Suggested fix: derive a template from the rules' ACTION FORMAT line at prep and let the fallback fill it (or keep re-using the example with the next unused parameters); verify with `python tests/alex/audit/f2_all.py games`.
- Draft: `issues/B1_strict_format_fallback.md`.

## B2 [FIXED in 855ff15] nim winning move lost when the observation layout is unusual (not a rule break)
- `solvers/precompute.py:460-472` regex miss on `Heaps: h1=3 h2=4 h3=5`. Owner alex. Draft: `issues/B2_nim_parse.md`.

## B3 [FIXED in 7f5948f] speech rule: `forbidden_terms` stays empty in the artifact (rules 6.8, 6.9)
- Evidence (image, main `6bf751d`): `audit_qa` rules say "never say the word harbor"; prep artifact `forbidden_terms: []`. Terms are only filled from model-written hooks/grammar (`core/hooks.py:77,106`); the stub writes none. Our chat stayed clean in 56 runs only because the stub chat is canned.
- Not proven either way with the real model (needs approval). Owner: bld (core/hooks). Candidate: a code-side keyword extraction from "never say/word ..." in the rules as a floor.
- B1 (strict format fallback) re-confirmed unchanged on `6bf751d`.

## Fix notes (X4, branch fix/audit-t2)
- B1 532b019: `core/actionfmt.py` parses the ACTION FORMAT line into template + regex + placeholder ranges (stored in artifacts["action_format"]); fallback fills it with unused valid values; `main.on_turn` gates every outgoing action (model, tool, fallback) on the regex; warning reason refines it. Tests: `tests/bld/test_action_format.py`. Image: `f2_all.py games` -> 48/48 runs, 0 problems (claim 8/8, qa 8/8), 0 warnings, 0 losses.
- B3 7f5948f: `core/forbidden.py` extracts terms from the rules (code, no model), merges model terms, adds variants (+ solvers/guard.py in prep); filter on ready chat, turn chat and action (replaced by a template value, never cut). Tests: `tests/bld/test_forbidden_terms.py`. Image: `f2_all.py b3` -> artifact has harbor/Harbor/harbors/h4rbor; 8 runs (4 spellings x 2 seats) with the stub saying them in chat and action: 0 problems, 0 speech breaks.
- B2 855ff15: `_heaps()` reads `h1=3`, `Row 1 has 3 stones`, `Heap 1 is 7`; also fixed `loser 0` being read as misere. Tests in `tests/alex/test_precompute.py`.
- Note: the f2 scenario `nim_win_move_v2` (heaps 1,3,5,7) is a lost position (nim-sum 0): no move can give nim-sum 0, so that scenario can never pass. Use heaps like 1,3,5,6.
