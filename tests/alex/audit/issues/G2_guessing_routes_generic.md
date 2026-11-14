# [alex/bld] Guessing family routes to generic, deduce never picked (G2)
## Goal
guess_number plays 100% through core/generic; registered strategy deduce is never selected, feedback model unverified with stub. Check with a REAL prep run, then route guessing to deduce if the feedback model verifies.
## Contract
Router returns strategy deduce for family guessing when artifacts.feedback verified=True; else generic. Example: guess_number turn -> decision log strategy=deduce.
## Acceptance
Decision log shows strategy=deduce on a real-model run; no illegal moves; same fallback ladder otherwise.
## From
alex (audit F1 G2; needs real-model budget)
