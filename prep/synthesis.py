"""Automated, Parameter-Driven Simulator Synthesis for 10-Minute Prep.
Synthesizes lightweight, fast Python game simulators dynamically adapted to the discovered game mechanics.
Fully game-agnostic (Rules 10.7, 12.1).
Owned by agent `bld`.
"""
from __future__ import annotations

import os
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
        actions = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r * self.cols + c] is None:
                    actions.append(f"{{chr(ord('A') + c)}}{{r + 1}}")
        return actions

    def step(self, action):
        clean = action.strip()
        col = ord(clean[0].upper()) - ord('A')
        row = int(clean[1:]) - 1
        idx = row * self.cols + col

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
'''

    elif family == "dice_push":
        target = params.get("target_score", 50)
        actions = grammar.discrete_actions or ["roll", "hold"]
        continue_candidates = {"roll", "draw", "push", "spin", "continue", "hit", "take"}
        stop_candidates = {"hold", "bank", "stop", "pass", "stand", "keep"}

        continue_act = next((a for a in actions if a.lower() in continue_candidates), actions[0])
        stop_act = next((a for a in actions if a.lower() in stop_candidates), actions[-1] if len(actions) > 1 else "pass")

        return f'''"""Adaptive Accumulator/Push-Your-Luck Simulator for {game_id} (target: {target})."""

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
        new_state = State(self.target)
        new_state.banked = list(self.banked)
        new_state.turn_total = self.turn_total
        new_state.current = self.current

        if action.lower() == self.stop_action.lower():
            new_state.banked[self.current] += self.turn_total
            new_state.turn_total = 0
            new_state.current = 1 - self.current
        else:
            # Continuing adds expected marginal gain
            new_state.turn_total += 4
        return new_state

    def is_terminal(self):
        return max(self.banked) >= self.target

    def evaluate(self, seat):
        return float(self.banked[seat] - self.banked[1 - seat])
'''

    elif family == "deduction":
        lo = grammar.numeric_min or 1
        hi = grammar.numeric_max or 100
        prefix = grammar.numeric_prefix or "guess "
        return f'''"""Adaptive Deduction & Interval Search Simulator for {game_id} (range: {lo}-{hi})."""

class State:
    def __init__(self, lo={lo}, hi={hi}):
        self.lo = lo
        self.hi = hi
        self.prefix = "{prefix}"
        self.current = 0

    def legal_actions(self):
        mid = (self.lo + self.hi) // 2
        return [f"{{self.prefix}}{{mid}}"]

    def step(self, action):
        return self

    def is_terminal(self):
        return self.lo >= self.hi

    def evaluate(self, seat):
        return 0.0
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
'''


def save_synthesized_simulator(
    destination_dir: str,
    classification: GameClassification,
    grammar: ActionGrammar,
    game_id: str,
) -> str:
    """Generate and write synthesized simulator to destination directory."""
    code = synthesize_simulator_code(classification, grammar, game_id)
    path = os.path.join(destination_dir, "simulator.py")
    atomic_write_bytes(path, code.encode("utf-8"))
    return path
