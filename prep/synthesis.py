"""Automated, Parameter-Driven Simulator Synthesis for 10-Minute Prep.
Synthesizes lightweight, fast Python game simulators dynamically adapted to the discovered game mechanics.
Supports state reconstruction via parse(observation, seat) for verification and search.
Fully game-agnostic (Rules 10.7, 12.1).
Owned by agent `bld`.
"""
from __future__ import annotations

import os
import time
from typing import Any

from optimization.serializer import atomic_write_bytes
from .action_parser import ActionGrammar
from .classifier import GameClassification


def synthesize_simulator_code(
    classification: GameClassification,
    grammar: ActionGrammar,
    game_id: str,
) -> str:
    """Synthesize standalone, runnable Python simulator code parameterized by parsed grammar and rules."""
    family = classification.family
    params = grammar.parameters or {}

    if family == "grid_board":
        cols = grammar.grid_cols or 3
        rows = grammar.grid_rows or 3
        k = params.get("connect_k", min(cols, rows, 3))
        return f'''"""Adaptive Grid Simulator for {game_id} ({cols}x{rows}, connect {k})."""

class State:
    def __init__(self):
        self.cols = {cols}
        self.rows = {rows}
        self.k = {k}
        self.board = [None] * ({cols} * {rows})
        self.current = 0

    def legal_actions(self):
        if self.has_line(0) or self.has_line(1):
            return []
        actions = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r * self.cols + c] is None:
                    actions.append(f"{{chr(ord('A') + c)}}{{r + 1}}")
        return actions

    def step(self, action):
        import re
        clean = action.strip()
        m = re.search(r"([A-Za-z])\\s*(\\d+)", clean)
        if not m:
            return self
        col = ord(m.group(1).upper()) - ord('A')
        row = int(m.group(2)) - 1
        idx = row * self.cols + col
        if idx < 0 or idx >= len(self.board) or self.board[idx] is not None:
            return self

        new_state = State()
        new_state.board = list(self.board)
        new_state.board[idx] = self.current
        new_state.current = 1 - self.current
        return new_state

    def is_terminal(self):
        return len(self.legal_actions()) == 0 or self.has_line(0) or self.has_line(1)

    def has_line(self, seat):
        s_c, s_r, k = self.cols, self.rows, self.k
        b = self.board
        for r in range(s_r):
            for c in range(s_c):
                if b[r * s_c + c] == seat:
                    # Horizontal
                    if c + k <= s_c and all(b[r * s_c + (c + i)] == seat for i in range(k)):
                        return True
                    # Vertical
                    if r + k <= s_r and all(b[(r + i) * s_c + c] == seat for i in range(k)):
                        return True
                    # Down-right
                    if r + k <= s_r and c + k <= s_c and all(b[(r + i) * s_c + (c + i)] == seat for i in range(k)):
                        return True
                    # Down-left
                    if r + k <= s_r and c - k + 1 >= 0 and all(b[(r + i) * s_c + (c - i)] == seat for i in range(k)):
                        return True
        return False

    def evaluate(self, seat):
        if self.has_line(seat):
            return 1.0
        if self.has_line(1 - seat):
            return -1.0
        return 0.0

    def key(self):
        val = 0
        for i, cell in enumerate(self.board):
            if cell is not None:
                val ^= ((cell + 1) * 0x9E3779B97F4A7C15 + i * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        if self.current == 1:
            val ^= 0x94D049BB133111EB
        return val


def parse(observation: str, seat: int = 0) -> State:
    """Parse text observation into a State object matching current turn and board layout."""
    import re
    s = State()
    s.current = int(seat)

    mark_0 = "X"
    mark_1 = "O"
    m_marks = re.search(r"seat\\s+(\\d+)\\s+(?:and\\s+)?plays?\\s+([A-Za-z0-9])", observation, re.IGNORECASE)
    if m_marks:
        st = int(m_marks.group(1))
        mk = m_marks.group(2).upper()
        if st == 0:
            mark_0 = mk
            mark_1 = "O" if mk == "X" else "X"
        else:
            mark_1 = mk
            mark_0 = "X" if mk == "O" else "O"

    row_count = 0
    for line in observation.splitlines():
        line = line.strip()
        m_num = re.match(r"^(\\d{{1,2}})\\s+([A-Za-z0-9.\\s]+)$", line)
        if m_num:
            r = int(m_num.group(1)) - 1
            if 0 <= r < s.rows:
                tokens = [t for t in re.split(r"\\s+", m_num.group(2).strip()) if t in (mark_0, mark_1, ".", "-", "_")]
                if len(tokens) == s.cols:
                    for c in range(s.cols):
                        tok = tokens[c]
                        if tok == mark_0:
                            s.board[r * s.cols + c] = 0
                        elif tok == mark_1:
                            s.board[r * s.cols + c] = 1
                        else:
                            s.board[r * s.cols + c] = None
                    row_count += 1
        else:
            m_let = re.match(r"^([A-Za-z])[:\\s]+([A-Za-z0-9.\\s]+)$", line)
            if m_let:
                r = ord(m_let.group(1).upper()) - ord("A")
                if 0 <= r < s.rows:
                    tokens = [t for t in re.split(r"\\s+", m_let.group(2).strip()) if t in (mark_0, mark_1, ".", "-", "_")]
                    if len(tokens) == s.cols:
                        for c in range(s.cols):
                            tok = tokens[c]
                            if tok == mark_0:
                                s.board[r * s.cols + c] = 0
                            elif tok == mark_1:
                                s.board[r * s.cols + c] = 1
                            else:
                                s.board[r * s.cols + c] = None
                        row_count += 1

    if row_count == 0:
        raise ValueError("Could not parse grid board from observation")
    return s
'''

    elif family == "dice_push":
        target = params.get("target_score", 50)
        dice_count = params.get("dice_count", 1)
        snake_eyes = params.get("snake_eyes_reset", False)
        actions = grammar.discrete_actions or ["roll", "hold"]
        continue_candidates = {"roll", "draw", "push", "spin", "continue", "hit", "take"}
        stop_candidates = {"hold", "bank", "stop", "pass", "stand", "keep"}

        continue_act = next((a for a in actions if a.lower() in continue_candidates), actions[0])
        stop_act = next((a for a in actions if a.lower() in stop_candidates), actions[-1] if len(actions) > 1 else "pass")

        return f'''"""Adaptive Accumulator/Push-Your-Luck Simulator for {game_id} (target: {target}, dice: {dice_count})."""

class State:
    def __init__(self, target={target}):
        self.target = target
        self.banked = [0, 0]
        self.turn_total = 0
        self.current = 0
        self.continue_action = "{continue_act}"
        self.stop_action = "{stop_act}"

    def legal_actions(self):
        return [self.continue_action, self.stop_action]

    def step(self, action):
        import random
        new_state = State(self.target)
        new_state.banked = list(self.banked)
        new_state.turn_total = self.turn_total
        new_state.current = self.current

        if action.lower() == self.stop_action.lower():
            new_state.banked[self.current] += self.turn_total
            new_state.turn_total = 0
            new_state.current = 1 - self.current
        else:
            # Sample random dice rolls
            rolls = [random.randint(1, 6) for _ in range({dice_count})]
            ones = rolls.count(1)
            if {str(snake_eyes)} and ones == 2:
                new_state.banked[self.current] = 0
                new_state.turn_total = 0
                new_state.current = 1 - self.current
            elif ones > 0:
                new_state.turn_total = 0
                new_state.current = 1 - self.current
            else:
                new_state.turn_total += sum(rolls)
        return new_state

    def is_terminal(self):
        return max(self.banked) >= self.target

    def evaluate(self, seat):
        return float(self.banked[seat] - self.banked[1 - seat])

    def key(self):
        return (self.banked[0] << 32) ^ (self.banked[1] << 16) ^ (self.turn_total << 2) ^ self.current


def parse(observation: str, seat: int = 0) -> State:
    """Parse accumulator observation into a State object."""
    import re
    s = State()
    s.current = int(seat)
    m_bank = re.search(r"Banked:\\s*you\\s*(\\d+),\\s*opponent\\s*(\\d+)", observation, re.IGNORECASE)
    if m_bank:
        you_b = int(m_bank.group(1))
        opp_b = int(m_bank.group(2))
        s.banked = [you_b if i == seat else opp_b for i in range(2)]
    else:
        m_list = re.search(r"banked[:\\s]+\\[?(\\d+)[,\\s]+(\\d+)\\]?", observation, re.IGNORECASE)
        if m_list:
            s.banked = [int(m_list.group(1)), int(m_list.group(2))]

    m_turn = re.search(r"Turn total:\\s*(\\d+)", observation, re.IGNORECASE)
    if m_turn:
        s.turn_total = int(m_turn.group(1))
    return s
'''

    elif family in ("deduction", "guessing"):
        lo = grammar.numeric_min if grammar.numeric_min is not None else 1
        hi = grammar.numeric_max if grammar.numeric_max is not None else 100
        prefix = grammar.numeric_prefix or "guess "
        return f'''"""Adaptive Deduction & Interval Search Simulator for {game_id} (range: {lo}-{hi})."""

class State:
    def __init__(self, lo={lo}, hi={hi}, tried=None):
        self.lo = lo
        self.hi = hi
        self.prefix = "{prefix}"
        self.current = 0
        self.tried = set(tried or [])

    def legal_actions(self):
        lo, hi = self.lo, self.hi
        if lo <= hi:
            mid = (lo + hi) // 2
            cand = f"{{self.prefix}}{{mid}}".strip()
            if cand not in self.tried:
                return [cand]
            # Search nearest untried candidate within current interval
            for offset in range(1, max(hi - mid, mid - lo) + 1):
                for g in (mid + offset, mid - offset):
                    if lo <= g <= hi:
                        c = f"{{self.prefix}}{{g}}".strip()
                        if c not in self.tried:
                            return [c]
        # Fallback to any untried candidate in full range {lo}..{hi}
        for n in range({lo}, {hi} + 1):
            c = f"{{self.prefix}}{{n}}".strip()
            if c not in self.tried:
                return [c]
        return [f"{{self.prefix}}{{lo}}".strip()]

    def step(self, action):
        new_tried = set(self.tried)
        new_tried.add(str(action).strip())
        s = State(self.lo, self.hi, new_tried)
        s.current = 1 - self.current
        return s

    def is_terminal(self):
        return self.lo >= self.hi or len(self.tried) >= min(30, max(1, {hi} - {lo} + 1))

    def evaluate(self, seat):
        return 1.0 if self.lo == self.hi else 0.0

    def key(self):
        return hash((self.lo, self.hi, frozenset(self.tried), self.current))


def parse(observation: str, seat: int = 0) -> State:
    import re
    lo, hi = {lo}, {hi}
    tried = set()

    # 1. Parse initial range from header if present, e.g. "(1-100)" or "range 1-100"
    m_head = re.search(r"\\((\\d+)\\s*-\\s*(\\d+)\\)", observation) or re.search(r"range\\s+(\\d+)\\s*-\\s*(\\d+)", observation, re.IGNORECASE)
    if m_head:
        lo, hi = int(m_head.group(1)), int(m_head.group(2))

    # 2. Extract strictly OUR guesses section, ignoring the opponent's guesses at our secret
    my_section = observation
    if "Your guesses" in observation:
        parts = observation.split("Opponent's guesses")
        my_section = parts[0]
        if "Your guesses" in my_section:
            my_section = my_section.split("Your guesses", 1)[1]

    # 3. Parse all of our guesses and referee feedback
    for m in re.finditer(r"(?:you guessed|\\bguess)\\s+(\\d+)\\s*->\\s*(higher|lower|correct|above|below)", my_section, re.IGNORECASE):
        n = int(m.group(1))
        fb = m.group(2).lower()
        tried.add(f"{prefix}{{n}}".strip())
        tried.add(str(n))
        if "higher" in fb or "above" in fb:
            lo = max(lo, n + 1)
        elif "lower" in fb or "below" in fb:
            hi = min(hi, n - 1)
        elif "correct" in fb:
            lo = hi = n

    s = State(lo, hi, tried)
    s.current = int(seat)
    return s
'''

    # Discrete / Matrix simultaneous or generic game
    discrete = grammar.discrete_actions or ["pass"]
    return f'''"""Adaptive Finite-Action State Simulator for {game_id}."""

class State:
    def __init__(self):
        self.actions = {discrete}
        self.current = 0

    def legal_actions(self):
        return list(self.actions)

    def step(self, action):
        new_state = State()
        new_state.current = 1 - self.current
        return new_state

    def is_terminal(self):
        return False

    def evaluate(self, seat):
        return 0.0


def parse(observation: str, seat: int = 0) -> State:
    s = State()
    s.current = int(seat)
    return s
'''


