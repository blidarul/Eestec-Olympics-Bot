"""Shared interfaces for strategies. Owned by the core (contract issues only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Decision:
    action: str
    chat: str
    source: str  # "strategy" | "model" | "fallback"
    # optional, for the decision log (core/worker.py fills what is missing):
    #   tool ("alpha-beta" | "mcts" | "deduction" | "model" | ...), reason (one line), candidates_left (int)
    info: dict = field(default_factory=dict)


@dataclass
class TurnState:
    game_id: str
    rules: str
    variant: dict
    seat: int
    observation: str
    legal_actions: list[str] | None
    turn: int
    warning: dict | None
    opponent_chat: list[str]  # untrusted, latest last
    artifacts: dict = field(default_factory=dict)  # from prep, may be {}
    deadline: float = 0.0  # time.monotonic() value
    llm: object | None = None  # core.llm client, None if unavailable
    # added by the core (all optional, safe defaults):
    chat_full: list = field(default_factory=list)   # [{"from": "opponent"|"you", "text": str}], untrusted, latest last
    my_actions: list = field(default_factory=list)  # every action we sent in THIS game, oldest first
    new_feedback: list = field(default_factory=list)  # observation lines that are new since our last action
    match_id: str = ""
    game_index: int = 0


class Strategy(Protocol):
    """A strategy object exposed as STRATEGY in strategies/<family>/<name>/__init__.py.

    name:     short unique id (the router's policy table in core/registry.py refers to it)
    matches:  score in [0, 1]; > 0.5 means "I can play this game better than core/generic". Pure and fast.
    decide:   returns move AND chat from one decision (rule 6.4). Never raises into the core (the worker falls
              back to core/generic if it does).
    prepare:  OPTIONAL. prepare(rules, variant, llm, deadline) -> dict | None, called once per variant in the
              prep worker (deadline = time.monotonic() value inside the 540 s prep clock; llm may be None).
              The returned dict is stored under artifacts[<name>] and in /memory/<game>/<rules_hash>/. Never
              called during a match.
    """
    name: str

    def matches(self, rules: str, artifacts: dict) -> float: ...

    def decide(self, state: TurnState) -> Decision: ...
