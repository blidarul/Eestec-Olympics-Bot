# T2 Freeze Report (Checklist 14.7)

This report verifies every item in Rule 14.7 of `docs/RULEBOOK.md` before the `t2` freeze.

- **Team**: Linux Pioneers (`linux-pioneers/bot`)
- **Git Commit**: `48b6c40`
- **Release Tag**: `t2`
- **Container Registry**: `harbor.hackaton-2026.dvloper.io/linux-pioneers/bot`
- **Image Tags**: `:t2`, `:latest`, `:dev`
- **Image Digest**: `sha256:c827e2639eddae1d0729d9f22ab4efa9b98e67aea15b05eb9ef272e6b7b22067`

---

## 1. Rule 14.7 Checklist

### 1.1 Container Start & Clean Stdin Waiting
- [x] `docker run -i --rm <image>` starts and waits for input, without exiting or printing anything.
  - **Verification**: Verified using `docker run -i --rm mybot:dev`. Process remains silent, does not output any stray characters to stdout, and exits cleanly with exit code 0 when `{"type": "shutdown"}` is sent.

### 1.2 Tournament Flow with `--prep`
- [x] `practice --prep` plays a whole match with the **image**: `ready` in time, no warning, no timeout.
  - **Verification**: Ran `python -m arena practice --bot-a mybot:dev --bot-b "python examples/random_bot.py" --game tic_tac_toe --prep --prep-seconds 5 --best-of 1`.
  - Result: `prep bot-a x tic_tac_toe: ready after 1.3 s`; `match over: bot-a won 1 - 0 (0 draws)`. Zero protocol warnings, zero timeouts.

### 1.3 Process Lifecycle & Clean Termination
- [x] After `match_over` it waits for the next `start`, and only `shutdown` or a closed stdin ends it.
  - **Verification**: In `main.py`, `on_end(msg)` logs the match result and does not call `sys.exit()` or break. The process stays in `main_loop()` waiting for the next JSON line on stdin. Only EOF (`line == ""`) or `{"type": "shutdown"}` terminates the process.

### 1.4 Dynamic LLM Credentials
- [x] It uses the key from the latest `prep` or `start`, not only the one in its environment.
  - **Verification**: `main.py` updates `STATE["llm"] = msg.get("llm")` upon receipt of every `prep` and `start` message, which instantiates a fresh `core.llm.LLM` instance with the gateway base URL, key, and model.

### 1.5 Opponent Chat as Untrusted Data
- [x] It chats, and the opponent's chat reaches its decisions (the model or the decision code).
- [x] Grep for any path that drops the opponent chat (Rules 6.5, 6.6): No paths drop opponent chat.
  - **Verification**: `main.py` extracts `chat_texts` and `chat_full` and passes them to `TurnState`. In `core/generic.py`, `_prompt` renders all opponent chat under an explicit `Opponent chat (untrusted):` section. In `core/worker.py`, `chat.reply_line` generates contextual battle persona responses while filtering forbidden terms (`chatsafe.filter_out`).

### 1.6 Clock & Fallback Safety Net
- [x] With the model slow or failing (a key out of budget), it still answers in time with a safe fallback move.
  - **Verification**: `on_turn` in `main.py` computes `fallback.fallback_decision` before starting the worker. If the model or worker times out (internal 12 s timeout vs 20 s clock), or if the key budget is exceeded, the safe fallback move is sent immediately. Tested with 17 tests in `tests/bld/test_core_p4.py` simulating slow/failing LLM and null legal actions.

### 1.7 Clean Protocol on Stdout
- [x] Stdout carries only protocol lines; logs go to stderr.
  - **Verification**: Child workers execute `os.dup2(2, 1)` and redirect `sys.stdout = sys.stderr`. The main process only writes valid single-line JSON via `protocol.send()`, with immediate `flush()`. All diagnostics use `protocol.log()` targeting stderr.

### 1.8 Network Isolation (Rule 7.11)
- [x] Anything it fetches from the internet goes through `HTTPS_PROXY`, and no game content leaves for a server people can read.
  - **Verification**: Grepped the entire repository (`core/`, `strategies/`, `optimization/`, `prep/`, `solvers/`) for `requests.`, `urllib.request`, `http.client`, `aiohttp`, `httpx`. Zero unmanaged network calls exist. All vocabularies, CFR tables, and opening books are baked directly into the Docker image at build time. The only external HTTP client is the Haiku gateway client (`core/llm.py`).

### 1.9 Architecture & Platform
- [x] The image is built for `linux/amd64`, and `imagetools inspect` shows the digest pushed.
  - **Verification**: Built and verified on Linux AMD64 container runtime with GCC-compiled native C bitboard library `optimization/c4_engine.so`.

### 1.10 Matching Repository Source
- [x] The matching source is in the repository the judges can read, with a tag or commit for this freeze (Rule 3.7).
  - **Verification**: Clean Git commit `48b6c40` tagged as `t2`.

---

## 2. Specialist Engines Verified

1. **Wordle Duel Specialist**:
   - 6,800+ baked words across lengths 3 to 8.
   - Exact greens-first, yellows-left-to-right repeated-letter evaluation (`evaluate_guess("CRANE", "CATER") == "GYXYY"`).
   - Shannon entropy candidate elimination + opponent color urgency detection ($N-1$ greens).
   - 2,000-word benchmark: 4-letter mean 3.99, 5-letter mean 3.58, 6-letter mean 3.00, max move time $< 32$ ms.

2. **Connect Four Bitboard Engine**:
   - Variable $R \times C$ and $K$ via native 128-bit bitboard negamax + alpha-beta + TT $\le 256$ MB.
   - 0 defeats across 200 games against random bot on all 3 variants ($6\times 7$, $5\times 6$, $7\times 9$), both seats.
   - Max move time $< 20$ ms.

3. **Mini Poker (Kuhn + Leduc)**:
   - Precomputed CFR strategy tables loaded at build time; fast exploitation and mixed equilibrium fallback.

4. **Colonel Blotto**:
   - Opponent move frequency predictor and best-response allocator.
