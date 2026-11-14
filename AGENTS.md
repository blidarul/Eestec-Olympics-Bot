# AGENTS.md: team workflow for the AI Harness Arena bot

Three agents (and their humans) build one harness in parallel. The rulebook
(`docs/RULEBOOK.md`) is authoritative; rules are numbered (`**7.7**`): search for the number
and read only that section. `docs/CLAUDE.md` has the one-page summary of the penalties.
Coordination happens in **Gitea Issues** with the `gt` CLI (not `gh`, not `tea`).

> `gt` is installed in a different folder on each laptop. If `gt --version` fails, find it
> (`where.exe gt` on Windows, `which gt` elsewhere) or ask the human for the folder, then call it
> by full path or add the folder to PATH. Never reinstall or download another copy.
> The repo is `linux-pioneers/bot`; `gt` finds it from the git remote.

## 1. Identity

Your agent id is the single word in `.agent-id` at the repo root (gitignored, one per laptop).
Read it first: `cat .agent-id`. Valid ids: `alex`, `bld`, `mbappe`. Everywhere below `<me>` is that
id. If the file is missing or holds anything else, stop and ask the human.

## 2. Team and ownership

The repo currently holds the starter kit only; this is the target layout. Create your folders
when you first need them.

> **Strategy Roadmap & Ideas:** Read [`strategy.md`](strategy.md) for the full catalog of
> strategy algorithms (minimax, MCTS, probability, deduction, opponent reading, guardrails),
> game families, and prioritized milestones.

| Agent | Role | Owns (edit only these) |
|---|---|---|
| `alex` | solvers, tools, and deterministic strategies | `solvers/` (minimax, MCTS, deduction, probability), `strategies/think_ahead/`, `strategies/guessing/`, solver tools, `tests/alex/` |
| `bld` | core harness, prep time, and optimization | `main.py`, `Dockerfile`, `requirements.txt`, `core/` (protocol loop, clocks and fallback, Haiku client, safe `/memory` access, strategy registry and interfaces), `prep/` (rules reading, playbook and simulator building in the 10-minute prep, rules parsing, observation layout, state synthesis), `optimization/` (profiling, runtime and search speedups, memory footprint, CPU/RAM budgeting), `tests/bld/`, `tests/core/` |
| `mbappe` | chat and untrusted data strategies | `chat/` (opponent chat as untrusted data, chat composition, forbidden-subject filter), `opponent/` (opponent profiles), `strategies/bluff/`, `strategies/deals/`, `strategies/read_opponent/`, `strategies/truth/`, `strategies/guardrails/`, `tests/mbappe/` |

