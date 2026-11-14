"""DecisionInfo: what the chat line may know about the move we chose (rule 6.4: move and chat from ONE decision).

Every move source (model, solver, fallback) can hand its Decision here; the chat line is then built from the
action actually chosen. Only PUBLIC facts are kept: the action string, a coarse action type and the game id.
The opponent sees our move anyway when it reads the chat, so the type carries no tell. Our private state (hand,
values, evaluation of the move) is never part of it.

A strategy may set `decision.info["action_type"]` itself; otherwise the type comes from the action's words.
"""
import re
from dataclasses import dataclass

TYPES = ("aggressive", "passive", "defensive", "probe", "neutral")

_WORDS = {
    "aggressive": r"raise|bet|all[- ]?in|attack|shoot|fire|strike|capture|take|push|bid|claim|challenge|accuse|bluff|offer|demand",
    "passive": r"fold|check|pass|wait|skip|hold|stay|stand|keep|none|nothing|accept",
    "defensive": r"block|defend|guard|cover|protect|retreat|fortify|shield|hide|decline|refuse|reject",
    "probe": r"guess|ask|query|scan|probe|test|look|peek|call|reveal|inspect|check_",
}
_RX = {k: re.compile(r"(?<![a-z])(?:%s)(?![a-z])" % v, re.I) for k, v in _WORDS.items()}


@dataclass(frozen=True)
class DecisionInfo:
    action: str = ""
    action_type: str = "neutral"
    game_id: str = ""
    source: str = ""        # "model", "strategy" or "fallback": for logs only

    @classmethod
    def build(cls, action, legal=None, game_id="", source="", action_type=""):
        return cls(str(action or "")[:80], classify_action(action, legal, action_type), str(game_id or "")[:60],
                   str(source or "")[:20])

    @classmethod
    def coerce(cls, decision, legal=None, game_id=""):
        """A DecisionInfo from a DecisionInfo, a strategies.base.Decision (has .action/.source/.info), a dict or a
        bare action string. None when there is nothing usable. Never raises."""
        try:
            if decision is None or decision == "":
                return None
            if isinstance(decision, cls):
                return decision
            if isinstance(decision, str):
                return cls.build(decision, legal, game_id)
            if isinstance(decision, dict):
                return cls.build(decision.get("action"), legal, game_id or decision.get("game_id", ""),
                                 decision.get("source", ""), decision.get("action_type", ""))
            info = getattr(decision, "info", None)
            hint = info.get("action_type", "") if isinstance(info, dict) else ""
            return cls.build(getattr(decision, "action", ""), legal, game_id, getattr(decision, "source", ""), hint)
        except Exception:
            return None


def classify_action(action, legal=None, hint=""):
    """aggressive / passive / defensive / probe / neutral, from the words of the action (public information only)."""
    if isinstance(hint, str) and hint.lower() in TYPES:
        return hint.lower()
    text = re.sub(r"[_\-/:]+", " ", str(action or "")).lower()
    for kind in ("aggressive", "defensive", "probe", "passive"):
        if _RX[kind].search(text):
            return kind
    return "neutral"
