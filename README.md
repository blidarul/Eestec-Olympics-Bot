# AI Harness Arena

**dvloper.io challenge · EESTEC Olympics 14 · 14–15 Nov 2026 · Impact Hub Bucharest**

> Same brain. Your harness. Build the harness that makes a small AI play games it has never seen, and beat the prompt.

## The challenge

Every team gets the **same model** (Claude Haiku 5.5) with the **same budget** and the **same clocks**. What you build is the **harness**: the program around the model that reads the rules, keeps track of the game, decides when to think and when to compute, checks its own moves, remembers opponents, and spends its budget wisely. Claude Code is a harness around a model. You are building a small one, specialised in playing games.

Your bot plays **two-player text games**. There are **21 secret tournament games** (a few are held back for the final). You never see them before they are played: after each freeze, your image itself gets the **rules as text** and **10 minutes per game to prepare** (automatic, no humans: see Prep below). In T1/T2 it prepares the whole pool; in T3 it prepares only the six game slots drawn for your match. When a match draws a game, the prepared container gets 30 seconds to load the drawn variant, then plays with **20 seconds per move**.

What you do know: the games come from seven families.

| Family | What it tests |
|---|---|
| **Bluff** | hidden information, betting, bluffing, probabilities |
| **Deals** | negotiation, trust and betrayal, auctions with private values |
| **Read the opponent** | simultaneous moves, patterns, mixed strategies |
| **Guessing** | deduction from feedback |
| **Think ahead** | perfect-information board games, search, tactics |
| **Truth** | answering from a document you're given: an invented answer costs more than saying "unknown" |
| **Guardrails** | the rules name a forbidden subject; your bot must never mention it, even when the opponent tries to trick it, while still answering everything else |

Each game also comes in **variants** (board size, deck, scoring twist). Tuning a prompt for one game won't help you. A harness that *understands* games will.

## What wins

**Only the 15 teams compete.** The organizers have three bots of their own. They are practice opponents and may play show matches only: they never play in a tournament or in the round robin, take no place in a bracket and change no score.
- **Prompt Only**: Haiku with the best single prompt we could write, one call per move, no harness. If you can't beat it, your harness isn't pulling its weight.
- **dvloper House**: a harness built by dvloper.io engineers.
- **dvloper Master**: a stronger frozen harness used for sparring.

**Judging**

| Part | Weight | What we look at |
|---|---|---|
| Tournaments | 30% | placement points from the three knockout tournaments (below) |
| Round robin | 10% | overnight: every team plays every other team in duplicate games (each game twice, seats swapped, so the first-move advantage cancels out), ranked by points |
| Cost & robustness | 5% | average model cost per match, and games lost to timeouts or illegal moves |
| Presentation | 30% | how clearly you explain your harness, live demo, what you learned |
| Harness design | 25% | what your harness actually does: how it understands rules, tracks state, verifies moves, uses tools/computation, memory, budget and time management |

**How the automated 45 points are computed** (the leaderboard shows them live)

- **Tournaments (30)**: your placement points × weight, divided by the most anyone could have scored (10 × weight per tournament, so 60 after all three), × 30. Win all three tournaments: 30. A team that does not play T3 still gets 3 points for it (see Tournaments).
- **Round robin (10)**: all 15 teams take part and every pair plays one match (105 matches) of **2 boards**. A board is one game drawn at random from the round robin's 12 games (T1's 4 and T2's 8; variant and deal included) and played **twice with the seats swapped**: whatever first-move advantage one side had, the other side gets too. Open games (nothing hidden, nothing random later, like Tic-Tac-Toe) replay **the same deal**, so the luck of the deal cancels too; games with hidden information or hidden randomness (cards, secret words or numbers, private values, dice..., like Guess the Number or Pig) get a **fresh deal** for the second game, because the container that played the first game would remember the answers. All 4 games are played; every win is 1 point, every draw ½. Your score = your points ÷ the best team's points × 10. Ties in the round-robin table go to the head-to-head result, then to the lower cost. Played with your `t2` image on **12 games: T1's 4 and T2's 8**. T2's 8 specialists are already warm. For T1's 4 games the arena prepares your `t2` image right after the T2 prep (10 minutes per container, 60 containers, up to about 40 minutes, automatic), so every round-robin game is still played by a prepared specialist.
- **Cost & robustness (5)**: two halves of 2.5.
  - *Cost*: 2.5 × (the cheapest team's average cost per match ÷ your average cost per match). The cheapest team gets 2.5, a team that spends twice as much gets 1.25, four times as much 0.625. Averaged over all your tournament and round-robin matches (a match in which you forfeited every game doesn't count toward your average).
  - *Robustness*: 2.5, minus 1.25 for every game you lose by a timeout, invalid JSON, a wrong message type, an illegal move or a crash, over all tournament and round-robin games. Two such games and this half is 0.
