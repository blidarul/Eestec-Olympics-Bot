"""Move validator (P3). Pure python, safe in the main process.

validate(action, legal, artifacts, rejected) -> legal/valid action string, or None (caller uses the fallback).
"""
import difflib
import re

FUZZY = 0.85


def _norm(s):
    return re.sub(r"[\s'\"`]+", "", str(s)).lower()


def _fuzzy(norms, n):
    best, score = None, 0.0
    for l, ln in norms:
        r = difflib.SequenceMatcher(None, n, ln).ratio()
        if r > score:
            best, score = l, r
    return best if score >= FUZZY else None


def validate(action, legal, artifacts=None, rejected=None, previous=()):
    """`previous`: actions already sent in this game that must not be repeated (guessing games): treated like rejected."""
    if not isinstance(action, str) or not action.strip():
        return None
    action = action.strip()
    out = None
    if isinstance(legal, list) and legal:
        legal = [str(a) for a in legal]
        if action in legal:
            out = action
        else:
            n = _norm(action)
            norms = [(l, _norm(l)) for l in legal]
            out = next((l for l, ln in norms if ln == n), None) or _fuzzy(norms, n)
    else:  # legal_actions is null: follow the action format from prep
        out = _validate_format(action, artifacts)
    if out is None or (rejected is not None and out == str(rejected)):
        return None
    if previous and _norm(out) in {_norm(p) for p in previous}:
        return None
    return out


def _numeric(action, artifacts):
    """Numeric-range games (prep grammar numeric_min/max/prefix): a number inside the range is valid whatever the
    examples are. Returns the action (as given, or rebuilt as prefix + n when the model wrapped it in words), or None."""
    g = (artifacts or {}).get("grammar") if isinstance(artifacts, dict) else None
    if not (isinstance(g, dict) and g.get("kind") == "numeric_range"
            and isinstance(g.get("numeric_min"), int) and isinstance(g.get("numeric_max"), int)):
        return None
    nums = re.findall(r"-?\d+", action)
    if len(nums) != 1:
        return None
    n = int(nums[0])
    if not g["numeric_min"] <= n <= g["numeric_max"]:
        return None
    if re.fullmatch(r"\s*(?:[A-Za-z_]+\s+)?-?\d+\s*", action):  # "46" or "guess 46": as given (a verified strategy knows the format)
        return action
    return f"{g.get('numeric_prefix') or ''}{n}"          # words around the number: rebuild from the parsed grammar


def _validate_format(action, artifacts):
    num = _numeric(action, artifacts)
    if num is not None:
        return num
    fmt = (artifacts or {}).get("action_format") if isinstance(artifacts, dict) else None
    fmt = fmt if isinstance(fmt, dict) else {}
    examples = [str(e) for e in (fmt.get("examples") or []) if str(e).strip()]
    rx = fmt.get("regex")
    if rx:
        try:
            if re.fullmatch(rx, action):
                return action
        except re.error:
            rx = None
    if not rx and not examples:
        return action if len(action) <= 200 and "\n" not in action else None  # nothing to check against
    if not rx and any(difflib.SequenceMatcher(None, _norm(action), _norm(e)).ratio() >= 0.6 for e in examples):
        return action
    if not examples:
        return None
    return difflib.get_close_matches(action, examples, n=1, cutoff=0.0)[0]
