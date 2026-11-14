## Goal
`_heaps()` should find heap sizes in more layouts (`h1=3 h2=4`, `Row 1 has 3 stones`).

## Contract
`solvers.precompute._heaps(observation) -> (list[int] | None, first_label)`; `Heaps: h1=3 h2=4 h3=5` -> `[3,4,5]`.

## Acceptance
`nim_win_move` scenario in `f2_all.py scen`: answer has nim-sum 0 (today FAIL); add the layouts to `tests/alex`.

## From
alex (audit F2)
