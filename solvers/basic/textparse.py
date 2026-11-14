"""Text extraction helpers: numbers, boards, cards and move history found in observation text.

General tools (no game names, rule 10.7): text in, plain data out, stdlib only. The text is data
(it may hold opponent chat, rule 6.7): nothing in it is ever evaluated. Caller-supplied regexes
are compiled and run on short lines only, with a guard against nested quantifiers.
"""
import re
import time

from solvers.catalog import ToolError, ToolSpec, register

_MAX_TEXT = 20000
_MAX_LINES = 400
_MAX_LINE = 300


def _check_time(deadline):
    if time.monotonic() > deadline:
        raise ToolError("deadline exceeded")


def _num(s):
    s = s.replace(",", "")
    try:
        return int(s)
    except ValueError:
        return float(s)


# ---------------------------------------------------------------- extract_numbers

_NUM_RE = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w|\.\d)")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")


def extract_numbers(args, deadline):
    text = args["text"]
    limit = args.get("max_items", 60)
    ctx = args.get("context_words", 3)
    items = []
    total = 0
    lines = text.split("\n")
    for ln, line in enumerate(lines[:_MAX_LINES]):
        _check_time(deadline)
        for m in _NUM_RE.finditer(line):
            total += 1
            if len(items) >= limit:
                continue
            before = _WORD_RE.findall(line[:m.start()])[-ctx:] if ctx else []
            after = _WORD_RE.findall(line[m.end():])[:ctx] if ctx else []
            raw = m.group(0).lstrip("+")
            items.append({"value": _num(raw), "text": m.group(0), "line": ln,
                          "before": before, "after": after})
    res = {"numbers": items, "count": total}
    if total > len(items):
        res["numbers_truncated"] = total - len(items)
    res["explain"] = "Found %d number(s)." % total
    return res


register(ToolSpec(
    name="extract_numbers",
    summary="List every integer/decimal in a text with its line number and the words just before and after it (scores, bounds, counts in an observation).",
    params={"type": "object",
            "properties": {
                "text": {"type": "string", "maxLength": _MAX_TEXT, "description": "text to scan"},
                "max_items": {"type": "integer", "minimum": 1, "maximum": 200, "description": "cap on numbers returned (default 60)"},
                "context_words": {"type": "integer", "minimum": 0, "maximum": 6, "description": "words kept on each side (default 3)"}},
            "required": ["text"]},
    fn=extract_numbers, families=("any",), model_callable=True, max_ms=1000))


# ---------------------------------------------------------------- extract_grid

def _is_seq(tokens):
    """True if single-char tokens run 1,2,3.. / 0,1,2.. / A,B,C.. / a,b,c.. (ascending, step 1)."""
    if len(tokens) < 2 or any(len(t) != 1 for t in tokens):
        return False
    if all(t.isdigit() for t in tokens):
        v = [int(t) for t in tokens]
    elif all(t.isalpha() for t in tokens):
        v = [ord(t.lower()) for t in tokens]
        if len({t.isupper() for t in tokens}) != 1:
            return False
    else:
        return False
    return all(b - a == 1 for a, b in zip(v, v[1:])) or all(a - b == 1 for a, b in zip(v, v[1:]))


def _row_tokens(line):
    """Cells of a spaced board row (all tokens one character), else None."""
    if "|" in line:  # "1 |X|O| |": empty cells are spaces between pipes
        parts = line.strip().split("|")
        lead = parts[0].strip()
        body = parts[1:-1] if not parts[-1].strip() else parts[1:]
        toks = ([lead] if lead else []) + [p.strip() or " " for p in body]
    else:
        toks = line.split()
    if len(toks) >= 2 and all(len(t) == 1 for t in toks):
        return toks
    return None


def _compact_row(line):
    """A board row written without spaces ('.XO'): one token, few distinct characters."""
    toks = line.replace("|", "").split()
    if len(toks) != 1:
        return None
    t = toks[0]
    if len(t) < 2 or len(set(t)) > 6:
        return None
    if t.isalpha() and not (t.isupper() and len(set(t)) <= 3):
        return None
    return list(t)


