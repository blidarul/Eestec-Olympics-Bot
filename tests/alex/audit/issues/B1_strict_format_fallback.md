## Goal
The fallback must never send an illegal move when `legal_actions` is null and the rules give a strict format (blocker, rules 8.1, 9.4).

## Contract
Function: `core.fallback.fallback_action(legal=None, artifacts, rejected, avoid_also)`.
Input: rules "exactly `CLAIM R<row>-C<col>`", observation lists claimed cells, `rejected="F6"`.
Output: a string that matches the format (e.g. `CLAIM R11-C12`), never `pass`/`F6`.
Limits: no model call, under 50 ms.

## Acceptance
`python tests/alex/audit/f2_all.py games`: `audit_claim` and `audit_qa` show 0 "SECOND BAD ANSWER" (today 8/8 each).

## From
alex (audit F2)
