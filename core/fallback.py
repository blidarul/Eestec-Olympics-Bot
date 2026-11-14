"""Always-legal fallback, computed from the turn message and prep artifacts alone.

Imports nothing heavy: the main process uses it before any strategy work.
"""
import random

NEUTRAL_CHAT = "Your move."


def _as_list(x):
    return [str(i) for i in x] if isinstance(x, (list, tuple)) else []


def fallback_chat(artifacts: dict | None) -> str:
    bank = _as_list((artifacts or {}).get("chat_bank"))
    bank = [b for b in bank if b.strip()]
    return random.choice(bank)[:200] if bank else NEUTRAL_CHAT


def fallback_action(legal, artifacts: dict | None, rejected: str | None = None, conservative: bool = False) -> str:
    art = artifacts or {}
    policy = art.get("fallback_policy") if isinstance(art.get("fallback_policy"), dict) else {}
    prefer = _as_list(policy.get("prefer"))
    avoid = set(_as_list(policy.get("avoid")))
    if rejected:
        avoid.add(str(rejected))
    if legal:
        legal = [str(a) for a in legal]
        for p in prefer:
            if p in legal and p not in avoid:
                return p
        ok = [a for a in legal if a not in avoid]
        if conservative:  # most deterministic rung: first acceptable legal move
            return ok[0] if ok else legal[0]
        return random.choice(ok) if ok else legal[0]
    fmt = art.get("action_format") if isinstance(art.get("action_format"), dict) else {}
    for ex in _as_list(fmt.get("examples")):
        if ex.strip() and ex not in avoid:
            return ex
    return "pass"


def fallback_decision(msg: dict, artifacts: dict | None) -> tuple[str, str]:
    warning = msg.get("warning") if isinstance(msg.get("warning"), dict) else {}
    action = fallback_action(msg.get("legal_actions"), artifacts, warning.get("rejected"))
    return action, fallback_chat(artifacts)
