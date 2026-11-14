# [bld] Cold container plays generic without search (G3)
## Goal
A container with empty /memory (pig cold) plays model-only, no simulator or tool. Rule 4.3 gives 120 s at start: build or load the simulator on demand.
## Contract
At start, if no artifacts for the rules hash: run the prep pipeline's cheap stages (parse, classify, simulator) within a 60 s deadline, still answer ready first in time.
Limits: ready within 30 s (120 s cold), no stdout.
## Acceptance
Cold pig run shows strategy=search and source=tool; ready latency logged.
## From
alex (audit F1 G3)
