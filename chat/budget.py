"""Budget guard for the model: when this match key has cost too much, play without the model.

core/llm.py counts `spend` (tokens times the prices of rule 7.5) and keeps counting across keys, so this guard
remembers the spend at the moment a NEW key arrives (a new match) and measures from there. The soft limit
(config.BUDGET_SOFT_USD) is well under the $0.75 of a match because the key is shared by all our containers
and we only see our own spend. A typical match costs about $0.003, so this only triggers when something is wrong.
The caller must also check llm.available() (core/llm.py pauses the model after repeated failures).
"""
from . import config


class BudgetGuard:
    def __init__(self, soft=None):
        self.soft = config.BUDGET_SOFT_USD if soft is None else soft
        self.key = None
        self.base = 0.0

    def spent(self, llm):
        info = getattr(llm, "info", None)
        key = info.get("api_key") if isinstance(info, dict) else None
        spend = float(getattr(llm, "spend", 0.0) or 0.0)
        if key != self.key:  # a new key = a new match: count from here
            self.key, self.base = key, spend
        return max(0.0, spend - self.base)

    def allows(self, llm):
        """True while the model may still be used."""
        try:
            return self.spent(llm) < self.soft
        except Exception:
            return False  # when in doubt, play without the model
