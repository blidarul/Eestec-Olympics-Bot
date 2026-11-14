"""Forbidden terms from the rules text, independent of the model (rules 6.8, 6.9). Pure python, stdlib only.

extract_terms(rules)        -> base terms ("never say the word "harbor"" -> ["harbor"])
expand(terms, use_guard)    -> base terms + variants (case, diacritics, plurals, spacing, leetspeak), capped
contains(text, terms)       -> the term that hit, or None (word-aware, leet/diacritics/spaced-out letters)
merge(rules, model_terms)   -> final list for artifacts["forbidden_terms"]
safe_action(action, ...)    -> an action without a forbidden term: a template value or another legal move, never a cut
"""
import re
import unicodedata

MAX_TERMS = 600
MAX_BASE = 40
_LEET_TO_LETTER = {"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t", "8": "b",
                   "9": "g", "|": "i", "l": "i"}
_LETTER_TO_LEET = {"a": "4@", "e": "3", "i": "1!", "o": "0", "s": "5$", "t": "7", "l": "1", "b": "8", "g": "9"}
STOP = {"a", "an", "the", "any", "anything", "anyone", "your", "you", "to", "in", "of", "or", "and", "that", "this", "it",
        "word", "words", "term", "terms", "phrase", "phrases", "subject", "subjects", "topic", "topics", "chat", "during",
        "when", "while", "at", "about", "else", "such", "following", "other", "another", "on", "for", "with", "is", "are",
        "be", "as", "if", "game", "move", "message", "messages", "answer", "answers", "ever", "again", "here", "there",
        "which", "who", "whom", "what", "so", "than", "then", "not", "no", "only", "also", "even", "both", "all", "one"}
VERBS = (r"say(?:ing)?|mention(?:ing)?|use|using|utter(?:ing)?|write|writing|type|typing|include|including|speak|spell(?:ing)?|"
         r"pronounc(?:e|ing)|name|naming|send(?:ing)?|reveal(?:ing)?|talk(?:ing)?\s+about|discuss(?:ing)?|refer(?:ring)?\s+to|"
         r"output(?:ting)?|print(?:ing)?|repeat(?:ing)?|contain(?:ing)?|utter")
NEG = (r"never|must\s+not|may\s+not|should\s+not|shall\s+not|cannot|can't|can\s+not|do\s+not|don't|"
       r"not\s+allowed\s+to|not\s+permitted\s+to|forbidden\s+to|prohibited\s+from|banned\s+from|avoid|refrain\s+from|"
       r"is\s+forbidden\s+to|are\s+forbidden\s+to|no\s+one\s+may|nobody\s+may|you\s+lose\s+if\s+you|loses\s+if\s+(?:they|you)")
QUOTE = r"[\"“”‘’'`]"
QUOTED = re.compile(r"[\"“`]([^\"”`\n]{1,40})[\"”`]|(?<![A-Za-z])['‘]([^'’\n]{1,40})['’](?![A-Za-z])")
KIND = r"(?:(?:forbidden|banned|prohibited|following|taboo|restricted|secret)\s+)?(?:words?|terms?|phrases?|subjects?|topics?|keywords?)"


def _quoted(s: str) -> list[str]:
    out = []
    for m in QUOTED.finditer(s):
        t = (m.group(1) or m.group(2) or "").strip()
        if t and len(t.split()) <= 4 and "<" not in t and re.search(r"[A-Za-z0-9]", t):
            out.append(t)
    return out


def _bare_list(s: str, limit: int = 6) -> list[str]:
    """`harbor, anchor or dock` -> terms, until a clause end; stop words dropped."""
    s = re.split(r"[.!?\n(]|\bin\s+(?:your|the)\b|\bduring\b|\bwhen\b|\bwhile\b|\bor\s+you\b|\botherwise\b|\bbecause\b|\bsince\b|\bunless\b|\bif\b", s)[0]
    out = []
    for part in re.split(r",|;|\s+or\s+|\s+and\s+|/", s):
        toks = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", part)]
        while toks and toks[0].lower() in STOP:
            toks.pop(0)
        while toks and toks[-1].lower() in STOP:
            toks.pop()
        if toks and len(toks) <= 3 and not all(t.lower() in STOP for t in toks):
            out.append(" ".join(toks))
        if len(out) >= limit:
            break
    return out


def extract_terms(rules: str) -> list[str]:
    """Forbidden words / subjects named in the rules. Order kept, duplicates (case-insensitive) dropped."""
    text = str(rules or "")[:20000]
    found: list[str] = []

    def add(ts):
        for t in ts:
            t = t.strip().strip(".,;:!?").strip()
            if 2 <= len(t) <= 40 and t.lower() not in STOP and t.lower() not in {x.lower() for x in found}:
                found.append(t)

    # A. "never say the word "x"", "must not mention harbor", "do not talk about the sea"
    pat_a = re.compile(rf"\b(?:{NEG})\s+(?:ever\s+|even\s+)?(?:{VERBS})\s+(?:the\s+|any\s+of\s+the\s+|a\s+|an\s+)?"
                       rf"(?:(?P<kind>{KIND})\s*:?\s*)?(?P<rest>[^\n]{{0,160}})", re.I)
    for m in pat_a.finditer(text):
        rest = m.group("rest")
        q = _quoted(rest.split(".")[0] if QUOTED.search(rest.split(".")[0]) else "")
        if q:
            add(q)
        elif m.group("kind"):
            add(_bare_list(rest))
    # B. "forbidden words: a, b", "banned topics are x and y", "Forbidden subject: harbor"
    pat_b = re.compile(rf"\b(?:forbidden|banned|prohibited|taboo|restricted|off-limits)\s+(?:words?|terms?|phrases?|subjects?|topics?|keywords?|content)?"
                       rf"\s*(?:\([^)\n]*\)\s*)?(?:are|is|include|includes|list|=|:|-)\s*(?P<rest>[^\n]{{0,200}})", re.I)
    for m in pat_b.finditer(text):
        rest = m.group("rest").strip()
        add(_quoted(rest) or _bare_list(rest))
    # C. quoted words in a sentence that talks about forbidden speech
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        if re.search(rf"\b(?:{NEG}|forbidden|banned|prohibited|taboo|off-limits|speech rule|penalt|lose)", sent, re.I) and \
                re.search(r"\b(?:say|said|saying|mention|word|words|chat|talk|speak|utter|term|phrase|topic|subject|spoken|speech)\b", sent, re.I):
            if re.search(r"ACTION FORMAT|e\.g\.|answer\s+(?:exactly|with|only)", sent, re.I):
                continue
            add(_quoted(sent))
    return found[:MAX_BASE]


