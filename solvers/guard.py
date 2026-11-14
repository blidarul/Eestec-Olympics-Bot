"""Layer 3, phase M5: forbidden-term library for mbappe's guardrails and chat filter (rules 6.8, 6.9).

forbidden_variants(term, translations=None) -> list of surface forms (case, diacritics, plurals, spacing,
leetspeak, listed translations). forbidden_check(text, terms, translations=None) -> {hit, term, position}.
Matching is word-aware (no "class" hit for "ass") and also catches spaced-out letters ("f u c k") and leetspeak.
Pure functions, stdlib only, never raise, no stdout. Game text only; never used on opponent chat as a tool input.
"""
import re
import unicodedata

LEET = {"a": "4@", "e": "3", "i": "1!", "o": "0", "s": "5$", "t": "7", "l": "1", "b": "8", "g": "9"}
_UNLEET = {"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t", "8": "b", "9": "g",
           "|": "l"}
_SEPS = ("", " ", "-", "_", ".")
MAX_VARIANTS = 400


def _strip_marks(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _plurals(w):
    out = [w, w + "s", w + "es"]
    if w.endswith("y") and len(w) > 2:
        out.append(w[:-1] + "ies")
    return out


def forbidden_variants(term, translations=None, limit=MAX_VARIANTS):
    """Surface forms of `term`. `translations`: {term: [other-language forms]} (from artifacts)."""
    try:
        base = {str(term).strip()}
        tr = translations.get(term) if isinstance(translations, dict) else None
        if isinstance(tr, (list, tuple)):
            base.update(str(t).strip() for t in tr[:50])
        out = []
        for b in [x for x in base if x]:
            plain = _strip_marks(b).lower()
            words = plain.split()
            forms = {b, b.lower(), b.upper(), b.title(), plain}
            for p in _plurals(plain):
                forms.add(p)
            for sep in _SEPS:
                forms.add(sep.join(words))
                forms.add(sep.join(plain.replace(" ", "")))   # f-u-c-k, f.u.c.k, f u c k
            squashed = plain.replace(" ", "")
            full = "".join((LEET[c][0] if c in LEET else c) for c in squashed)
            forms.add(full)
            for i, c in enumerate(squashed):                   # one leet substitution at a time
                for r in LEET.get(c, ""):
                    forms.add(squashed[:i] + r + squashed[i + 1:])
            out.extend(sorted(forms))
        return list(dict.fromkeys(out))[:max(1, int(limit))]
    except Exception:  # noqa: BLE001
        return [str(term)]


def _fold_token(tok):
    tok = _strip_marks(tok).lower()
    if any(c.isalpha() for c in tok):
        tok = "".join(_UNLEET.get(c, c) for c in tok.rstrip("!"))
    return tok


def _tokens(text):
    """[(folded token, start position)]; runs of 3+ single letters are glued into one token (spaced-out words)."""
    toks = [(_fold_token(m.group(0)), m.start()) for m in re.finditer(r"[^\W_]+|[@$!|]+", str(text)[:20000])]
    toks = [(t, p) for t, p in toks if t]
    out, i = [], 0
    while i < len(toks):
        j = i
        while j < len(toks) and len(toks[j][0]) == 1 and toks[j][0].isalpha():
            j += 1
        if j - i >= 3:
            out.append(("".join(t for t, _ in toks[i:j]), toks[i][1]))
            i = j
        else:
            out.append(toks[i])
            i += 1
    return out


def _term_forms(term, translations):
    forms = [term]
    tr = translations.get(term) if isinstance(translations, dict) else None
    if isinstance(tr, (list, tuple)):
        forms.extend(str(t) for t in tr[:50])
    return forms


def forbidden_check(text, terms, translations=None):
    """First hit of any term (or its listed translations) in text -> {"hit": bool, "term", "position"}."""
    none = {"hit": False, "term": None, "position": -1}
    try:
        if not text or not terms:
            return none
        toks = _tokens(text)
        words = [t for t, _ in toks]
        best = None
        for term in [t for t in terms if isinstance(t, str) and t.strip()][:500]:
            for form in _term_forms(term, translations):
                fw = [_fold_token(w) for w in re.findall(r"[^\W_]+|[@$!|]+", form)]
                fw = [w for w in fw if w]
                if not fw:
                    continue
                joined = "".join(fw)
                n = len(fw)
                for i in range(len(words)):
                    if n > 1 and i + n <= len(words) and all(words[i + k] == fw[k] for k in range(n - 1))                             and words[i + n - 1] in _plurals(fw[-1]):
                        pass
                    elif words[i] in _plurals(joined):
                        pass
                    else:
                        continue
                    if best is None or toks[i][1] < best[0]:
                        best = (toks[i][1], term)
                    break
        if best is None:
            return none
        return {"hit": True, "term": best[1], "position": best[0]}
    except Exception:  # noqa: BLE001
        return none


from solvers import catalog  # noqa: E402
from solvers.catalog import ToolSpec  # noqa: E402


def _check_tool(args, deadline):
    return forbidden_check(args["text"], args["terms"], args.get("translations"))


catalog.register(ToolSpec(
    name="forbidden_check", summary="Harness-only: does a text contain a forbidden term (case, diacritics, plurals, spacing, leetspeak).",
    params={"type": "object", "properties": {"text": {"type": "string"}, "terms": {"type": "array", "items": {"type": "string"}},
                                              "translations": {"type": "object"}},
            "required": ["text", "terms"]},
    fn=_check_tool, families=("guardrails", "any"), model_callable=False, max_ms=500))
