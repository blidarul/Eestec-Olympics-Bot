# [bld] Use the prep time for unknown games (G1)
## Goal
Prep takes 0.5-1.3 s of 600 s; nothing is calibrated or probed. Use it (self-play of the verified simulator, opponent-profile priors, model-written playbook) to win more (rules 9.1, 12.1).
## Contract
Prep stage that, within 540 s and with a deadline, runs self-play on the verified simulator and stores results in /memory/<game>/<hash>/. Output: new artifact key plus one line in the prep log.
Limits: stays inside 540 s, no stdout, $ budget per 7.5.
## Acceptance
Prep of pig and nim writes the new artifact; second prep reuses it (see G4); python -m arena practice --prep shows no warning.
## From
alex (audit F1, G1, G4)