def _strip_marks(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def fold(s: str) -> str:
    """lowercase, no diacritics, leetspeak mapped back to letters (l and i are merged)."""
    s = _strip_marks(str(s)).lower()
    return "".join(_LEET_TO_LETTER.get(c, c) for c in s)


def _plural_forms(w: str) -> set[str]:
    return {w, w + "s", w + "es", w + "ed", w + "ing", w + "er", w + "ers", w + "'s", w + "ly"} | \
           ({w[:-1] + "ies", w[:-1] + "ied"} if w.endswith("y") and len(w) > 2 else set())


def contains(text, terms) -> str | None:
    """The first forbidden term found in `text`, else None. Word-aware for short terms; spaced-out letters and
    leetspeak ("h4rbor", "h a r b o r") are caught for terms of 5+ letters."""
    try:
        t = str(text or "")[:5000]
        if not t.strip() or not terms:
            return None
        folded = fold(t)
        tokens = re.findall(r"[a-z0-9']+", folded)
        squashed = re.sub(r"[^a-z0-9]+", "", folded)
        seen = set()
        for term in terms:
            if not isinstance(term, str) or not term.strip():
                continue
            ft = fold(term)
            words = re.findall(r"[a-z0-9']+", ft)
            key = "".join(words)
            if not key or key in seen:
                continue
            seen.add(key)
            if len(key) >= 5:
                if key in squashed:
                    return term
            else:
                n = len(words)
                for i in range(len(tokens) - n + 1):
                    if all(tokens[i + k] == words[k] for k in range(n - 1)) and tokens[i + n - 1] in _plural_forms(words[-1]):
                        return term
        return None
    except Exception:
        return None


def variants(term: str, limit: int = 60) -> list[str]:
    base = _strip_marks(str(term).strip())
    if not base:
        return []
    plain = base.lower()
    forms = {str(term).strip(), plain, plain.upper(), plain.title(), plain.capitalize()}
    for p in _plural_forms(plain.replace(" ", "")) | _plural_forms(plain):
        forms.add(p)
    sq = plain.replace(" ", "")
    for sep in ("", " ", "-", "_", "."):
        forms.add(sep.join(sq))
    forms.add("".join(_LETTER_TO_LEET[c][0] if c in _LETTER_TO_LEET else c for c in sq))
    for i, c in enumerate(sq):
        for r in _LETTER_TO_LEET.get(c, ""):
            forms.add(sq[:i] + r + sq[i + 1:])
    out = [str(term).strip()] + sorted(f for f in forms if f and f != str(term).strip())
    return out[:limit]


def expand(terms, use_guard: bool = False) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def push(x):
        x = str(x).strip()
        if x and x not in seen and len(out) < MAX_TERMS:
            seen.add(x)
            out.append(x)

    base = [str(t).strip() for t in (terms or []) if str(t).strip()][:MAX_BASE]
    for t in base:
        push(t)
    for t in base:
        forms = variants(t)
        if use_guard:
            try:
                from solvers.guard import forbidden_variants
                forms = forms + list(forbidden_variants(t, limit=80))
            except Exception:
                pass
        for f in forms:
            push(f)
    return out


def merge(rules: str, model_terms=None, extra=None, use_guard: bool = False) -> list[str]:
    """Base terms from the rules (code), from the model (prep) and from other extractors, with variants."""
    base: list[str] = []
    for src in (extract_terms(rules), list(model_terms or []), list(extra or [])):
        for t in src:
            t = str(t).strip()
            if t and t.lower() not in {b.lower() for b in base}:
                base.append(t)
    return expand(base, use_guard)


def safe_action(action, terms, legal=None, fmt=None, art=None, avoid=(), observation: str = "", warning=None) -> str:
    """`action` itself when clean; otherwise a clean legal move, a template value or a clean fallback. Never a cut-off string."""
    if not contains(action, terms):
        return action
    avoid = list(avoid) + [action]
    if isinstance(legal, list) and legal:
        for a in legal:
            if not contains(a, terms) and str(a) not in avoid:
                return str(a)
        return str(action)  # every legal move is forbidden: nothing better exists
    from core import actionfmt, fallback
    if fmt:
        for _ in range(8):
            cand = actionfmt.fill(fmt, avoid, observation)
            if cand and not contains(cand, terms):
                return cand
            if cand:
                avoid.append(cand)
    for _ in range(8):
        cand = fallback.fallback_action(legal, art or {}, avoid_also=avoid, observation=observation, warning=warning)
        if not contains(cand, terms):
            return cand
        avoid.append(cand)
    return fallback.fallback_action(None, {}, avoid_also=avoid)