_SEP_RE = re.compile(r"^[\s\-+=|_#*]*$")


def _is_sep(line):
    s = line.strip()
    return bool(s) and bool(_SEP_RE.match(s)) and len(set(s.replace(" ", ""))) <= 2 and ("-" in s or "=" in s or "+" in s) and "#" not in s


def _find_blocks(lines, parser):
    """Runs of consecutive lines for which parser(line) is not None (separator lines are skipped)."""
    blocks, cur = [], []
    for i, line in enumerate(lines):
        if _is_sep(line):
            continue
        toks = parser(line)
        if toks is None:
            if cur:
                blocks.append(cur)
            cur = []
        else:
            cur.append((i, toks))
    if cur:
        blocks.append(cur)
    return blocks


def _build_grid(block):
    """Turn a run of token rows into a grid dict, or None if it does not look like a board."""
    header = None
    rows = block
    if len(rows) >= 3 and _is_seq(rows[0][1]):
        n = len(rows[0][1])
        if all(len(t) in (n, n + 1) for _, t in rows[1:]) and len({len(t) for _, t in rows[1:]}) == 1:
            header = rows[0]
            rows = rows[1:]
    if len(rows) < 2:
        return None
    widths = {len(t) for _, t in rows}
    if len(widths) != 1:
        return None
    w = widths.pop()
    row_labels = None
    col_labels = None
    if header is not None:
        col_labels = list(header[1])
        if w == len(col_labels) + 1:
            row_labels = [t[0] for _, t in rows]
            rows = [(i, t[1:]) for i, t in rows]
        elif w != len(col_labels):
            return None
    else:
        first = [t[0] for _, t in rows]
        if w >= 3 and _is_seq(first):
            row_labels = first
            rows = [(i, t[1:]) for i, t in rows]
    width = len(rows[0][1])
    if width < 2:
        return None
    cells = ["".join(t) for _, t in rows]
    syms = {}
    for r in cells:
        for ch in r:
            syms[ch] = syms.get(ch, 0) + 1
    if row_labels is None and col_labels is None and len(syms) > 12:
        return None
    if col_labels and row_labels:
        if col_labels[0].isalpha() and row_labels[0].isdigit():
            style = "A1"
        elif col_labels[0].isdigit() and row_labels[0].isdigit():
            style = "numeric"
        else:
            style = "other"
    elif col_labels or row_labels:
        style = "other"
    else:
        style = "r,c"
    out = {"rows": cells, "height": len(cells), "width": width,
           "start_line": rows[0][0], "coord_style": style, "symbols": syms}
    if col_labels:
        out["col_labels"] = col_labels
    if row_labels:
        out["row_labels"] = row_labels
    return out


def extract_grid(args, deadline):
    text = args["text"]
    lines = text.split("\n")[:_MAX_LINES]
    grids = []
    for parser in (_row_tokens, _compact_row):
        for block in _find_blocks(lines, parser):
            _check_time(deadline)
            g = _build_grid(block)
            if g is not None and not any(g["start_line"] == o["start_line"] for o in grids):
                grids.append(g)
        if grids:
            break
    grids.sort(key=lambda g: g["start_line"])
    grids = grids[:4]
    if not grids:
        return {"found": False, "grids": [], "explain": "No board block found."}
    g = grids[0]
    return {"found": True, "grids": grids,
            "explain": "Board %dx%d (rows x cols), coordinates: %s." % (g["height"], g["width"], g["coord_style"])}


register(ToolSpec(
    name="extract_grid",
    summary="Find the board block in an observation (consecutive equal-width rows, optional row/column labels) and return its rows, labels and coordinate style; feed rows to grid_* and board_lines.",
    params={"type": "object",
            "properties": {"text": {"type": "string", "maxLength": _MAX_TEXT, "description": "observation text"}},
            "required": ["text"]},
    fn=extract_grid, families=("any",), model_callable=True, max_ms=1000))


