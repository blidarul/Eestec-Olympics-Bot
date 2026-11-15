"""Always-legal fallback, computed from the turn message and prep artifacts alone.

Imports nothing heavy: the main process uses it before any strategy work.
"""
import random
import re

NEUTRAL_CHAT = "Your move."


def _as_list(x):
    return [str(i) for i in x] if isinstance(x, (list, tuple)) else []


def fallback_chat(artifacts: dict | None, forbidden: list | None = None, family: str | None = None) -> str:
    bank = _as_list((artifacts or {}).get("chat_bank"))
    clean_terms = [str(term).strip().lower() for term in (forbidden or []) if str(term).strip()]
    if clean_terms:
        bank = [b for b in bank if b.strip() and not any(term in b.lower() for term in clean_terms)]
    else:
        bank = [b for b in bank if b.strip()]
    if bank:
        return random.choice(bank)[:180]
    fam = family or (artifacts or {}).get("family") or (artifacts or {}).get("prep_family")
    try:
        from core import chatsafe
        return chatsafe._pick_safe_default(clean_terms, family=fam)
    except Exception:
        for cand in ("Ready.", "Your move.", "Proceed.", "Standing by."):
            if not any(term in cand.lower() for term in clean_terms):
                return cand
        return NEUTRAL_CHAT


def norm(s) -> str:
    return "".join(ch for ch in str(s).lower() if ch not in " 	'\"`")


def unused_numeric(artifacts: dict | None, avoid) -> str | None:
    """A numeric action from the parsed grammar (prefix + n, numeric_min..numeric_max) not in `avoid`, or None."""
    import re
    g = (artifacts or {}).get("grammar")
    g = g if isinstance(g, dict) else {}
    lo, hi = g.get("numeric_min"), g.get("numeric_max")
    if not (isinstance(lo, int) and isinstance(hi, int) and 0 <= hi - lo <= 1_000_000):
        return None
    pre = str(g.get("numeric_prefix") or "")
    taken = {norm(a) for a in avoid}
    taken_nums = set()
    for a in avoid:
        for num in re.findall(r"-?\d+", str(a)):
            taken_nums.add(int(num))
    for _ in range(64):
        val = random.randint(lo, hi)
        if val in taken_nums:
            continue
        c = f"{pre}{val}"
        if norm(c) not in taken:
            return c
    for n in range(lo, hi + 1):
        if n in taken_nums:
            continue
        c = f"{pre}{n}"
        if norm(c) not in taken:
            return c
    return None


WORDS_BY_LENGTH = {
    3: ["cat", "dog", "run", "sun", "sky", "red", "big", "top", "air", "box", "car", "sea", "cup", "pen"],
    4: ["play", "game", "time", "word", "star", "open", "line", "plan", "real", "gold", "tree", "bird", "rain", "fire"],
    5: ["slate", "crane", "audio", "raise", "stare", "roast", "adieu", "trace", "brick", "glint", "jumpy", "waltz", "climb"],
    6: ["planet", "stream", "spring", "silver", "golden", "simple", "ground", "master", "forest", "winter", "bridge", "castle"],
    7: ["balance", "playing", "explore", "freedom", "journey", "mystery", "dynamic", "plastic", "silence", "crystal", "diamond"],
    8: ["building", "strength", "computer", "universe", "mountain", "solution", "football", "triangle", "sunshine", "treasure"],
    9: ["knowledge", "algorithm", "discovery", "champion", "landscape", "beautiful", "structure", "operation", "adventure"],
    10: ["basketball", "everything", "understand", "friendship", "foundation", "generation", "mysterious", "successful"],
}
WORDLE_OPENERS = WORDS_BY_LENGTH[5]


