"""Automated Simulator Synthesis for 10-Minute Prep.
Synthesizes lightweight, fast Python game simulators for unknown games during prep.
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
    """Synthesize standalone Python simulator code for the game."""
    family = classification.family

    if family == "grid_board":
        cols = grammar.grid_cols or 3
        rows = grammar.grid_rows or 3
        return f'''"""Auto-synthesized Simulator for {game_id} (grid_board)."""

class State:
    def __init__(self):
        self.cols = {cols}
        self.rows = {rows}
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
        col = ord(action[0].upper()) - ord('A')
        row = int(action[1:]) - 1
        idx = row * self.cols + col
        new_state = State()
        new_state.board = list(self.board)
        new_state.board[idx] = self.current
        new_state.current = 1 - self.current
        return new_state

    def is_terminal(self):
        return len(self.legal_actions()) == 0

    def evaluate(self, seat):
        return 0.0
'''

    elif family == "dice_push":
        return f'''"""Auto-synthesized Simulator for {game_id} (dice_push)."""

class State:
    def __init__(self, target=50):
        self.target = target
        self.banked = [0, 0]
        self.turn_total = 0
        self.current = 0

    def legal_actions(self):
        return ["roll", "hold"]

    def step(self, action):
        new_state = State(self.target)
        new_state.banked = list(self.banked)
        new_state.turn_total = self.turn_total
        new_state.current = self.current

        if action.lower() == "hold":
            new_state.banked[self.current] += self.turn_total
            new_state.turn_total = 0
            new_state.current = 1 - self.current
        return new_state

    def is_terminal(self):
        return max(self.banked) >= self.target

    def evaluate(self, seat):
        return float(self.banked[seat] - self.banked[1 - seat])
'''

    elif family == "deduction":
        lo = grammar.numeric_min or 1
        hi = grammar.numeric_max or 100
        return f'''"""Auto-synthesized Simulator for {game_id} (deduction)."""

class State:
    def __init__(self):
        self.lo = {lo}
        self.hi = {hi}
        self.current = 0

    def legal_actions(self):
        mid = (self.lo + self.hi) // 2
        return [f"guess {{mid}}"]

    def step(self, action):
        return self

    def is_terminal(self):
        return self.lo >= self.hi

    def evaluate(self, seat):
        return 0.0
'''

    # Generic state fallback
    return f'''"""Generic State Simulator for {game_id}."""

class State:
    def __init__(self):
        self.current = 0

    def legal_actions(self):
        return ["pass"]

    def step(self, action):
        return self

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
