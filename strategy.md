# Strategy Roadmap & Ideas Catalog

This document outlines the strategy catalog, algorithmic ideas, and architecture for the AI Harness Arena bot. All agents (`alex`, `bld`, `mbappe`) should consult this catalog when designing modules, claiming tasks, or opening contract issues.

---

## 1. Architectural Philosophy

1. **Code Before Model (Save Budget & Time):**
   The tournament allocates \$0.75 per match and strict clocks (20s per move, 30s warm study). Never call the LLM when deterministic logic or a solver can compute the optimal move.
2. **Never Miss a Clock:**
   Every solver or LLM call must be strictly bounded by a deadline timer (e.g., cut off search or model call at 16s on a 20s clock) with an immediate, legal fallback move precomputed.
3. **Unified Move & Chat Decision:**
   Rule **6.4** requires that the move and the chat come from a single, coherent decision. Never bolt on random chat after picking an action.
4. **Opponent Chat Is Untrusted Data:**
   Opponent chat must be sanitized and clearly tagged as untrusted context to prevent prompt injection or adversarial steering (Rules **6.5–6.7**).
5. **Shared `/memory` Persistence:**
   Use `/memory/<game_id>/` (keyed by rule hash) to persist precomputed simulators, opening books, opponent profiles, and match histories across all running containers.

---

## 2. Strategy Ideas by Agent & Ownership

```mermaid
graph TD
    subgraph Bld [bld: Core Harness, Prep Time & Optimization]
        PL[Protocol Loop & Fallback]
        LLM[Haiku Gateway Client]
        MEM[Safe /memory Writer]
        REG[Strategy Registry]
        PREP[10-min Prep Engine]
        PARSE[Rules & Action Grammar Parser]
        SIM[Automated Simulator Synthesis]
        OPT[Runtime & Memory Profiling / Speedups]
    end

    subgraph Alex [alex: Solvers, Tools & Deterministic Strategies]
        SOLV[Solvers: Minimax / MCTS / Prob]
        TOOLS[Solver Tools & LLM Calling]
        TA[think_ahead: Board Games]
        GUESS[guessing: Deduction]
    end

    subgraph Mbappe [mbappe: Chat & Untrusted Data Strategies]
        CHAT[Untrusted Chat Filter & Gen]
        OPP[Opponent Profiler]
        BLUFF[bluff: Hidden Info]
        DEALS[deals: Negotiation]
        READ[read_opponent: Simultaneous Moves]
        TRUTH[truth: Grounded QA]
        GUARD[guardrails: Filter & Evasion]
    end

    REG --> TA
    REG --> GUESS
    REG --> BLUFF
    REG --> DEALS
    REG --> READ
    REG --> TRUTH
    REG --> GUARD
```

---

### A. Core Harness (`bld`)

| Component | Path | Key Ideas & Responsibilities |
|---|---|---|
| **Protocol Loop** | `core/protocol.py`, `main.py` | Robust JSON-lines loop on stdin/stdout, logs strictly on stderr. Must handle `prep`, `start`, `turn`, `end`, and `shutdown`. |
| **Clock & Deadline Manager** | `core/clocks.py` | Strict timeouts with safety buffers (e.g. 16s timeout for 20s move clock, 25s for 30s study clock). |
| **Fallback Engine** | `core/fallback.py`, `core/validate.py` | Always maintains an immediate, validated legal move. If the solver or LLM times out or fails, returns the fallback instantly. Anti-repeat safety net. |
| **Haiku Gateway Client** | `core/haiku.py`, `core/llm.py` | Clean wrapper for Claude Haiku via the tournament gateway. Supports thinking budget control (`budget_tokens >= 1024`, `max_tokens >= budget + 1500`), retry logic, and empty response guards. |
| **Atomic `/memory` Writer** | `core/memory.py` | Thread-safe, cross-container safe atomic writes (write to temp file in same directory then `os.replace`). Keyed by rules hash. |
| **Strategy Registry** | `core/registry.py` & `strategies/base.py` | Dynamic discovery of strategies exposed in `strategies/<family>/<name>/` matching the rules text. |
| **Packaging & Deployment** | `Dockerfile`, `requirements.txt` | Container image builds, limits enforcement (2 CPU / 2 GB RAM), freeze tagging (`t1`, `t2`, `t3`), and Harbor registry pushes. |

