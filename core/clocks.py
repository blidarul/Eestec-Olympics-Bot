"""Clock & Deadline Management (Rules 5.11, 8.2).
Provides unified clock guards and safety buffers across prep, start, and turn messages.
Owned by agent `bld`.
"""
from __future__ import annotations

import time

PREP_TOTAL_SECONDS = 600.0
PREP_SAFETY_BUFFER = 60.0
PREP_HARD_DEADLINE = 540.0

WARM_STUDY_SECONDS = 30.0
COLD_STUDY_SECONDS = 120.0
START_RESPONSE_CAP = 2.0

MOVE_CLOCK_SECONDS = 20.0
MOVE_SAFETY_BUFFER = 8.0
MOVE_HARD_DEADLINE = 12.0

SHUTDOWN_SECONDS = 15.0


def compute_turn_deadline(seconds: float | None = None) -> float:
    """Return max time allowed for turn computation (Rule 5.11: 20s move clock).
    Enforces a strict 12.0s hard cap (or 0.6x of announced seconds) with generous safety buffer.
    """
    total = float(seconds or MOVE_CLOCK_SECONDS)
    return min(MOVE_HARD_DEADLINE, 0.6 * total)


def compute_study_deadline(seconds: float | None = None, is_cold: bool = False) -> float:
    """Return max time for start response: specialist gets 30s, cold gets 120s."""
    total = float(seconds or (COLD_STUDY_SECONDS if is_cold else WARM_STUDY_SECONDS))
    return min(START_RESPONSE_CAP, 0.1 * total)


def compute_prep_deadline(seconds: float | None = None) -> float:
    """Return max time for 10-minute prep window (Rule 5.6: 600s).
    Cuts off at 540s to guarantee container is completely prepped and ready before arena timeout.
    """
    total = float(seconds or PREP_TOTAL_SECONDS)
    return min(PREP_HARD_DEADLINE, total - PREP_SAFETY_BUFFER)


class DeadlineTracker:
    """Tracks elapsed time and remaining budget against a monotonic deadline."""
    __slots__ = ("deadline", "start_time", "max_budget")

    def __init__(self, budget_seconds: float):
        self.start_time = time.monotonic()
        self.max_budget = float(budget_seconds)
        self.deadline = self.start_time + self.max_budget

    def expired(self, buffer_seconds: float = 0.5) -> bool:
        """Returns True if remaining time is less than buffer_seconds."""
        return time.monotonic() >= (self.deadline - buffer_seconds)

    def remaining(self) -> float:
        """Seconds remaining before deadline."""
        return max(0.0, self.deadline - time.monotonic())

    def elapsed(self) -> float:
        """Seconds elapsed since tracker creation."""
        return time.monotonic() - self.start_time
