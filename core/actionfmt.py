"""Action-format templates (rules 8.1, 9.4). Pure python, no heavy imports: safe in the main process and in prep.

parse_template(rules)  -> {"templates": [...], "regex": str, "placeholders": [...]} | None
    Reads the ACTION FORMAT line(s) of the rules text, e.g.  "CLAIM R<row>-C<col>"  or  answer <text>.
matches(fmt, action)   -> bool   (regex + placeholder ranges)
repair(fmt, action)    -> str | None   (light clean-up of a near miss: quotes, trailing period, case)
fill(fmt, avoid, observation) -> str | None   (valid, unused parameters; "unknown" for free text)
from_artifacts(art, warning) -> fmt | None   (the stored template, refined by a warning's reason)
"""
import random
import re

TEXT_NAMES = ("text", "message", "free", "comment", "reason", "answer", "string", "sentence", "phrase", "say", "msg")
WORD_NAMES = ("word", "letter", "name", "token")
CELL_NAMES = ("cell", "coord", "coordinate", "square")
CODE_NAMES = ("code", "secret")
INT_NAMES = ("row", "col", "column", "count", "number", "num", "amount", "value", "index", "heap", "pile",
             "id", "position", "pos", "size", "quantity", "qty", "x", "y", "n", "k", "bet", "stones", "line", "digit")
PLACEHOLDER = re.compile(r"<([^<>\n]{1,40})>")
RANGE_IN_NAME = re.compile(r"(-?\d+)\s*(?:-|–|to|\.\.)\s*(-?\d+)")
TEXT_DEFAULT = "unknown"
MAX_TEXT = 150


def _kind(name: str) -> str:
    base = re.sub(r"[^a-z ]", " ", name.lower()).split()
    for w in base:
        if w in TEXT_NAMES:
            return "text"
    for w in base:
        if w in CELL_NAMES or w.rstrip("s") in CELL_NAMES:
            return "cell"
    for w in base:
        if w in CODE_NAMES:
            return "code"
    for w in base:
        if w in WORD_NAMES and "number" not in base:
            return "word"
    for w in base:
        if w in INT_NAMES or w.rstrip("s") in INT_NAMES:
            return "int"
    return "token"


def _name_key(name: str) -> str:
    m = re.match(r"\s*([A-Za-z]+)", name)
    return m.group(1).lower() if m else ""


def _range_from_rules(rules: str, name: str):
    """Find `rows R1-R12`, `column 1-7`, `heap number 1..3`: the first int pair next to the placeholder's key word."""
    key = _name_key(name)
    if not key:
        return None
    pat = rf"\b{re.escape(key)}\w{{0,6}}\b[^.\n<>]{{0,14}}?(?<![\d])[A-Za-z]?(-?\d+)\s*(?:-|–|to|\.\.|\.\.\.)\s*[A-Za-z]?(-?\d+)"
    m = re.search(pat, rules, re.I)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b and b - a <= 1_000_000:
            return a, b
    return None