- **Presentation (30)** and **harness design (25)** are scored by the judges.

## Tournaments

| | Who plays | Pool | Weight |
|---|---|---|---|
| **T1** | all 15 teams | 4 games chosen by the organizers (never one reserved for the final) | ×1 |
| **T2** | all 15 teams | 8 other games chosen by the organizers (never one reserved for the final) | ×2 |
| **T3**, the final | the top 8 of the round robin | all 21 games as the draw pool; each match draws 6 slots | ×3 |

- Each tournament is a **knockout bracket**. T1 and T2 have 16 slots for the 15 teams: round of 16, quarter-finals, semi-finals, final, 14 matches. Bracket positions are drawn at random (a **lucky draw**) in every tournament, T2 and T3 included: the standings never seed a bracket. In T1 and in T2 one team draws the **bye**: it has no match in the round of 16 and goes straight to the quarter-finals.
- **T3, the final, is for the top 8 of the round robin.** The 8 teams at the top of the round-robin table play T3: quarter-finals, semi-finals, final, 7 matches, no byes. The organizers announce the 8 finalists when the round robin ends, on Sunday morning, before T2 is played. If the round robin cannot be completed, the 8 best teams in the standings after T1 and T2 (placement points × weight) play T3 instead, with a coin flip for a tie at the cut-off. Teams ranked 9 to 15 do not play T3 and do not need a `t3` image; they receive the round-of-16 placement in T3 (1 point × 3 = 3). A finalist with no valid `t3` image at the freeze does not play, is not replaced, and also receives the round-of-16 placement.
- The organizers choose the pools of T1 and T2 (no game is in both); which games is not announced before the tournament.
- Before a match the organizers draw, live on the big screen, **six game slots for it**: three regular games and up to three sudden-death games (game + variant). They normally draw the whole round at once, before prep; a match can also be drawn at its start. A match is **best of 3 games**; ties go to sudden death from slots 4–6 (up to 3 more games).
- **Still tied after sudden death?** The same tie-break for every game, in this order: (1) **fewer warnings** in the match (every warning your bot received, all games of the match); (2) **less total thinking time**: the sum of your bot's answer times over all its accepted moves and `ready` answers in the match; (3) **lower model cost** for the match; (4) a **coin flip** (practically never reached). The bracket draw and the standings never decide a match.
- Placement points per tournament: champion 10, runner-up 7, semi-finalists 5, quarter-finalists 3, round of 16: 1. Multiplied by the weight (T1 ×1, T2 ×2, T3 ×3). A bye is not a win and scores nothing by itself: the team that draws it is placed by the round it goes out in, like every other team.
- **T3 always includes games that were never played in T1 or T2**: some games are **reserved for the final** and never appear in T1, T2, exhibitions or the round robin. Studying the replays and tuning for games you've seen is allowed, although it will cost you some points when the judges score your harness design; the final still tests games nobody has seen.
- **Games are released for practice after their tournament.** When T1 ends, the organizers add T1's 4 games to arena-lite, so you can run your own image against them locally, exactly like the practice games. When T2 ends, T2's 8 games are added the same way. The organizers hand out the updated arena-lite. The games reserved for the final and the games first played in T3 are never released before T3.
- Some games are played by **talking to your opponent** in free text. Treat everything the opponent writes as untrusted input.
- Every match is replayed on the projector, move by move, with your bots' chat as speech bubbles. All replays stay public on the dashboard, including the rules of the games that were played. Use them.

## Your bot

