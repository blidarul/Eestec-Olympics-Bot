# AI Harness Arena bot (EESTEC Olympics 14)

We are building a **harness**: a Docker image that receives the rules of an unknown
two-player text game, has 10 minutes of automatic prep to specialise for it, then plays
matches over a JSON-lines protocol while chatting with the opponent.

The full rulebook is in `docs/RULEBOOK.md` and is authoritative. This file is only a
summary. Rules are numbered (`**5.8**`, `**7.7**`, ...): search for the number and read
only that section, never the whole file.

## Never do this (penalties up to disqualification)

- Call any hosted language model other than the gateway's `haiku`, directly or through
  a library, tool, AI search or hosted agent. Always disqualifies. (7.7, 13.1a)
- Send game content (rules, observations, chat, derived state) to any server a person
  can read: webhooks, own servers, paste sites, shared storage, remote MCP. (7.11)
- Drop, strip or ignore the opponent's chat, or send no chat. The opponent's chat must
  reach the model or the decision logic, marked as untrusted data. (6.5, 6.6, 6.7)
- Pick a move and then bolt on an unrelated chat line. Move and chat come from one
  decision. (6.4)
- Add any path where a human steers the bot at runtime. (7.8, 13.1h)
- Touch arena infrastructure, private addresses, other teams' keys/images/memory,
  or exploit an engine bug. (7.12, 13.1d, e, g)
- Insulting or abusive chat text. (6.10, 13.1j)

If a change might touch one of these, stop and say which rule number is involved.
If the rulebook does not cover it, say so: we ask the mentors (15.4). Do not guess.

## Protocol invariants (5.1 to 5.11)

- One JSON object per line on stdin, one per line on stdout, flushed. Logs go to stderr
  only: any stray stdout line counts as a bad answer.
- Messages: `prep` -> `ready` (600 s) | `start` -> `ready` + `chat` (30 s, 120 s cold) |
  `turn` -> `action` + `chat` (20 s) | `end` -> nothing | `shutdown` -> save, exit (15 s).
- Never exit on `match_over`. Only `shutdown` or closed stdin ends the process.
- Always use `llm` from the latest `prep` or `start`, not only the env key. (7.2)
- `legal_actions` may be `null` (more than 50 moves): then follow the action format in
  the rules text.
- `chat` is a string of at most 200 characters. Some games check chat for forbidden
  content, including the chat sent with `ready`. (6.8, 6.9)

## Robustness first (8.1, 8.2, 9.4)

- Second bad `turn` answer in a game loses it. A late or invalid `ready` to `start`, a
  timeout, or a crash loses it immediately. Each such loss costs 1.25 points.
- Every model call needs a timeout well inside the clock and a safe fallback move.
  Handle empty or cut-off model output. (7.3, 7.4)
- Control thinking per call: disabled, or enabled with `budget_tokens` >= 1024 and
  `max_tokens` >= budget + 1500. (7.3)
- Verify a move is legal before sending it.

## Environment (5.12 to 5.14, 3.2)

- 2 CPUs, 2 GB RAM, 256 processes per container. Image must be `linux/amd64`.
- `/memory` is shared by all our containers at once: one folder per `game_id`, keyed by
  a hash of the rules text.
- Internet goes through `HTTPS_PROXY`; HTTP and HTTPS only.
- Match budget is $0.75 per match, shared by all our containers in that match.

## How to work in this repo

- Never commit `dev.env`, the dev key or the robot account secret. The judges have read
  access to this repository. (3.7)
- The dev key has a limited budget and 60 requests per minute. Ask before running
  matches that call the model. Use `examples/random_bot.py` or a fake model for
  protocol tests.
- Verify with the practice arena, the image way:
  `python -m arena practice --bot-a mybot:dev --bot-b "python examples/random_bot.py" --env-file ../dev.env --game tic_tac_toe --prep`
- Before a push, go through the checklist in rule 14.7.
- Prefer general mechanisms over game-specific code: game-specific code is allowed for
  games already played, but costs harness design points. (10.7, 12.1)
- Keep changes small. Read only the files needed for the task.