# ---------------------------------------------------------------- extract_cards

_RANK_WORDS = {"ace": "A", "king": "K", "queen": "Q", "jack": "J", "ten": "T", "nine": "9", "eight": "8",
               "seven": "7", "six": "6", "five": "5", "four": "4", "three": "3", "two": "2", "deuce": "2"}
_SUIT_WORDS = {"spade": "S", "heart": "H", "diamond": "D", "club": "C"}
_SUIT_SYM = {"♠": "S", "♥": "H", "♦": "D", "♣": "C",
             "♤": "S", "♡": "H", "♢": "D", "♧": "C"}
_WORD_CARD = re.compile(
    r"\b(10|[2-9]|[AKQJT]|ace|king|queen|jack|ten|nine|eight|seven|six|five|four|three|two|deuce)"
    r"\s+of\s+(spade|heart|diamond|club)s?\b", re.I)
_SHORT_CARD = re.compile(
    r"(?<![A-Za-z0-9])(10|[2-9TJQKA])\s?([♠♥♦♣♤♡♢♧]|[SHDCshdc])(?![A-Za-z0-9])")


def _rank(s):
    s = s.lower()
    if s in _RANK_WORDS:
        return _RANK_WORDS[s]
    return "T" if s == "10" else s.upper()


def extract_cards(args, deadline):
    text = args["text"]
    letters = args.get("suit_letters", True)
    found = []
    for ln, line in enumerate(text.split("\n")[:_MAX_LINES]):
        _check_time(deadline)
        spans = []
        for m in _WORD_CARD.finditer(line):
            spans.append((m.start(), m.end(), _rank(m.group(1)), _SUIT_WORDS[m.group(2).lower()]))
        for m in _SHORT_CARD.finditer(line):
            suit_raw = m.group(2)
            if suit_raw in _SUIT_SYM:
                suit = _SUIT_SYM[suit_raw]
            elif letters:
                # letter suits: a lowercase rank letter is never a rank, so "ah" is only a card as "Ah"/"AH"
                suit = suit_raw.upper()
            else:
                continue
            if any(s <= m.start() < e for s, e, _, _ in spans):
                continue
            spans.append((m.start(), m.end(), _rank(m.group(1)), suit))
        for s, e, r, su in sorted(spans):
            found.append({"rank": r, "suit": su, "text": line[s:e], "line": ln})
    total = len(found)
    rank_counts, suit_counts = {}, {}
    for c in found:
        rank_counts[c["rank"]] = rank_counts.get(c["rank"], 0) + 1
        suit_counts[c["suit"]] = suit_counts.get(c["suit"], 0) + 1
    res = {"cards": found[:80], "count": total, "rank_counts": rank_counts, "suit_counts": suit_counts}
    if total > 80:
        res["cards_truncated"] = total - 80
    res["explain"] = "Found %d card(s) (rank T = ten, suits S H D C)." % total
    return res


register(ToolSpec(
    name="extract_cards",
    summary="Find playing cards in a text (A K Q J 10/T 2-9 with suit letters S H D C, suit symbols, or 'Ace of Spades') and normalise them to rank + suit, with rank and suit counts.",
    params={"type": "object",
            "properties": {
                "text": {"type": "string", "maxLength": _MAX_TEXT, "description": "text to scan"},
                "suit_letters": {"type": "boolean", "description": "accept letter suits like 'KH' or '10d' (default true); set false if words like 'AS' appear"}},
            "required": ["text"]},
    fn=extract_cards, families=("any",), model_callable=True, max_ms=1000))


# ---------------------------------------------------------------- extract_history

