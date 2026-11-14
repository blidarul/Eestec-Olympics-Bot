"""Strategy package. P1: only the random-legal-move strategy (proves the pipeline)."""
import os
import random
import time

from strategies.base import Decision, TurnState


def _test_sleep():
    """Test-only: BOT_TEST_SLEEP=<seconds> delays the strategy. No effect when unset."""
    v = os.environ.get("BOT_TEST_SLEEP")
    if v:
        try:
            time.sleep(float(v))
        except ValueError:
            pass


class RandomLegal:
    name = "random_legal"

    def matches(self, rules: str, artifacts: dict) -> float:
        return 0.0

    def decide(self, state: TurnState) -> Decision:
        _test_sleep()
        legal = state.legal_actions
        action = random.choice(legal) if legal else "pass"
        return Decision(action=action, chat="Your move.", source="strategy")


def default_strategy():
    return RandomLegal()
