# arena-lite

The same match engine we run in the tournaments, with the **3 practice games**. Use it to run your
bot against itself, an older version of itself, or the random example bot, exactly the way the arena will
run it: same protocol, same clocks, same rules (one warning, then out: the second illegal action, invalid JSON
or wrong message type in a game loses it; a timeout or a crash loses it at once).

Requirements: Python 3.10+ (standard library only) and, for image mode, Docker.

## Run it

From this folder (`arena-lite/`):

```bash
python -m arena practice --list                      # the practice games and their variants

# two random bots, best of 3, random practice game for each game
python -m arena practice --bot-a "python examples/random_bot.py" --bot-b "python examples/random_bot.py"

# your bot as a local command, with your team's dev key, on one game, short clocks
python -m arena practice --bot-a "python ../starter/main.py" --bot-b "python examples/random_bot.py" \
    --env-file ../dev.env --game tic_tac_toe --study 60 --move 20

# the prep phase: one container, one game's rules, `prep`, wait for `ready` (then shutdown)
python -m arena prep --bot "python ../starter/main.py" --game tic_tac_toe --env-file ../dev.env --seconds 600
python -m arena prep --bot "python ../starter/main.py" --game tic_tac_toe --show     # just print the message

# the tournament flow: prep both bots once per game (warm containers), then play the match with them
python -m arena practice --bot-a mybot:dev --bot-b "python examples/random_bot.py" --env-file ../dev.env \
    --game tic_tac_toe --prep --prep-seconds 300

# your bot as a Docker image (what we run in the tournament)
docker build -t mybot:dev ../starter
python -m arena practice --bot-a mybot:dev --bot-b "python examples/random_bot.py" --env-file ../dev.env
```

On Windows use `py` or `python` (whichever starts Python 3), and keep the quotes around commands.

`--env-file` is a text file with your dev credentials:

```
LLM_BASE_URL=http://<gateway host>:4000/v1
LLM_API_KEY=sk-...your team dev key...
LLM_MODEL=haiku
```

## How a bot is started

- `--bot-a` / `--bot-b` is either a **command** (anything with a space, or a `.py`/`.exe`/... file) or a
  **Docker image** (a single word like `mybot:dev`). Force it with a prefix: `cmd:mybot` or `image:mybot`.
- **Command mode**: the process gets `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `TEAM_ID` and `MEMORY_DIR`
  in its environment (from `--env-file`).
- **Image mode**: `docker run -i --rm --cpus 2 --memory 2g --pids-limit 256 -v memory/<bot>:/memory -e ... <image>`,
  the same limits as in the tournament. A gateway URL on `localhost` is rewritten to `host.docker.internal`
  so the container can reach it. `--network NAME` picks a docker network.
- The shared chat works as in the tournament: `chat` on your answers reaches the other bot in its next
  message (`"chat"` field) and lands in the replay.
- Without `--prep` the bot lives for the whole match (all games), with the cold study clock (120 s).
  When the match ends it gets `{"type": "shutdown"}`, its stdin is closed and it has 15 seconds to
  save to `/memory` and exit.
- With `--prep` it runs like the tournament: first one container per bot per game gets `prep` (that
  game's rules, `--prep-seconds`), then each game of the match is played by that game's warm
  container (study clock 30 s, `--warm-study`); `start` carries the match's key in `llm`. A bot that
  ignores `prep` simply gets a cold container for the game. The warm containers are shut down
  (`shutdown`) after the match.

## Options

| Option | Default | Meaning |
|---|---|---|
| `--game ID` | random | play only this practice game |
| `--best-of N` | 3 | games per match (ties go to up to 3 sudden-death games) |
| `--study S` / `--move S` | 120 / 20 | study clock per game (cold container) and move clock, in seconds |
| `--prep` / `--prep-seconds S` | off / 600 | prep each bot once per game first, then play with the warm containers |
| `--warm-study S` | 30 | study clock of a warm (prepared) container |
| `--seed N` | random | same seed + same match id = same games, variants and deals |
| `--name-a` / `--name-b` | bot-a / bot-b | names shown to the bots (`you` / `opponent`) |
| `--id ID` | p-&lt;timestamp&gt; | match id (file name of the replay) |
| `--quiet` | | print only the final result |

## What you get

- `results/practice/matches/<id>.json`: the full replay (rules, the full-information game state after
  every step, actions, comments, timings, results), the same format as the tournament replays.
- `results/practice/logs/<id>-bot-a.log`: everything your bot wrote to **stderr**, plus `[arena]` notes
  (starts, ignored stdout lines, kills). With `--prep` (and for `prep`) each warm container has its own log in
  `results/practice/logs/warm/<bot>--<game>.log`; `<id>-bot-a.log` then says which container played which game.
- `memory/<bot name>/`: the bot's persistent memory folder.

## Your own test games

The practice games don't cover every family. Write your own: a module in `arena/games/` with one
subclass of `arena.core.Game` (copy a practice game as a template), then run it with
`python -m arena practice --games-dir games --game <your id> ...`. Bluff, negotiation and
simultaneous-move test games are worth the effort.

## Env file and keys

Only `LLM_*` and `BOT_*` variables from `--env-file` reach your bot (`BOT_*` is for your own practice settings; in the tournament only the standard variables exist, so bake real settings into your image). When both practice bots use your dev key they share
its 60 requests/minute limit. In the tournament each bot gets its own per-match key ($0.75 budget, no
per-minute limit of ours), sent in `start["llm"]` (a warm container outlives matches: always use the latest); check any key's spend with `GET <LLM_BASE_URL without /v1>/key/info` and header
`Authorization: Bearer <key>`.

See `../PROTOCOL.md` for the message format.