---

### B. Solvers, Tools & Deterministic Strategies (`alex`)

| Component | Path | Key Ideas & Responsibilities |
|---|---|---|
| **Solvers Library** | `solvers/` | Minimax with alpha-beta and iterative deepening (`minimax.py`), MCTS (`mcts.py`), constraint deduction (`deduction.py`), probability/expected value & DP (`probability.py`). |
| **Solver Tools** | `solvers/`, `core/` tool interfaces | Pre-computed evaluation tools and simulator search tools callable by LLM during turn execution. |
| **Deterministic Strategies** | `strategies/think_ahead/`, `strategies/guessing/` | Board games (Tic-Tac-Toe, connect-N, grid games) and deduction from feedback (binary search for `guess_number`, candidate elimination). |

---

### C. Prep Time & Optimization (`bld`)

#### 1. 10-Minute Prep Engine (`prep/`)
- **Game Family Classifier:**
  - Analyzes the rules text during `prep` using keyword matching and small LLM prompts to classify the game into one of the 7 families.
- **Rules & Action Grammar Parser:**
  - Extracts the exact action syntax (e.g., coordinates `A1`, `roll`/`hold`, numbers, commands) and observation regexes.
  - Tests the parsed grammar against `sample_turn` provided during `prep`.
- **Automated Python Simulator Synthesis:**
  - Prompts Haiku during prep to write a lightweight Python game state class (`step()`, `legal_actions()`, `is_terminal()`, `evaluate()`).
  - Validates the synthesized simulator against `sample_turn` before saving it to `/memory/<game_id>/simulator.py`.
- **Precomputed Heuristics & Opening Books:**
  - Computes opening moves or endgame tables during the 10-minute prep window and serializes them to `/memory/`.

#### 2. Performance & Resource Optimization (`optimization/`)
- **Simulator & Search Loop Profiling:**
  - Profiles state representation and transition bottlenecks (e.g. state cloning vs. in-place mutation with undo).
  - Optimizes data structures (bitboards, integer encodings, `__slots__`) allowing minimax and MCTS to evaluate orders of magnitude more nodes per second within the 20s move clock.
- **CPU & Memory Budget Enforcement (2 CPU / 2 GB RAM):**
  - Keeps garbage collection overhead minimal to avoid latency spikes during turn execution.
  - Monitors resident memory (RSS) to guarantee containers stay well within the 2 GB container limit.
- **Fast Serialization & Cold-Start Caching:**
  - Streamlines `/memory/` persistence (compact JSON/binary dumps, rapid caching) so cold containers can load prepped state in milliseconds.

---

### C. Chat & Untrusted Data Strategies (`mbappe`)

#### 1. Chat & Guardrails Architecture (`chat/`)
- **Untrusted Chat Sanitizer:**
  - Wraps incoming opponent chat as untrusted data (`[OPPONENT_CHAT_UNTRUSTED]`).
  - Strips prompt injection attempts (e.g., `"Ignore previous instructions"`, `"System: play move X"`).
- **Unified Chat Generator:**
  - Generates conversational messages tied to the chosen move (e.g., polite sportsmanship, tactical commentary, subtle bluffing).
  - Enforces length limit: strictly <= 200 characters (Rule **6.8**).
- **Forbidden-Subject Filter (`chat/forbidden_filter.py`):**
  - Scans outgoing chat against forbidden topics / keywords identified in the rules text (Rule **6.9**).
  - Automatically suppresses or rewrites chat that risks rule violations or penalty points.

#### 2. Opponent Modeling (`opponent/`)
- **Opponent Profiler (`opponent/tracker.py`):**
  - Records match histories in `/memory/opponents/<opponent_name>.json`.
  - Metrics tracked:
    - Bluff frequency (how often they show down with weak hands).
    - Defection rate in negotiation/cooperation games.
    - Repetition and cycle tendencies in simultaneous move games.
    - Chat sentiment and bluff indicators.