def _grid_size(rules: str):
    m = re.search(r"\b(\d{1,3})\s*[x×]\s*(\d{1,3})\b", rules)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _split_template(tpl: str, rules: str) -> dict | None:
    """One template string -> {"template", "regex", "placeholders"}; None when it has no placeholder."""
    phs = list(PLACEHOLDER.finditer(tpl))
    if not phs:
        return None
    parts, regex, out, pos = [], "", [], 0
    grid = None
    for i, m in enumerate(phs):
        lit = tpl[pos:m.start()]
        regex += _lit_regex(lit)
        raw = m.group(1).strip()
        kind = _kind(raw)
        rng = None
        rm = RANGE_IN_NAME.search(raw)
        if rm:
            rng = (int(rm.group(1)), int(rm.group(2)))
            if kind not in ("text", "word"):
                kind = "int"
        if kind == "cell":
            grid = grid or _grid_size(rules)
            regex += r"([A-Za-z0-9_-]+)"
            out.append({"name": raw, "type": "cell", "grid": grid, "min": None, "max": None})
            pos = m.end()
            continue
        if kind == "code":
            m_len = re.search(r"\b(\d+)\s*(?:characters?|digits?|letters?|chars?)\b", rules, re.I)
            length = int(m_len.group(1)) if m_len else 4
            m_chars = re.search(r"from\s+([A-Za-z0-9]+)", rules, re.I)
            alpha = m_chars.group(1) if m_chars else "0123456789"
            regex += r"(\S+)"
            out.append({"name": raw, "type": "code", "length": length, "alpha": alpha, "min": None, "max": None})
            pos = m.end()
            continue
        if kind == "word":
            m_wlen = re.search(r"\b(\d+)[ -](?:letters?|characters?|chars?)\b", rules, re.I) or re.search(r"length\s*(?:of|is|:)?\s*(\d+)", rules, re.I)
            w_len = int(m_wlen.group(1)) if m_wlen else 5
            regex += rf"([A-Za-z0-9_-]{{{w_len}}})" if w_len else r"([A-Za-z0-9_-]+)"
            out.append({"name": raw, "type": "word", "length": w_len, "min": None, "max": None})
            pos = m.end()
            continue
        if kind == "int" and rng is None:
            rng = _range_from_rules(rules, raw)
            if rng is None and _name_key(raw) in ("row", "col", "column", "cell", "x", "y"):
                grid = grid or _grid_size(rules)
                if grid:
                    rng = (1, grid[0] if _name_key(raw) in ("row", "y") else grid[1])
        if kind == "int":
            regex += r"(-?\d+)"
        elif kind == "word":
            regex += r"([A-Za-z0-9_-]+)"
        elif kind == "text":
            regex += r"(\S[^\n]{0,%d})" % (MAX_TEXT - 1)
        else:
            regex += r"(\S+)"
        out.append({"name": raw, "type": kind, "min": rng[0] if rng else None, "max": rng[1] if rng else None})
        pos = m.end()
    regex += _lit_regex(tpl[pos:])
    return {"template": tpl, "regex": "^" + regex.strip() + "$", "placeholders": out}


def _lit_regex(lit: str) -> str:
    out = ""
    for ch in re.split(r"(\s+)", lit):
        if not ch:
            continue
        out += r"\s+" if ch.isspace() else re.escape(ch)
    return out


def _candidate_templates(rules: str) -> list[str]:
    """Template strings from the lines that carry the ACTION FORMAT (quoted first, bare line otherwise)."""
    cands: list[str] = []
    for m in re.finditer(r"(?im)^.*?\b(?:action|move|answer|command|input)s?[ _-]*(?:format|syntax)\b[^\n]*", rules):
        line = m.group(0)
        line = re.sub(r"(?i)^.*?(?:action|move|answer|command|input)s?[ _-]*(?:format|syntax)\b", "", line, count=1)
        line = re.sub(r"^\s*(\([^)]*\))?\s*[:=-]?\s*", "", line)
        head = re.split(r"(?i)[,;]?\s*\b(?:e\.g\.|eg\.|for example|example)\b", line)[0]
        quoted = re.findall(r"[\"“`]([^\"”`\n]{1,80})[\"”`]", head)
        found = [q.strip() for q in quoted if PLACEHOLDER.search(q)]
        if not found and PLACEHOLDER.search(head):
            bare = re.split(r"(?<=[>\w])\.(?:\s|$)", head)[0].strip(" .:\t")
            bare = re.sub(r"(?i)^(?:exactly|strictly|only|write|send|use)\s*:?\s*", "", bare).strip(" \"'`")
            if bare:
                found = [bare]
        for t in found:
            if t not in cands:
                cands.append(t)
    if not cands:
        sec = re.search(r"(?i:\b(?:action|move|answer|command|input)s?[ _-]*(?:format|syntax)\b)\s*:?\s*(.*?)(?=\n[A-Z][A-Z0-9\s_]{2,}(?:\([^\)]*\))?\s*\n|\Z)", rules, re.DOTALL)
        if sec:
            for line in sec.group(1).splitlines()[:6]:
                head = re.split(r"(?i)[,;]?\s*\b(?:e\.g\.|eg\.|for example|example|where)\b", line)[0]
                quoted = re.findall(r"[\"“`]([^\"”`\n]{1,80})[\"”`]", head)
                found = [q.strip() for q in quoted if PLACEHOLDER.search(q)]
                if not found and PLACEHOLDER.search(head):
                    m_ph = re.search(r"([A-Za-z0-9_-]+\s+<[^<>\n]+>|<[^<>\n]+>\s+[A-Za-z0-9_-]+|<[^<>\n]+>)", head)
                    if m_ph:
                        found = [m_ph.group(1).strip()]
                for t in found:
                    if t not in cands:
                        cands.append(t)
    return cands