def unused_word(artifacts: dict | None, avoid) -> str | None:
    """A word action from grammar (prefix + word of word_length) not in avoid, or None."""
    g = (artifacts or {}).get("grammar")
    g = g if isinstance(g, dict) else {}
    kind = g.get("kind")
    fam = (artifacts or {}).get("family") or (artifacts or {}).get("prep_family")
    is_word = kind == "word" or fam in ("word", "wordle", "hangman")
    if not is_word and not g.get("word_length"):
        return None
    if g.get("kind") == "numeric_range" or g.get("numeric_min") is not None:
        return None
    pre = str(g.get("word_prefix") or "")
    length = int(g.get("word_length") or 5)
    case = g.get("case")
    if not case:
        examples = (artifacts or {}).get("action_format", {}).get("examples") or g.get("examples") or []
        upper_ex = [e for e in _as_list(examples) if str(e).strip().isupper() and len(str(e).strip()) > 1]
        case = "upper" if upper_ex else "lower"
    taken = {norm(a) for a in avoid}

    # 1. First try words from grammar / format examples matching length
    fmt = (artifacts or {}).get("action_format") if isinstance(artifacts, dict) else {}
    fmt_examples = _as_list(fmt.get("examples")) if isinstance(fmt, dict) else []
    grammar_examples = _as_list(g.get("examples"))
    for cand in grammar_examples + fmt_examples:
        cand_str = str(cand).strip()
        w_part = cand_str[len(pre):].strip() if pre and cand_str.lower().startswith(pre.lower()) else cand_str
        if w_part.isalpha() and (len(w_part) == length or not length):
            c_out = f"{pre}{w_part.upper() if case == 'upper' else w_part.lower()}"
            if norm(c_out) not in taken and c_out not in avoid:
                return c_out

    # 2. Try standard dictionary for this exact word length
    words = WORDS_BY_LENGTH.get(length)
    if words:
        for w in words:
            w_str = w.upper() if case == "upper" else w.lower()
            cand = f"{pre}{w_str}"
            if norm(cand) not in taken and cand not in avoid:
                return cand

    # 3. If unusual length (>10 or <3), construct from words pool
    fallback_pool = [w for w_list in WORDS_BY_LENGTH.values() for w in w_list]
    for w in fallback_pool:
        cand_w = w[:length] if len(w) >= length else (w * ((length // len(w)) + 1))[:length]
        cand = f"{pre}{cand_w.upper() if case == 'upper' else cand_w.lower()}"
        if norm(cand) not in taken and cand not in avoid:
            return cand
    return None


def _extract_rules_examples(rules: str) -> list[str]:
    if not rules:
        return []
    import re
    pattern = re.compile(r"(?i:ACTION\s+FORMAT)\s*:?\s*(.*?)(?=\n[A-Z][A-Z0-9\s_]{2,}(?:\([^\)]*\))?\s*\n|\Z)", re.DOTALL)
    m = pattern.search(rules)
    sec = m.group(1).strip() if m else rules
    return [q.strip() for q in re.findall(r'["\']([^"\']+)["\']', sec) if q.strip() and len(q) < 40 and '<' not in q]


def fallback_action(legal, artifacts: dict | None, rejected: str | None = None, conservative: bool = False,
                    avoid_also=(), observation: str = "", warning: dict | None = None, rules: str = "",
                    opponent_chat: list | None = None) -> str:
    """Always-legal move. `avoid_also`: actions already sent in this game (guessing games must not repeat)."""
    art = artifacts or {}
    policy = art.get("fallback_policy") if isinstance(art.get("fallback_policy"), dict) else {}
    prefer = _as_list(policy.get("prefer"))
    avoid = set(_as_list(policy.get("avoid")))
    avoid.update(str(a) for a in avoid_also)
    if rejected:
        avoid.add(str(rejected))
    taken_norms = {norm(a) for a in avoid}
    if legal:
        legal = [str(a) for a in legal]
        pref_ok = [p for p in prefer if p in legal and p not in avoid and norm(p) not in taken_norms]
        if pref_ok:
            if conservative:
                return pref_ok[0]
            if opponent_chat and len(pref_ok) > 1:
                try:
                    from chat.influence import pick_among_equal
                    chosen, _ = pick_among_equal(pref_ok, opponent_chat)
                    if chosen:
                        return chosen
                except Exception:
                    pass
            return pref_ok[0]
        ok = [a for a in legal if a not in avoid and norm(a) not in taken_norms]
        if conservative:  # most deterministic rung: first acceptable legal move
            return ok[0] if ok else legal[0]
        if opponent_chat and ok and len(ok) > 1:
            try:
                from chat.influence import pick_among_equal
                chosen, _ = pick_among_equal(ok, opponent_chat)
                if chosen:
                    return chosen
            except Exception:
                pass
        return random.choice(ok) if ok else legal[0]
    # 0. A template parsed from the rules (core/actionfmt.py): fill it with valid, unused parameters.
    #    When a template exists the generic lists below (pass, guess N, grid names) are never used (8.1, 9.4).
    from core import actionfmt
    tfmt = actionfmt.from_artifacts(art, warning)
    if tfmt:
        filled = actionfmt.fill(tfmt, avoid, observation)
        if filled:
            return filled

    # 0.5. Colonel Blotto fallback: allocate exact soldiers across K fields
    obs_l = (observation or "").lower()
    rules_l = (rules or "").lower()
    is_blotto = (
        "blotto" in obs_l
        or "blotto" in rules_l
        or ("soldier" in obs_l and ("field" in obs_l or "battlefield" in obs_l))
        or ("soldier" in rules_l and ("field" in rules_l or "battlefield" in rules_l))
        or "soldiers this round:" in obs_l
        or "allocation of" in obs_l
    )
    if is_blotto:
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
            k = int(m_f.group(1)) if m_f else 5
        k = max(1, min(k, 12))

        m_s = (
            re.search(r"your\s+soldiers\s+this\s+round:\s*(\d+)", observation, re.I)
            or re.search(r"soldiers\s+this\s+round:\s*(\d+)", observation, re.I)
            or re.search(r"allocation of\s*(\d+)\s*soldiers", observation, re.I)
            or re.search(r"reserves?:?\s*you\s*(\d+)", observation, re.I)
            or re.search(r"available:\s*(\d+)\s*soldiers", observation, re.I)
            or re.search(r"(\d+)\s+soldiers", rules, re.I)
            or re.search(r"add\s+up\s+to\s+EXACTLY\s+(\d+)", rules, re.I)
            or re.search(r"\+\s*(\d+)\s*(?:soldiers\s*)?per\s*round", rules, re.I)
        )
        s = int(m_s.group(1)) if m_s else 100

        share = s // k
        rem = s - share * k
        base = [share + (1 if i < rem else 0) for i in range(k)]
        cand = " ".join(str(x) for x in base)
        if cand not in avoid and norm(cand) not in taken_norms:
            return cand

        # Perturbed partitions summing strictly to s
        rng_fb = random.Random(k * 7919 + s * 31 + len(avoid))
        for _ in range(50):
            cuts = sorted([rng_fb.randint(0, s) for _ in range(k - 1)])
            alloc = []
            prev_c = 0
            for c in cuts:
                alloc.append(c - prev_c)
                prev_c = c
            alloc.append(s - prev_c)
            cand_p = " ".join(str(x) for x in alloc)
            if cand_p not in avoid and norm(cand_p) not in taken_norms:
                return cand_p

        # Concession profile: give up last field
        if k > 1:
            share_c = s // (k - 1)
            rem_c = s - share_c * (k - 1)
            concede_alloc = [share_c + (1 if i < rem_c else 0) for i in range(k - 1)] + [0]
            cand_c = " ".join(str(x) for x in concede_alloc)
            if cand_c not in avoid and norm(cand_c) not in taken_norms:
                return cand_c

        return " ".join(str(x) for x in base)
    fmt = art.get("action_format") if isinstance(art.get("action_format"), dict) else {}
    # 1. Action format examples not in avoid
    examples = _as_list(fmt.get("examples"))
    if not examples and rules:
        examples = _extract_rules_examples(rules)
    for ex in examples:
        if ex.strip() and ex not in avoid and norm(ex) not in taken_norms:
            return ex
    # 2. Grammar-specific fallback
    g = art.get("grammar") if isinstance(art.get("grammar"), dict) else {}
    if g.get("kind") == "numeric_range" or g.get("numeric_min") is not None:
        n = unused_numeric(art, avoid)
        if n and n not in avoid and norm(n) not in taken_norms:
            return n
    elif g.get("kind") == "word" or g.get("word_length"):
        w = unused_word(art, avoid)
        if w and w not in avoid and norm(w) not in taken_norms:
            return w
    # 3. Fall through to either numeric or word fallback
    n = unused_numeric(art, avoid)
    if n and n not in avoid and norm(n) not in taken_norms:
        return n
    w = unused_word(art, avoid)
    if w and w not in avoid and norm(w) not in taken_norms:
        return w
    # 4. Discrete / opening moves
    for cand in _as_list((art.get("grammar") or {}).get("discrete_actions")) + prefer:
        if cand.strip() and cand not in avoid and norm(cand) not in taken_norms:
            return cand
    # 5. Emergency fallbacks that are NOT in avoid
    for em in ["pass", "ready", "0", "1", "A1", "yes", "play", "stop", "go"]:
        if em not in avoid and norm(em) not in taken_norms:
            return em
    return "pass_alt"


def fallback_decision(msg: dict, artifacts: dict | None, previous=(), rules: str = "", opponent_chat: list | None = None) -> tuple[str, str]:
    art = artifacts or {}
    warning = msg.get("warning") if isinstance(msg.get("warning"), dict) else {}
    if opponent_chat is not None:
        opp_chat = opponent_chat
    else:
        raw_chat = msg.get("chat") if isinstance(msg, dict) else None
        opp_chat = [c.get("text", "") for c in raw_chat if isinstance(c, dict) and c.get("from") == "opponent" and c.get("text")] if isinstance(raw_chat, list) else None
    action = fallback_action(msg.get("legal_actions"), artifacts, warning.get("rejected"),
                             conservative=bool(warning), avoid_also=previous,
                             observation=str(msg.get("observation", "")), warning=warning, rules=rules,
                             opponent_chat=opp_chat)
    chat = fallback_chat(artifacts, forbidden=(artifacts or {}).get("forbidden_terms"))
    return action, chat
