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


def validate(action, legal, artifacts=None, rejected=None, previous=(), observation=""):
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
        out = _validate_format(action, artifacts, observation=observation)
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
    case = g.get("case")
    if not case:
        examples = (artifacts or {}).get("action_format", {}).get("examples") or g.get("examples") or []
        upper_ex = [e for e in examples if isinstance(e, str) and e.strip().isupper() and len(e.strip()) > 1]
        case = "upper" if upper_ex else "lower"
    word_out = cand.upper() if case == "upper" else cand.lower()
    return f"{prefix}{word_out}" if prefix else word_out


def _blotto(action, artifacts, observation=""):
    """Colonel Blotto allocation validator:
    Validates K whole numbers >= 0 summing to S (or <= S in reserves mode).
    Returns formatted action "n1 n2 ... nk", or None if not a blotto action.
    """
    if not isinstance(action, str):
        return None
    clean = action.replace(",", " ").strip()
    tokens = clean.split()
    if len(tokens) < 2 or not all(re.fullmatch(r"\d+", t) for t in tokens):
        return None
    nums = [int(t) for t in tokens]

    obs_lower = (observation or "").lower()
    art_str = str(artifacts or {}).lower()
    is_blotto = (
        "blotto" in obs_lower
        or "blotto" in art_str
        or ("soldier" in obs_lower and "field" in obs_lower)
        or ("soldier" in art_str and "field" in art_str)
    )
    if not is_blotto:
        return None

    m_f = (
        re.search(r"across\s*(\d+)\s*fields", observation, re.I)
        or re.search(r"(\d+)\s*fields", observation, re.I)
        or re.search(r"across\s*(\d+)\s*battlefields", art_str, re.I)
        or re.search(r"(\d+)\s*fields", art_str, re.I)
    )
    k = int(m_f.group(1)) if m_f else len(nums)

    m_s = (
        re.search(r"soldiers this round:\s*(\d+)", observation, re.I)
        or re.search(r"allocation of\s*(\d+)\s*soldiers", observation, re.I)
        or re.search(r"available:\s*(\d+)\s*soldiers", observation, re.I)
        or re.search(r"(\d+)\s*soldiers", art_str, re.I)
    )
    s = int(m_s.group(1)) if m_s else 100

    is_reserves = "reserve" in obs_lower or "reserve" in art_str

    if len(nums) != k:
        return None

    total = sum(nums)
    if is_reserves:
        if total <= s:
            return " ".join(str(x) for x in nums)
        # Scaled down to at most s
        if total > 0:
            scaled = [int(x * s / total) for x in nums]
            diff = s - sum(scaled)
            for i in range(diff):
                scaled[i % k] += 1
            return " ".join(str(x) for x in scaled)
    else:
        if total == s:
            return " ".join(str(x) for x in nums)
        # Scale to exact sum s
        if total > 0:
            scaled = [int(x * s / total) for x in nums]
            diff = s - sum(scaled)
            for i in range(diff):
                scaled[i % k] += 1
            return " ".join(str(x) for x in scaled)
        else:
            share = s // k
            rem = s - share * (k - 1)
            res = [share] * (k - 1) + [rem]
            return " ".join(str(x) for x in res)
    return None


def _validate_format(action, artifacts, observation=""):
    num = _numeric(action, artifacts)
    if num is not None:
        return num
    w = _word(action, artifacts)
    if w is not None:
        return w
    bl = _blotto(action, artifacts, observation)
    if bl is not None:
        return bl
    obs_lower = (observation or "").lower()
    art_str = str(artifacts or {}).lower()
    if "blotto" in obs_lower or "blotto" in art_str or ("soldier" in obs_lower and "field" in obs_lower):
        return None
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
