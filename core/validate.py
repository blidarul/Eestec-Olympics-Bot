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
    if out is None:
        return None
    if rejected is not None:
        if str(out) == str(rejected) or _norm(out) == _norm(rejected):
            return None
    if previous:
        prev_norms = {_norm(p) for p in previous}
        if _norm(out) in prev_norms or str(out) in previous:
            return None
        out_nums = re.findall(r"-?\d+", out)
        if len(out_nums) == 1:
            out_val = int(out_nums[0])
            for p in previous:
                p_nums = re.findall(r"-?\d+", str(p))
                if len(p_nums) == 1 and int(p_nums[0]) == out_val:
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


def _word(action, artifacts):
    """Word games (prep grammar kind='word' or word_length/prefix): validate word length and alphabet."""
    g = (artifacts or {}).get("grammar") if isinstance(artifacts, dict) else None
    if not isinstance(g, dict):
        g = {}
    fam = (artifacts or {}).get("family") or (artifacts or {}).get("prep_family")
    is_word = g.get("kind") == "word" or fam in ("word", "wordle", "hangman")
    length = g.get("word_length")
    prefix = g.get("word_prefix") or ""
    if not is_word and not length:
        return None
    clean = action.strip()
    if prefix and clean.lower().startswith(prefix.lower()):
        cand = clean[len(prefix):].strip()
    else:
        m = re.match(r"^(?:guess\s+)?([A-Za-z]+)$", clean, re.IGNORECASE)
        cand = m.group(1) if m else clean
    if not cand.isalpha():
        return None
    if length and len(cand) != int(length):
        return None
    case = g.get("case", "lower")
    word_out = cand.upper() if case == "upper" else cand.lower()
    return f"{prefix}{word_out}" if prefix else word_out


def _validate_format(action, artifacts):
    num = _numeric(action, artifacts)
    if num is not None:
        return num
    w = _word(action, artifacts)
    if w is not None:
        return w
    g = (artifacts or {}).get("grammar") if isinstance(artifacts, dict) else None
    if isinstance(g, dict) and (g.get("kind") in ("word", "numeric_range") or g.get("word_length") or g.get("numeric_min") is not None):
        return None
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
    if examples:
        matches = difflib.get_close_matches(action, examples, n=1, cutoff=0.45)
        if matches:
            return matches[0]
    return None