def parse_template(rules: str, extra: str = "") -> dict | None:
    rules = str(rules or "")
    tpls = []
    for t in _candidate_templates(rules + ("\n" + extra if extra else "")):
        p = _split_template(t, rules)
        if p:
            tpls.append(p)
    if not tpls:
        return None
    main = tpls[0]
    fmt = {"template": main["template"], "regex": main["regex"], "placeholders": main["placeholders"],
           "templates": tpls}
    if len(tpls) > 1:
        fmt["regex"] = "|".join(f"(?:{t['regex']})" for t in tpls)
    # self-check against the example(s) of the rules: a template that rejects the rules' own example is unreliable
    examples = re.findall(r"(?i)(?:e\.g\.|for example|example)[:,]?\s*[\"“`]([^\"”`\n]{1,80})[\"”`]", rules)
    for ex in examples:
        if PLACEHOLDER.search(ex):
            continue
        if not any(_match_one(t, ex.strip()) for t in tpls):
            if any(_looks_related(t, ex) for t in tpls):
                return None
    return fmt


def _looks_related(t: dict, ex: str) -> bool:
    lead = t["template"].split("<")[0].strip().lower()
    return bool(lead) and ex.strip().lower().startswith(lead)


def _match_one(t: dict, action: str) -> bool:
    try:
        m = re.fullmatch(t["regex"], action.strip(), re.I)
    except re.error:
        return False
    if not m:
        return False
    for ph, val in zip(t["placeholders"], m.groups()):
        if ph["type"] == "int":
            n = int(val)
            if ph["min"] is not None and n < ph["min"]:
                return False
            if ph["max"] is not None and n > ph["max"]:
                return False
    return True


def _templates(fmt) -> list[dict]:
    if not isinstance(fmt, dict):
        return []
    ts = fmt.get("templates")
    if isinstance(ts, list) and ts:
        return [t for t in ts if isinstance(t, dict) and t.get("regex")]
    if fmt.get("template") and fmt.get("regex") and isinstance(fmt.get("placeholders"), list):
        return [fmt]
    return []


def matches(fmt, action) -> bool:
    ts = _templates(fmt)
    if not ts:
        return True  # no template: nothing to enforce
    if not isinstance(action, str) or not action.strip() or "\n" in action:
        return False
    return any(_match_one(t, action) for t in ts)


def has_template(fmt) -> bool:
    return bool(_templates(fmt))


def repair(fmt, action) -> str | None:
    """A near miss turned into a valid action (outer quotes, trailing period, spacing), else None."""
    if not isinstance(action, str):
        return None
    a = re.sub(r"\s+", " ", action.strip())
    q = "\"'`“”"
    for cand in (a, a.strip(q), a.strip(q).rstrip(".!;,"), a.rstrip(".!;,"), a.rstrip(".!;,").strip(q),
                 a.rstrip(".!;,").strip(q).rstrip(".!;,")):
        if cand and matches(fmt, cand):
            return cand
    return None


def _cell_token(parts: list) -> str:
    return "".join(parts)


