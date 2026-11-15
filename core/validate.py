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


def _is_repeat_allowed(artifacts, observation="", rules=""):
    obs_lower = (observation or "").lower()
    rules_lower = (rules or "").lower()
    return (
        _is_blotto(artifacts, observation=observation, rules=rules)
        or "auction" in obs_lower
        or "auction" in rules_lower
        or "bargain" in obs_lower
        or "bargain" in rules_lower
        or "poker" in obs_lower
        or "poker" in rules_lower
        or "dice" in obs_lower
        or "dice" in rules_lower
    )


def validate(action, legal, artifacts=None, rejected=None, previous=(), observation="", rules=""):
    """`previous`: actions already sent in this game that must not be repeated (guessing games): treated like rejected."""
    if not isinstance(action, str) or not action.strip():
        return None
    action = action.strip()
    out = None
    if isinstance(legal, list) and legal:
        legal = [str(a) for a in legal]
        if action in legal:
            out = action
        elif any(kw in str(rules).lower() or kw in str(observation).lower() for kw in ("document qa", "reference document")) and action.lower().startswith("answer "):
            out = _validate_format(action, artifacts, observation=observation, rules=rules)
        else:
            n = _norm(action)
            norms = [(l, _norm(l)) for l in legal]
            out = next((l for l, ln in norms if ln == n), None) or _fuzzy(norms, n)
    else:  # legal_actions is null: follow the action format from prep
        out = _validate_format(action, artifacts, observation=observation, rules=rules)
    if out is None:
        return None
    if rejected is not None:
        if str(out) == str(rejected) or _norm(out) == _norm(rejected):
            return None
    if previous and not _is_repeat_allowed(artifacts, observation=observation, rules=rules):
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


def _is_blotto(artifacts=None, observation="", rules=""):
    obs_lower = (observation or "").lower()
    rules_lower = (rules or "").lower()
    return (
        "blotto" in obs_lower
        or "blotto" in rules_lower
        or ("soldier" in obs_lower and ("field" in obs_lower or "battlefield" in obs_lower))
        or ("soldier" in rules_lower and ("field" in rules_lower or "battlefield" in rules_lower))
        or "soldiers this round:" in obs_lower
        or "allocation of" in obs_lower
    )


def _blotto(action, artifacts, observation="", rules=""):
    """Colonel Blotto allocation validator:
    Validates K whole numbers >= 0 summing to S (or <= S in reserves mode).
    Returns formatted action "n1 n2 ... nk", or None if not a blotto action.
    """
    if not isinstance(action, str):
        return None
    clean = action.replace(",", " ").strip()
    tokens = clean.split()
    if not tokens or not all(re.fullmatch(r"\d+", t) for t in tokens):
        return None
    nums = [int(t) for t in tokens]

    if not _is_blotto(artifacts, observation, rules):
        return None

    obs_lower = (observation or "").lower()
    rules_lower = (rules or "").lower()

    # Determine K
    f_matches = re.findall(r"\bF(\d+)\b", observation)
    k = max(int(x) for x in f_matches) if f_matches else None
    if not k:
        f_matches_r = re.findall(r"\bF(\d+)\b", rules)
        k = max(int(x) for x in f_matches_r) if f_matches_r else None
    if not k:
        m_f = (
            re.search(r"across\s*(\d+)\s*fields", observation, re.I)
            or re.search(r"(\d+)\s*fields", observation, re.I)
            or re.search(r"across\s*(\d+)\s*battlefields", rules, re.I)
            or re.search(r"(\d+)\s*battlefields", rules, re.I)
            or re.search(r"(\d+)\s*fields", rules, re.I)
        )
        k = int(m_f.group(1)) if m_f else len(nums)
    k = max(1, min(k, 12))

    # Determine S
    m_s = (
        re.search(r"your\s+soldiers\s+this\s+round:\s*(\d+)", observation, re.I)
        or re.search(r"soldiers this round:\s*(\d+)", observation, re.I)
        or re.search(r"allocation of\s*(\d+)\s*soldiers", observation, re.I)
        or re.search(r"reserves?:?\s*you\s*(\d+)", observation, re.I)
        or re.search(r"available:\s*(\d+)\s*soldiers", observation, re.I)
        or re.search(r"(\d+)\s+soldiers", rules, re.I)
        or re.search(r"add\s+up\s+to\s+EXACTLY\s+(\d+)", rules, re.I)
        or re.search(r"\+\s*(\d+)\s*(?:soldiers\s*)?per\s*round", rules, re.I)
    )
    s = int(m_s.group(1)) if m_s else 100

    is_reserves = "reserve" in obs_lower or "reserve" in rules_lower

    # If length matches exactly and sum matches criteria
    if len(nums) == k:
        total = sum(nums)
        if is_reserves and total <= s:
            return " ".join(str(x) for x in nums)
        elif not is_reserves and total == s:
            return " ".join(str(x) for x in nums)

    # Need repair: adapt length to k
    if len(nums) > k:
        nums = nums[:k]
    elif len(nums) < k:
        nums = nums + [0] * (k - len(nums))

    total = sum(nums)
    target = s if (not is_reserves or total > s) else total
    if total > 0:
        scaled = [int(x * target / total) for x in nums]
        diff = target - sum(scaled)
        sorted_indices = sorted(range(k), key=lambda idx: nums[idx], reverse=True)
        for i in range(diff):
            scaled[sorted_indices[i % k]] += 1
        return " ".join(str(x) for x in scaled)
    else:
        target = s if not is_reserves else 0
        if target > 0:
            share = target // k
            rem = target - share * k
            scaled = [share + (1 if i < rem else 0) for i in range(k)]
            return " ".join(str(x) for x in scaled)
        return " ".join(["0"] * k)


def _validate_format(action, artifacts, observation="", rules=""):
    if _is_blotto(artifacts, observation, rules):
        return _blotto(action, artifacts, observation, rules)
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
    if not rx and rules:
        try:
            from core import actionfmt
            parsed = actionfmt.parse_template(rules)
            if parsed and parsed.get("regex"):
                rx = parsed["regex"]
        except Exception:
            rx = None
    if rx:
        try:
            if re.fullmatch(rx, action):
                return action
        except re.error:
            rx = None
    if not rx and not examples:
        return action if len(action) <= 200 and "\n" not in action else None  # nothing to check against
    # If action shares command verb with examples (e.g. 'CAST FIREBALL' vs 'CAST MEDITATE')
    act_words = action.split()
    if act_words and examples:
        cmd = act_words[0].upper()
        ex_cmds = {e.split()[0].upper() for e in examples if e.split()}
        if cmd in ex_cmds and len(action) <= 200 and "\n" not in action:
            return action
    if not rx and any(difflib.SequenceMatcher(None, _norm(action), _norm(e)).ratio() >= 0.6 for e in examples):
        return action
    if examples:
        matches = difflib.get_close_matches(action, examples, n=1, cutoff=0.45)
        if matches:
            return matches[0]
    return None
