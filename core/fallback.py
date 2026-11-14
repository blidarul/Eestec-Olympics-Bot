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


def norm(s) -> str:
    return "".join(ch for ch in str(s).lower() if ch not in " 	'\"`")


def unused_numeric(artifacts: dict | None, avoid) -> str | None:
    """A numeric action from the parsed grammar (prefix + n, numeric_min..numeric_max) not in `avoid`, or None."""
    g = (artifacts or {}).get("grammar")
    g = g if isinstance(g, dict) else {}
    lo, hi = g.get("numeric_min"), g.get("numeric_max")
    if not (isinstance(lo, int) and isinstance(hi, int) and 0 <= hi - lo <= 1_000_000):
        return None
    pre = str(g.get("numeric_prefix") or "")
    taken = {norm(a) for a in avoid}
    for _ in range(64):
        c = f"{pre}{random.randint(lo, hi)}"
        if norm(c) not in taken:
            return c
    for n in range(lo, hi + 1):
        c = f"{pre}{n}"
        if norm(c) not in taken:
            return c
    return None


def fallback_action(legal, artifacts: dict | None, rejected: str | None = None, conservative: bool = False,
                    avoid_also=()) -> str:
    """Always-legal move. `avoid_also`: actions already sent in this game (guessing games must not repeat)."""
    art = artifacts or {}
    policy = art.get("fallback_policy") if isinstance(art.get("fallback_policy"), dict) else {}
    prefer = _as_list(policy.get("prefer"))
    avoid = set(_as_list(policy.get("avoid")))
    avoid.update(str(a) for a in avoid_also)
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
    if avoid_also:  # a repeat is the one thing to avoid: build a fresh value from the grammar first
        n = unused_numeric(art, avoid)
        if n:
            return n
    for ex in _as_list(fmt.get("examples")):
        if ex.strip() and ex not in avoid:
            return ex
    n = unused_numeric(art, avoid)
    return n or "pass"


def fallback_decision(msg: dict, artifacts: dict | None, previous=()) -> tuple[str, str]:
    warning = msg.get("warning") if isinstance(msg.get("warning"), dict) else {}
    action = fallback_action(msg.get("legal_actions"), artifacts, warning.get("rejected"), avoid_also=previous)
    return action, fallback_chat(artifacts)