def fill(fmt, avoid=(), observation: str = "", rnd=None) -> str | None:
    """A valid action from the first template with valid, unused parameters. Never returns a generic word."""
    ts = _templates(fmt)
    if not ts:
        return None
    rnd = rnd or random
    taken = {re.sub(r"\s+", "", str(a)).lower() for a in avoid}
    obs = str(observation or "")
    best_repeat = None
    for t in ts:
        for attempt in range(80):
            vals = []
            for ph in t["placeholders"]:
                vals.append(_value(ph, rnd, attempt, t))
            act = _render(t, vals)
            if act is None or not _match_one(t, act):
                continue
            key = re.sub(r"\s+", "", act).lower()
            if best_repeat is None:
                best_repeat = act
            if key in taken:
                continue
            if len(vals) >= 2 and _in_text(act, t, obs):
                continue
            return act
        # exhaustive pass over a single small int placeholder
        ph = t["placeholders"]
        if len(ph) == 1 and ph[0]["type"] == "int" and ph[0]["min"] is not None and ph[0]["max"] - ph[0]["min"] <= 5000:
            for n in range(ph[0]["min"], ph[0]["max"] + 1):
                act = _render(t, [str(n)])
                if act and re.sub(r"\s+", "", act).lower() not in taken:
                    return act
    return best_repeat


def _in_text(act: str, t: dict, obs: str) -> bool:
    """Cell-like parameters (two or more) already mentioned in the observation: the cell is probably taken."""
    try:
        m = re.fullmatch(t["regex"], act, re.I)
    except re.error:
        return False
    if not m:
        return False
    s, e = m.start(1), m.end(len(m.groups()))
    core = act[s:e]
    if len(core) < 3:
        return False
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(core) + r"(?!\d)", obs, re.I) is not None


def _value(ph: dict, rnd, attempt: int, t: dict) -> str:
    k = ph["type"]
    if k == "int":
        lo, hi = ph["min"], ph["max"]
        if lo is None or hi is None:
            lo, hi = (1, 3) if attempt < 20 else (1, 20)
        return str(rnd.randint(lo, hi))
    if k == "cell":
        grid = ph.get("grid") or (6, 6)
        r, c = grid[0], grid[1]
        letter = chr(ord("a") + rnd.randint(0, min(25, c - 1)))
        digit = rnd.randint(1, r)
        return f"{letter}{digit}"
    if k == "code":
        alpha = list(ph.get("alpha") or "0123456789")
        length = ph.get("length") or 4
        rnd.shuffle(alpha)
        return "".join(alpha[:length])
    if k == "text":
        return TEXT_DEFAULT
    if k == "word":
        w_len = ph.get("length") or 5
        from core.fallback import WORDS_BY_LENGTH
        words = WORDS_BY_LENGTH.get(w_len, WORDS_BY_LENGTH.get(5, ["words"]))
        return rnd.choice(words)
    return rnd.choice(["a", "1", "x"]) if attempt else "1"


def _render(t: dict, vals: list) -> str | None:
    tpl = t["template"]
    out, pos, i = "", 0, 0
    for m in PLACEHOLDER.finditer(tpl):
        out += tpl[pos:m.start()] + vals[i]
        pos, i = m.end(), i + 1
    return (out + tpl[pos:]).strip()


def from_artifacts(art, warning=None):
    """The template stored in the artifacts, refined by the `reason` of a warning (a fresh template or a range)."""
    fmt = art.get("action_format") if isinstance(art, dict) else None
    fmt = fmt if isinstance(fmt, dict) else {}
    base = fmt if _templates(fmt) else None
    reason = str(warning.get("reason", "")) if isinstance(warning, dict) else ""
    if not reason:
        return base
    if base is None:
        found = parse_template("", extra="ACTION FORMAT: " + reason) if PLACEHOLDER.search(reason) else None
        return found
    # numeric hint in the reason ("must be between 1 and 7"): narrow the only int placeholder
    ints = [p for p in base["placeholders"] if p["type"] == "int"]
    m = re.search(r"between\s+(-?\d+)\s+and\s+(-?\d+)", reason, re.I)
    if m and len(ints) == 1 and len(base["placeholders"]) == 1:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            new = dict(base)
            new["placeholders"] = [dict(ints[0], min=a, max=b)]
            new.pop("templates", None)
            return new
    return base
