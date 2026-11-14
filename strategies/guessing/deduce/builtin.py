"""Built-in feedback models detected from the rules text (no model-written code needed). General, no game names (10.7).

detect(rules, variant) -> Builtin | None. Builtin has the same interface as model.Model:
space(variant), history(observation), feedback(secret, guess), format(guess).
Covered: numeric (higher/lower/correct on an integer range) and distance (exact |secret-guess| on an integer range).
Pegs, positional and other layouts are NOT detected here: they still need a verified model-written feedback model.
"""
import re

from solvers.deduce import make_model

_RANGE = (r"(?:range|between|from)\s*(-?\d+)\s*(?:-|–|to|and|\.\.)\s*(-?\d+)",
          r"(-?\d+)\s*(?:-|–|to|\.\.)\s*(-?\d+)")
_OPP = re.compile(r"opponent['’]s\s+guesses", re.I)
_LINE = re.compile(r"(?:guess(?:ed)?\s+)?(-?\d+)\s*(?:->|→|=>|:)\s*([A-Za-z][A-Za-z ]*)")


def _range(text):
    for pat in _RANGE:
        m = re.search(pat, text, re.I)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo < hi:
                return lo, hi
    return None


def _kind(text):
    t = text.lower()
    if all(w in t for w in ("higher", "lower")) and not re.search(r"\b(distance|hot|cold|warm)\b", t):
        return "numeric"
    if re.search(r"\bdistance\b", t) and re.search(r"\b(exact|how far|away)\b", t) and "higher" not in t:
        return "distance"
    return None


class Builtin:
    def __init__(self, kind, lo, hi, prefix):
        self.kind, self.lo, self.hi, self.prefix = kind, lo, hi, prefix
        self._m = make_model(kind, {"lo": lo, "hi": hi})

    def space(self, variant=None):
        return list(self._m.candidates())

    def history(self, observation):
        obs = str(observation or "")
        parts = _OPP.split(obs, maxsplit=1)
        out = []
        for g, fb in _LINE.findall(parts[0]):
            try:
                out.append((self._m.parse_guess(g), self._m.parse_feedback(fb.strip())))
            except Exception:
                continue
        return out

    def feedback(self, secret, guess):
        return self._m.feedback(secret, guess)

    def format(self, guess):
        return f"{self.prefix}{guess}"


def detect(rules, variant=None):
    try:
        text = str(rules or "")
        kind = _kind(text)
        if kind is None:
            return None
        rg = None
        v = variant or {}
        if isinstance(v.get("lo"), int) and isinstance(v.get("hi"), int):
            rg = (v["lo"], v["hi"])
        rg = rg or _range(text)
        if rg is None:
            return None
        prefix = "guess " if re.search(r"guess\s*<\w+>", text, re.I) else ""
        return Builtin(kind, rg[0], rg[1], prefix)
    except Exception:
        return None
