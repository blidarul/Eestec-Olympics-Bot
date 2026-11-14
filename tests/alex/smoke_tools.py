"""Smoke test: call every registered solvers tool once with a sample input.

Run from the repo root:  python tests/alex/smoke_tools.py
Prints a pass/fail table to stderr (rule 5.1: no stdout). Exit code 1 on any failure.
Also importable: SAMPLES maps tool name -> sample args (used to build solvers/README.md).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import solvers  # noqa: E402,F401  (registers every tool)
from solvers import catalog  # noqa: E402

GRID = ["S..#", ".#..", "...G"]
EDGES = [["a", "b", 2], ["b", "c", 1], ["a", "c", 5], ["c", "d", 1]]
BOARD = ["XX.", "OO.", "..."]
PAYOFF = [[0, -1, 1], [1, 0, -1], [-1, 1, 0]]

# Model-callable tools: plain JSON arguments.
SAMPLES: dict[str, dict] = {
    "binary_search_next": {"lo": 1, "hi": 100, "history": [{"guess": 50, "feedback": "lower"}]},
    "bisect_predicate_points": {"points": [{"x": 3, "ok": False}, {"x": 9, "ok": True}], "integer": True},
    "dice_sum_distribution": {"dice": [6, 6], "target": 8},
    "grid_bfs": {"grid": GRID, "blocked": "#", "start": [0, 0], "goal": [2, 3]},
    "grid_astar": {"grid": GRID, "blocked": "#", "start": [0, 0], "goal": [2, 3]},
    "grid_flood_fill": {"grid": GRID, "blocked": "#", "start": [0, 0]},
    "grid_components": {"grid": GRID, "chars": ".", "liberty_chars": "G"},
    "graph_shortest_path": {"edges": EDGES, "source": "a", "target": "d"},
    "graph_reachable": {"edges": EDGES, "directed": True, "source": "b", "target": "d"},
    "graph_topo_sort": {"edges": EDGES},
    "graph_components": {"edges": EDGES + [["x", "y", 1]]},
    "graph_dfs_order": {"edges": EDGES, "directed": True, "source": "a"},
    "board_lines": {"board": BOARD, "k": 3, "players": ["X", "O"], "empty": ".", "coord_style": "A1"},
    "combinatorics": {"kind": "ncr", "n": 52, "k": 5},
    "count_hands": {"categories": [{"name": "ace", "count": 4, "min": 2, "max": 2},
                                   {"name": "other", "count": 48}], "k": 5},
    "hypergeometric": {"population": 40, "successes": 8, "draws": 5, "x": 2, "mode": "at_least"},
    "binomial_tail": {"n": 10, "p": "1/6", "x": 3, "mode": "at_least"},
    "expected_value": {"outcomes": [{"p": "1/2", "value": 10}, {"p": "1/2", "value": -4}]},
    "best_option": {"options": [{"name": "safe", "outcomes": [{"p": 1, "value": 2}]},
                                {"name": "risky", "outcomes": [{"p": 0.5, "value": 5}, {"p": 0.5, "value": 0}]}]},
    "bayes_update": {"hypotheses": [{"name": "fair", "prior": 0.9, "likelihood": 0.5},
                                    {"name": "loaded", "prior": 0.1, "likelihood": 0.9}]},
    "abstain_threshold": {"reward_correct": 1, "penalty_wrong": 1, "reward_unknown": 0, "confidence": 0.7},
    "matrix_nash": {"matrix": PAYOFF, "row_labels": ["rock", "paper", "scissors"]},
    "sample_action": {"probs": [0.5, 0.3, 0.2], "labels": ["a", "b", "c"], "seed": 7},
    "best_response": {"matrix": PAYOFF, "opponent_freq": [6, 2, 2], "row_labels": ["rock", "paper", "scissors"]},
    "nim_analysis": {"heaps": [3, 4, 5]},
    "kinrow_solve": {"rules": "Tic-tac-toe on a 3x3 board. Three in a row wins. You are X.",
                     "observation": "You are X.\n  A B C\n1 X O .\n2 . X .\n3 . O .\n", "legal_actions": ["C1", "A2", "C2", "A3", "C3"]},
    "subtraction_solve": {"rules": "A heap of stones. Remove 1, 2 or 3 stones. The player who takes the last stone wins.",
                          "observation": "Stones left: 21.", "legal_actions": ["1", "2", "3"]},
    "dice_race_solve": {"rules": "Roll one six-sided die; a 1 loses the turn total. Hold to bank. First to reach 100 points wins.",
                        "observation": "Your score: 0\nOpponent score: 0\nTurn total: 30", "legal_actions": ["roll", "hold"]},
    "range_guess_solve": {"rules": "Guess the number between 1 and 100; you hear higher or lower.",
                          "observation": "No guesses yet.", "legal_actions": None},
    "extract_numbers": {"text": "Round 3 of 10. You have 42 points, opponent 37.5."},
    "extract_grid": {"text": "Board:\n  A B C\n1 X . O\n2 . X .\n3 O . .\nYour move."},
    "extract_cards": {"text": "Your hand: Ace of Spades, 10h, KD"},
    "extract_history": {"text": "Round 1: you guessed 50 -> higher\nRound 2: you guessed 75 -> lower"},
}


# Harness-only tools: callables are passed directly (never JSON).
def _harness_samples() -> dict[str, dict]:
    # Take-1-or-2 game: the player who takes the last item wins (value for the mover at terminal = -1).
    return {
        "monte_carlo_estimate": {"sampler": lambda rng: rng.random() < 0.5, "max_samples": 2000, "seed": 1},
        "minimax_small": {
            "state": 5,
            "moves": lambda s: [m for m in (1, 2) if m <= s],
            "apply": lambda s, m: s - m,
            "terminal": lambda s: s == 0,
            "value": lambda s: -1,
        },
        "csp_backtrack": {
            "variables": {"x": [1, 2, 3], "y": [1, 2, 3]},
            "constraints": [{"vars": ["x", "y"], "check": lambda a, b: a < b}],
            "mode": "solutions",
        },
    }


def run() -> int:
    samples = dict(SAMPLES)
    samples.update(_harness_samples())
    rows, bad = [], 0
    for spec in catalog.list_tools():
        args = samples.get(spec.name)
        if args is None:
            rows.append((spec.name, "FAIL", "no sample input"))
            bad += 1
            continue
        t0 = time.monotonic()
        out = catalog.call(spec.name, args, deadline=time.monotonic() + 5)
        ok = bool(out.get("ok"))
        if ok and spec.model_callable and not any(
            t["function"]["name"] == spec.name for t in catalog.openai_tools([spec.name])
        ):
            ok, out = False, {"error": "missing from openai_tools()"}
        if ok and not spec.model_callable and any(
            t["function"]["name"] == spec.name for t in catalog.openai_tools()
        ):
            ok, out = False, {"error": "harness-only tool exported to the model"}
        bad += 0 if ok else 1
        note = out.get("explain", "") if ok else out.get("error", "?")
        rows.append((spec.name, "ok" if ok else "FAIL", f"{(time.monotonic() - t0) * 1000:.0f} ms  {note}"[:90]))
    print("tool".ljust(26) + "result  detail", file=sys.stderr)
    for name, res, note in rows:
        print(f"{name.ljust(26)}{res.ljust(8)}{note}", file=sys.stderr)
    print(f"{len(rows) - bad}/{len(rows)} passed", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(run())