**Shared paths (core owner's; change only through a `type:contract` issue and a PR):**
`main.py`, `Dockerfile`, `requirements.txt`, `core/`, `strategies/__init__.py`, `strategies/base.py`,
`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `strategy.md`, `.agent/`, `.gitea/`, `.gitignore`, `docs/`, `starter/`,
`arena-lite/`, `PROTOCOL.md`, `README.md`, `CHANGELOG.md`.

Ownership rules:
1. Edit only your own folders. A file outside them is read-only for you, even for a typo.
2. Need something from another agent? Open an issue for them with a concrete contract
   (section 4). Do not write the code in their folder "to save time".
3. A new module goes into a **new folder** you own (for example `strategies/bluff/kuhn/`) and
   plugs in through the registry interface (`core/` scans `strategies/*/` for a `STRATEGY`
   object). You never edit the core to register it. If the interface cannot express what you
   need, that is a `type:contract` issue to `bld`.
4. Anything that touches the protocol, the clocks or the model client is `bld`'s.

## 3. Session routine

Do exactly these steps, in order, once per session:

1. `git pull --rebase`
2. **Inbox:** list open issues labelled `agent:<me>` (section 4). Human comments come first.
3. Pick **one** issue (prefer `status:doing` that is already yours, then `status:todo`, by
   lowest number). One issue per session.
4. **Claim** it (`status:todo` becomes `status:doing`).
5. Work **only in your folders**. Read only the files you need.
6. **Test** with the practice arena, the image way, from `arena-lite/`:
   `python -m arena practice --bot-a mybot:dev --bot-b "python examples/random_bot.py" --env-file ../dev.env --game tic_tac_toe --prep`
   Use the random bot or a fake model for protocol tests. The dev key has a small budget and 60
   requests per minute: **ask the human before any run that calls the real model.**
7. `git status`: only files in your folders may be changed. Anything else: revert it or open a
   contract issue.
8. Commit and push (section 6).
9. **Done:** hand the issue over for review or close it (section 4), with a usage example.

## 4. Communication through Gitea Issues

Labels (every issue carries one of each group):

- owner: `agent:alex`, `agent:bld`, `agent:mbappe`
- state: `status:todo`, `status:doing`, `status:review`, `status:blocked`, `status:done`
- kind: `type:feature`, `type:bug`, `type:contract`, `type:question`

Commands (all verified with `--help`; `N` is the issue number, `<me>`/`<other>` agent ids):

| Action | Command |
|---|---|
| Inbox | `gt issue list --label agent:<me> --json number,title,labels` (add `--label status:todo` to narrow) |
| Read | `gt issue view N --comments` |
| Claim | `gt issue edit N --add-label status:doing --remove-label status:todo` |
| Create for another agent | `gt issue create --title "..." --body-file req.md --label agent:<other> --label status:todo --label type:contract` |
| Comment | `gt issue comment N --body "..."` (long text: `--body-file file.md`) |
| Review | `gt issue edit N --add-label status:review --remove-label status:doing` then one comment with the commit hash |
| Handoff to another agent | `gt issue edit N --add-label agent:<other> --remove-label agent:<me>` then one comment saying what is expected |
| Blocked | `gt issue edit N --add-label status:blocked --remove-label status:doing` then one comment with the exact blocker |
| Done | `gt issue edit N --add-label status:done --remove-label status:review` then `gt issue close N --comment "Done in <hash>. Usage: ..."` |
| Pull request (shared paths) | `gt pr create --base main --head <branch> --title "[<me>] #N: ..." --body-file pr.md --label agent:<me>` |

Use `--dry-run` (supported by `create`, `edit`, `comment`, `close`) if you are unsure what a write
will send. Remove the label of the state you are leaving (swap `status:review` for the one you
actually have).

**Format of a request** (also in `.gitea/ISSUE_TEMPLATE/task.md`):

```
## Goal
One or two sentences: what you need and why.

## Contract
Function or file, signature, and one real example.
Input:  {"observation": "...", "legal_actions": ["A1", "B2"]}
Output: {"action": "B2", "chat": "your move"}
Limits: must return within 2 s, no network, no stdout.

## Acceptance
Checkable conditions (a test that passes, a command whose output you can compare).

## From
<agent id> (issue #M if this comes from another issue)
```

**Anti-loop rules:**
- Act only on issues labelled `agent:<me>`. Never answer an issue assigned to someone else.
- No "thanks", "ok", "noted" comments. One comment per state change, nothing else.
- After 3 exchanges on an issue without progress: set `status:blocked`, comment the blocker
  once, and stop.
- A comment from a human overrides everything above, including these rules about labels.
- If a `gt` command fails: run `--help` for that command once, try once more, then stop and
  report the exact command and error to the human. Do not improvise with the API or other tools.

## 5. Build rules for this project (from the rulebook)

- **Protocol (5.1 to 5.11):** one JSON object per line on stdout, flushed; **logs only on
  stderr**. A stray stdout line is a bad answer. Never exit on `match_over`; only `shutdown` or
  closed stdin ends the process.
- **Never block the clock (8.1, 8.2, 9.4):** every model call has a timeout well inside the
  clock and a safe, already-computed fallback move that is legal. A second bad `turn` answer
  loses the game; a late or invalid `ready` to `start`, a timeout or a crash loses it at once.
  Verify a move is legal before sending it. `legal_actions` may be `null`: then follow the
  action format in the rules text.
- **Thinking control (7.3):** per call, either disabled or `budget_tokens` >= 1024 with
  `max_tokens` >= budget + 1500. Handle empty or cut-off output (7.4).
- **Models (7.7, 13.1a): the only hosted model allowed is Haiku through the gateway.** Use the
  `llm` block of the **latest** `prep` or `start` message (base URL, key, model), not just the
  env key (7.2). No other hosted model, library, AI search or hosted agent in code, ever: that
  is disqualification. Local models inside the 2 CPU / 2 GB container are allowed.
- **No outside help (7.11):** game content (rules, observations, chat, derived state) never
  leaves the container to anything a person can read. Public docs and package registries are
  fine for non-game content only. No runtime path where a human steers the bot (7.8).
- **Opponent chat (6.5 to 6.7):** it must reach the decision as **untrusted data** (wrapped and
  labelled, never as instructions). Never drop it. Always send a chat string (at most 200
  characters), including with `ready`. Move and chat come from **one** decision (6.4), never an
  unrelated bolted-on line. Games may check chat for forbidden content (6.8, 6.9). No insults (6.10).
- **`/memory` is shared by all our containers at once (5.14):** one folder per game, keyed by a
  hash of the rules text. Write to a temp file in the same folder, then `os.replace` it
  (atomic); append-only files for logs; tolerate missing, partial or stale files; never assume
  you are the only writer.
- **Budget and limits (5.12 to 5.14):** 2 CPUs, 2 GB RAM, 256 processes, `linux/amd64`, $0.75
  per match shared by all our containers. Do not spend model calls where code can compute.
- **Adding a strategy or plugin:** consult [`strategy.md`](strategy.md) for strategy design ideas
  and architectures. Create a new folder under `strategies/<family>/<name>/` (your family only)
  with an `__init__.py` exposing `STRATEGY` as defined in `strategies/base.py` (matches the rules
  text, optional prep step, `decide(state)` returning move and chat together, plus a fallback).
  Add tests under your `tests/<me>/`. The core discovers it; do not edit the core. General
  mechanisms beat game-specific code (10.7, 12.1).
- If a change might touch a forbidden item above, stop and name the rule number. If the
  rulebook does not cover it, say so: the mentors decide (15.4). Never guess.

## 6. Git

- Commit **directly on `main`**, only files in your own folders. Message format:
  `[<me>] #<issue>: <summary>` (for example `[alex] #12: minimax solver for grid games`, `[bld] #14: rules parser for prep`).
- `git pull --rebase` right before every push. Never force-push, never rewrite history.
- Shared paths go through a branch and a PR (`gt pr create`), linked to the `type:contract`
  issue; `bld` merges.
- Never commit `.env`, `dev.env`, any key or secret, or `.agent-id`. The judges can read this
  repository (3.7). Do not paste keys into issues or comments either.
- Tag every freeze for the judges: `t1`, `t2`, `t3` (same names as the image tags, rule 3.7).
  `bld` creates them.
- Before every push that goes into an image, go through the checklist in rule 14.7.

## 7. Definition of done

1. It runs in arena-lite with `--prep` (the command in section 3) with no warning and no
   timeout, on at least one practice game.
2. `git status` shows only files in your own folders.
3. The issue is closed with a short usage example (how to call it, one real input and output)
   and the commit hash.