_ARROW = r"(?:->|→|=>)"
_VERBS = r"(?:guessed|played|bid|chose|picked|said|rolled|moved|raised|called|bet|asked|answered|drew|placed)"
_DEFAULT_PATTERNS = [
    # "Round 1: you guessed 25 -> higher" / "Turn 1 (you): 3 -> held for +3." / "Move 2 (opponent) plays B3"
    r"^\s*(?:round|turn|move|step)\s*(?P<round>\d+)\s*(?:\((?P<actor>[^)]{1,20})\))?\s*[:.\-]?\s*"
    r"(?:(?P<actor2>you|opponent|opp|player\s*\d+|me|they)\s+)?(?:" + _VERBS + r"\s+)?"
    r"(?P<value>[^>=→]{1,60}?)\s*" + _ARROW + r"\s*(?P<feedback>.{1,120}?)\s*$",
    # no arrow: "Round 3: opponent bid 4 fives"
    r"^\s*(?:round|turn|move|step)\s*(?P<round>\d+)\s*(?:\((?P<actor>[^)]{1,20})\))?\s*[:.\-]?\s*"
    r"(?P<actor2>you|opponent|opp|player\s*\d+|me|they)\s+" + _VERBS + r"\s+(?P<value>.{1,60}?)\s*$",
]
_NESTED_Q = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*{]")
_MOVES_LINE = re.compile(r"^\s*(?:moves(?:\s+so\s+far)?|history|log)\s*:\s*(?P<body>.+)$", re.I)


def _actor(s):
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s.strip().lower())
    if s in ("you", "me", "i"):
        return "you"
    if s in ("opponent", "opp", "they", "them"):
        return "opponent"
    return s


def _entry(m, idx):
    d = m.groupdict()
    value = (d.get("value") or "").strip().rstrip(".,;")
    out = {"round": int(d["round"]) if d.get("round") and d["round"].isdigit() else idx}
    out["actor"] = _actor(d.get("actor") or d.get("actor2"))
    try:
        out["value"] = _num(value)
    except ValueError:
        out["value"] = value
    out["feedback"] = (d.get("feedback") or "").strip() or None
    return out


def extract_history(args, deadline):
    text = args["text"]
    pats = args.get("patterns")
    if pats:
        compiled = []
        for p in pats:
            if _NESTED_Q.search(p):
                raise ToolError("pattern rejected (nested quantifier): %s" % p[:60])
            try:
                compiled.append(re.compile(p, re.I))
            except re.error as e:
                raise ToolError("bad pattern %r: %s" % (p[:60], e))
    else:
        compiled = [re.compile(p, re.I) for p in _DEFAULT_PATTERNS]
    entries = []
    for line in text.split("\n")[:_MAX_LINES]:
        _check_time(deadline)
        line = line[:_MAX_LINE]
        done = False
        for rx in compiled:
            m = rx.search(line)
            if m:
                entries.append(_entry(m, len(entries) + 1))
                done = True
                break
        if done or pats:
            continue
        m = _MOVES_LINE.match(line)
        if m:
            for item in m.group("body").split(","):
                toks = item.split()
                if not toks:
                    continue
                if len(toks) == 1:
                    actor, val = None, toks[0]
                else:
                    actor, val = toks[0], " ".join(toks[1:])
                entries.append({"round": len(entries) + 1, "actor": _actor(actor), "value": val, "feedback": None})
    total = len(entries)
    res = {"history": entries[-60:], "count": total}
    if total > 60:
        res["history_dropped_oldest"] = total - 60
    res["explain"] = "Parsed %d history entr%s." % (total, "y" if total == 1 else "ies")
    return res


register(ToolSpec(
    name="extract_history",
    summary="Parse history lines such as 'Round 2: you guessed 47 -> lower' or 'Moves so far: X C2, O B1' into {round, actor, value, feedback}; optional regex patterns with named groups round/actor/value/feedback.",
    params={"type": "object",
            "properties": {
                "text": {"type": "string", "maxLength": _MAX_TEXT, "description": "observation text"},
                "patterns": {"type": "array", "maxItems": 4,
                             "description": "optional regexes (one line each) with named groups round, actor, value, feedback; replaces the defaults",
                             "items": {"type": "string", "maxLength": 200}}},
            "required": ["text"]},
    fn=extract_history, families=("any",), model_callable=True, max_ms=1000))
