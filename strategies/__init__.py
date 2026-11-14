"""Strategy package. P1: only the random-legal-move strategy (proves the pipeline)."""
import random

from strategies.base import Decision, TurnState


class RandomLegal:
    name = "random_legal"

    def matches(self, rules: str, artifacts: dict) -> float:
        return 0.0

    def decide(self, state: TurnState) -> Decision:
        legal = state.legal_actions
        action = random.choice(legal) if legal else "pass"
        return Decision(action=action, chat="Your move.", source="strategy")


def default_strategy():
    return RandomLegal()