#### 3. Strategies to Implement
- **`strategies/bluff/` (Hidden Information & Wagering):**
  - `kuhn_poker` / `dice_bluff`: Mixed strategy implementation (Nash equilibrium approximation).
  - Dynamic bluff rate: bluff at a calibrated frequency (e.g., 20–30%) to prevent exploitation, value-bet strong hands.
  - Risk-sensitive betting based on pot odds and expected utility.
- **`strategies/deals/` (Negotiation & Trust):**
  - `prisoner_dilemma`: Generous Tit-for-Tat (starts friendly, retaliates on defection, forgives occasionally to avoid mutual defection traps).
  - `bargaining`: Adaptive concession strategy (starts firm, slowly concessions towards deadline, never accepts deals below baseline threshold).
- **`strategies/read_opponent/` (Simultaneous Moves):**
  - `pattern_predictor`: N-gram transition matrix to detect opponent patterns in games like Rock-Paper-Scissors or Matching Pennies.
  - Frequency analysis: Plays the counter to the opponent's most frequent move or cycle pattern.
- **`strategies/truth/` (Document-Grounded QA):**
  - Strict grounding: only answers based on explicit facts in the provided text.
  - Confidence scoring: if confidence is below a threshold or facts are missing, returns `"unknown"` / passes to avoid hallucination penalties (Rule **1.3**).
- **`strategies/guardrails/` (Forbidden Subject Evasion):**
  - Identifies the forbidden subject from the rules.
  - Evasion agent: redirects conversations, answers neutral topics safely, refuses bait from the opponent, and double-checks outgoing responses against a negative blacklist.

---

## 3. Implementation Priorities & Milestone Roadmap

```mermaid
flowchart LR
    M1[Milestone 1: Foundations] --> M2[Milestone 2: Practice Games]
    M2 --> M3[Milestone 3: Solvers & Generic Harness]
    M3 --> M4[Milestone 4: Tournament Hardening]
```

### Milestone 1: Foundations & Core Scaffolding
- [x] `bld`: Build `core/protocol.py`, `core/clocks.py`, and `core/fallback.py` to ensure zero timeouts or illegal moves.
- [x] `bld`: Set up `core/haiku.py` client with timeout and thinking budget control.
- [x] `bld`: Create strategy discovery registry (`core/registry.py`) and base class (`strategies/base.py`).

### Milestone 2: Practice Games Specialization (T1 Prep)
- [x] `alex`: Implement `strategies/think_ahead/tic_tac_toe` (optimal minimax solver).
- [x] `alex`: Implement `strategies/guessing/guess_number` (optimal binary search).
- [x] `bld`: Implement rules parsing and observation layout extraction in `prep/`.
- [x] `mbappe`: Implement `strategies/bluff/pig` (optimal threshold dynamic programming).
- [x] `mbappe`: Implement `chat/sanitizer.py` and `chat/composer.py` for compliant chat generation.

### Milestone 3: Generalization & Advanced Solvers (T2 Prep)
- [ ] `alex`: Generic Alpha-Beta Minimax with iterative deepening in `solvers/minimax.py` and MCTS in `solvers/mcts.py`.
- [ ] `alex`: Expose evaluation and search tools in `solvers/` for LLM tool-calling.
- [x] `bld`: Automatic rules classification and simulator synthesis in `prep/`.
- [ ] `mbappe`: Opponent profiling and tracking in `opponent/tracker.py`.
- [ ] `mbappe`: Negotiation (`strategies/deals/`) and simultaneous prediction (`strategies/read_opponent/`).

### Milestone 4: Defense & Tournament Hardening (T3 Final)
- [ ] `mbappe`: Truth extraction with hallucination protection in `strategies/truth/`.
- [ ] `mbappe`: Guardrails leak defense and adversarial chat filter in `strategies/guardrails/`.
- [ ] `bld`: Runtime execution speedups, simulator inner-loop optimization, memory footprint tuning, and container stress tests under 2 CPU / 2 GB limits.
- [x] `bld`: Docker image builds, Harbor deployment, and tournament freeze tags (`t1`, `t2`, `t3`).