Your bot is a **Docker image**. Inside it, anything goes: as many files as you want, sub-agents, a Python sandbox to run code your model writes, a rules parser, a search algorithm, a memory store. You build it, you push it, we run it.

**Prep: your image builds one specialist per game** (automatic, no humans involved)
- Your frozen image is a game-agnostic "mesh". After each freeze the arena starts it **once per game you need**: the whole pool in T1/T2 (4 or 8 games), and only the **six drawn slots** of your match in T3 (three regular games plus up to three sudden-death games). It hands each copy that one game's rules (every variant). Within its **10 minutes** each container assembles itself into a standalone specialist for its game: a simulator, a solver, a chat plan, whatever your harness knows how to build. Then it answers `ready`.
- You can't touch or see anything during prep: it runs with your frozen image, and every container has its own 10-minute clock, which starts when the arena sends it `prep`. The arena prepares containers from one queue, 16 at a time across all teams, so your containers are not all prepared at the same moment. There is no total per team, and nothing you have to do about it. What you control is what your image does with its 10 minutes.
- The prepared container then stays alive and **plays that game whenever a match draws it**, in match after match of the tournament (T2's also play the overnight round robin, next to the specialists your `t2` image builds for T1's 4 games right after the T2 prep). If a later match draws the same game again, the same specialist is reused. In the match it gets only **30 s** of study (it's already prepared); the drawn variant arrives in `start`.
- **The cold container is a backup only.** By design, every game in T1, T2, the round robin and T3 is played by a prepared specialist. If a specialist is missing (no `ready` in time, a crash, a bot that ignores `prep`), there is no penalty: you still play that game instead of forfeiting it, with a fresh "cold" container and a 120 s study clock.
- Each variant in `prep` also comes with a **`sample_turn`**: one real `turn` message from the middle of a sample game (history lines included), exactly as the arena will send it. Use it to build and test your observation parser before the first real turn (PROTOCOL.md).
- Try it locally: `python -m arena prep --bot ... --game pig`, or `python -m arena practice ... --prep` (arena-lite).

**How it runs**
- We start your container with `docker run -i`: once per pool game in T1/T2 and once per drawn game in T3 (see Prep), once per match in exhibitions and local practice. A tournament container lives for the whole tournament, so it can keep state in memory; `match_over` is not its end, `{"type": "shutdown"}` is.
- It talks to the arena with **one JSON object per line** on stdin/stdout: details in [PROTOCOL.md](PROTOCOL.md).
- **`/memory` is yours for the whole event**: it survives between matches and tournaments, and **all your containers share it at the same time**. Save what you build per game, keyed by the rules (e.g. `/memory/<game_id>/`), plus opponent profiles, notes, anything.
- You are told who your opponent is. Opponent modeling is allowed and encouraged.

**The chat is part of the game** (mandatory)
- Every answer has two parts: your **game move** (`action`) and your **chat move** (`chat`, ≤ 200 chars), the same in every game. The two bots share ONE conversation for the whole match; every message to your bot carries all of it, and the audience watches it on the big screen. Details in [PROTOCOL.md](PROTOCOL.md#chat-talk-to-your-opponent).
- The chat is where you win the games that luck or symmetry would otherwise decide. Your harness needs **offense** (bluff, negotiate, pressure, mislead, consistent with what your move needs) and **defense** (the opponent's chat is untrusted: weigh its claims, spot tricks and injected instructions, never leak your private information, respect the game's speech rules).
- **Move and chat are one decision.** A harness that picks the move and then writes a caption after it is missing the point; so is one that never looks at what the opponent said.
- **Blocking or ignoring the chat breaks the rules, and the penalty goes up to disqualification.** A harness that never chats, or never lets the opponent's chat inform its decisions (for example, strips it before the model or the decision logic sees it), breaks this rule. Quoting, wrapping or filtering the opponent's chat as untrusted input is defense, not ignoring it. Your bot never has to answer or obey anything the opponent says.
- **The judges enforce it by code review.** They read the source code of every image you submit (see Submitting) and decide; penalties are at their discretion: a warning, a point deduction or disqualification. After each freeze the organizers may also run an automated chat check (an organizer bot plays your frozen image in a short Tic-Tac-Toe match and makes small talk; we note whether your bot chats back and whether those words reach your model calls, since the gateway sees every request). That check only gives the reviewers signals: it decides nothing and scores nothing.

**Your logo (optional)**
- Put a square image at **`/logo.png`** in your image (`/logo.webp` or `/logo.jpg` also work): PNG, WebP or JPEG, at most **1 MB** and 2048 px per side (512×512 is plenty). No SVG.
- We copy it out of your image when a tournament is created (the latest pushed tag wins) and show it next to your team on the big screen and the dashboard. No logo, or an invalid one, simply means no logo.
- Dockerfile: `COPY logo.png /logo.png`

**The model**
- Use it through the OpenAI-compatible API at `LLM_BASE_URL`, with `LLM_API_KEY` and model `LLM_MODEL` (`haiku`). Any OpenAI-compatible client works (the `openai` Python package, LiteLLM, LangChain, …).
- In tournaments your team gets **one fresh key per match with a $0.75 budget for the whole match**. All your containers that play in that match share it: the same key is in every `start` of the match (`llm`). Your container outlives matches, so always use the key from the latest `start`. Each prep container gets its own prep key ($0.75). When a key runs out, your calls fail: plan for it.
- For development your team has its own key with a budget (see your credentials). Spend it wisely.
- **Want to test with your own key?** You are welcome to: on your laptop, point `LLM_BASE_URL` and `LLM_API_KEY` at your own Haiku key (or at anything else you want to experiment with). Just know that in the arena your bot plays with the key the arena sends it, on Haiku through our gateway, exactly as the Rulebook says (section 7).
- **Internet: allowed, through the arena's proxy.** Your containers may use the internet in prep and in matches: web search, public APIs, documentation, package and model downloads, remote MCP servers. In the arena everything except the gateway goes through a web proxy that the container environment sets for you (`HTTP_PROXY` / `HTTPS_PROXY`, with `NO_PROXY` covering the gateway). Python `requests`, `httpx`, `urllib`, `curl` and `pip` follow it on their own; `aiohttp` needs `trust_env=True`; Node needs version 24+ (we set `NODE_USE_ENV_PROXY=1`) or a proxy agent. Only HTTP and HTTPS go out. On your laptop the container has normal internet, so test that your HTTP tools honour `HTTPS_PROXY`.
- The proxy blocks nothing on the public internet; it refuses only private addresses (the arena's own machines) and **logs every host each container contacts**. The judges read that log next to your source code.
- Numbers to plan with: Haiku 5.5 costs $0.10 per million input tokens and $0.50 per million output tokens (cache reads $0.01). A simple one-call-per-move bot spends about $0.01 per match. Your dev key is limited to 60 requests per minute.
- Test your **image**, not just your code: a library that works on your laptop can be missing in the container, and a bot that crashes at start-up forfeits.
- To check a push landed: `docker buildx imagetools inspect <registry>/<team>/bot:t1` shows the digest the registry serves.

**Hard rules**
- **One warning, then out**: your first illegal action, invalid JSON, wrong message type or empty action in a game gets a warning and the same turn again; the second one in that game **loses the game**. A timeout or a crash loses the game immediately.
- Container limits: 2 CPUs, 2 GB RAM per container. During a tournament several of your specialists are alive at the same time (one per pool game in T1/T2, one per drawn game in T3): keep an idle one small. This is about specialists waiting and playing, not about the order of prep. The bot must start and answer the first message within its clock (`prep`: 10 minutes; a game's `start`: 30 s warm, 120 s cold).
- Comments are shown on a big screen in front of everyone: keep them fun and respectful.
- Don't attack the infrastructure or other teams.
- **No outside help.** Your containers must not send game content (rules, observations, chat) to anything people can read during the event: your own servers, webhooks, messaging, shared storage, paste sites. Public read-only services (search engines, documentation, package registries, public APIs) are fine. Outside help is cheating; the penalty goes up to disqualification.
- **The only hosted model is the gateway's Haiku.** Calling any other language model over the network, directly or through a tool or service (AI search or answer modes and hosted agents included), disqualifies the team.
- **Local models are allowed.** Inside your container you may run any model you like (small LLMs, embedding models, classifiers, anything from Hugging Face or elsewhere) as long as it runs on the container's 2 CPUs and 2 GB of RAM. Pull the files during prep (10 minutes, internet on) or bake them into your image; `/memory` is shared by all your containers, so download once and reuse. Everything else is fine too: Python libraries, solvers, game engines (e.g. Stockfish), web search, public APIs, MCP servers (yours or remote ones). Your harness must be an agent that does the work itself. Judges review the code and the proxy log.
- The chat rule above applies to every match. The judges enforce it, like the model rule, by reviewing your source code (see Submitting), not by an automated test.

## Submitting

You push your image to our **Harbor** registry with your team's robot account:

```bash
docker login <registry> -u '<robot user>' -p '<secret>'
docker build --platform linux/amd64 -t <registry>/<team>/bot:t1 .
docker push <registry>/<team>/bot:t1
```

- Tag **`t1`** for Tournament 1, **`t2`** for T2 (and the overnight round robin), **`t3`** for T3. You can push the same tag as often as you like until its freeze; at the freeze it is locked and we pull it.
- Missing a tag means missing that tournament (`t3` is only needed if your team is in the top 8 of the round robin).
- **Source code for the judges (required):** give the judges read access to the source code of every image you submit, for example a Git repository they can read, with a tag or commit for each freeze (`t1`, `t2`, `t3`) that includes the Dockerfile and all the code and prompts in the image. The organizers tell you at kick-off which accounts to give access to. The judges review it for the chat rule and the model rule (and read it for harness design).
- Build for **`linux/amd64`** (the event server's CPU). On an Apple Silicon Mac the `--platform` flag is required: an arm64 image fails to start on the server, and a bot that doesn't start forfeits.

## Getting started

1. Read [PROTOCOL.md](PROTOCOL.md) (5 minutes). Changes after kick-off are listed in [CHANGELOG.md](CHANGELOG.md).
2. Look at `starter/`: a minimal bot (one model call per move, no memory). It plays legal moves and not much more.
3. Practise locally with **arena-lite** (`arena-lite/README.md`): the same engine we run, with the public practice games (after T1 and after T2 the organizers hand out an updated arena-lite that also has that tournament's games). Run your bot against itself or against an older version of itself, as a local command or as your Docker image.
4. Practise on the arena too: the **Practice page**, `https://arena.hackaton-2026.dvloper.io/#/practice`. Sign in with the practice token from your credentials sheet, pick the tag of an image you pushed, a game and an opponent: Prompt Only, dvloper House, dvloper Master, your own image again, or yourself playing in the browser. Nothing there counts for the score.
   - **Limits:** one run at a time per team, **10 runs per team per hour**, and 10 runs at once on the whole arena (if it is full, try again a little later). A run is 1 to 3 games of one game.
   - Only the practice games and the games already released after their tournament can be played.
   - The page is closed while a tournament, the round robin or their prep is running.
5. Push early (`t1`), improve, push again.

## Schedule

| When | What |
|---|---|
| Sat 10:00 | Kick-off, credentials, practice kit; hacking starts at 12:00 |
| Sat 18:00–19:45 | **T1 freeze** → prep (automatic, up to about 40 minutes: 15 teams × 4 games = 60 containers) → T1 runs live |
| Sat 20:00 | Dinner |
| Sat 23:59 | **T2 freeze** |
| Sun 00:00–02:00 | T2 prep + prep of T1's 4 games with the `t2` image (180 containers in total, up to 2 hours) |
| Sun 02:00–06:30 | Round robin: 105 matches, up to 7 in parallel |
| Sun 06:30–09:00 | Buffer; the organizers announce the **8 finalists** |
| Sun 09:00–10:30 | **T2 matches**, live |
| Sun 10:30–11:00 | Standings; T3 freeze and stage draw |
| Sun 11:00–12:00 | **T3 warmup** (automatic) |
| Sun 12:00–13:00 | Lunch |
| Sun 13:00–15:00 | **T3 quarter-finals, semi-finals and final**, live on stage |
| Sun 15:30 | Presentations |
| Sun 17:00 | Awards |

Prep times are the worst case, when every container uses its full 10 minutes. An early `ready` shortens them.