def calibrate_simulator(
    StateClass: Any,
    sample_turn: dict | None = None,
    max_steps: int = 2,
) -> dict[str, Any]:
    """Micro-benchmark the synthesized simulator (up to 2 turns/steps) to verify step() and legal_actions()."""
    try:
        state = StateClass()
        initial_actions = state.legal_actions()

        current_state = state
        steps_executed = 0
        start_time = time.perf_counter()

        for _ in range(max_steps):
            if current_state.is_terminal():
                break
            acts = current_state.legal_actions()
            if not acts:
                break
            current_state = current_state.step(acts[0])
            steps_executed += 1

        elapsed = time.perf_counter() - start_time
        rate = (steps_executed / elapsed) if elapsed > 0 else 50000.0

        return {
            "calibrated": True,
            "usable": True,
            "steps_executed": steps_executed,
            "initial_actions_count": len(initial_actions),
            "transitions_per_sec": round(rate, 1),
            "is_terminal_verified": current_state.is_terminal(),
        }
    except Exception as exc:
        return {
            "calibrated": False,
            "usable": False,
            "error": str(exc),
        }


def save_synthesized_simulator(
    destination_dir: str,
    classification: GameClassification,
    grammar: ActionGrammar,
    game_id: str,
    filename: str = "simulator.py",
) -> tuple[str, dict[str, Any]]:
    """Generate, write, and calibrate synthesized simulator to destination directory."""
    code = synthesize_simulator_code(classification, grammar, game_id)
    path = os.path.join(destination_dir, filename)
    atomic_write_bytes(path, code.encode("utf-8"))

    # Compile and calibrate (max 2 steps)
    namespace: dict[str, Any] = {}
    try:
        exec(code, namespace)
        calibration = calibrate_simulator(namespace.get("State"), max_steps=2)
    except Exception as exc:
        calibration = {"calibrated": False, "usable": False, "error": str(exc)}

    return path, calibration
