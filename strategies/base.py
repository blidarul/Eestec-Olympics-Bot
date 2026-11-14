"""Shared interfaces for strategies. Owned by the core (contract issues only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Decision:
    action: str
    chat: str
    source: str  # "strategy" | "model" | "fallback"


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


class Strategy(Protocol):
    name: str

    def matches(self, rules: str, artifacts: dict) -> float: ...

    def decide(self, state: TurnState) -> Decision: ...
