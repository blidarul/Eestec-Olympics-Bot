"""Layer 3, M1: guessing that deduces. General (no game names, rule 10.7), stdlib only, no stdout.

    best_guess(candidates, guess_pool, feedback_fn, mode, deadline, exclude=()) -> guess | None
    MODELS: numeric | pegs | positional | distance   (each: candidates(params), feedback(secret, guess),
                                                      parse_guess / parse_feedback for text and JSON input)
    deduce(model, params, history, mode, deadline, words=None, feedback_model=None) -> dict
    tool `deduce_next` (model-callable, family guessing)

Feedback models are chosen and parameterized by the caller. If bld's prep produced a verified feedback model, pass it
as `feedback_model` (object with `space() -> list`, `feedback(secret, guess)`): it is used instead of the built-ins.
Nothing here reads the opponent's chat (rules 6.5, 6.7); the model never sees code, only data.
"""
import itertools
import math
import time
from collections import Counter

from solvers.catalog import ToolError, ToolSpec, register

MAX_CANDIDATES = 60000
PROBE = 250        # candidates scored per guess
POOL = 250         # guesses scored
_BIG = 10 ** 9


# ------------------------------------------------------------------ best_guess

def _expired(deadline):
    return deadline is not None and time.monotonic() >= deadline


def _spread(seq, n):
    """At most n items spread evenly over seq."""
    if len(seq) <= n:
        return list(seq)
    step = len(seq) / float(n)
    return [seq[int(i * step)] for i in range(n)]


def _score(groups, total, mode):
    if mode == "minimax":
        return (max(groups.values()), -len(groups))              # smaller is better
    ent = 0.0
    for c in groups.values():
        p = c / total
        ent -= p * math.log2(p)
    return (-ent,)                                               # smaller is better


def best_guess(candidates, guess_pool, feedback_fn, mode="entropy", deadline=None, exclude=()):
    """Guess with maximum expected information ('entropy') or smallest worst-case group ('minimax').

    Never returns a guess in `exclude` (already made). Samples candidates x pool when too large; ties prefer a guess that
    is itself a candidate. With one candidate left it returns it. None when nothing is left to guess."""
    cands = list(candidates)
    excl = set(exclude)
    cands = [c for c in cands if c not in excl]
    if not cands:
        pool0 = [g for g in (guess_pool or []) if g not in excl]
        return pool0[0] if pool0 else None
    if len(cands) <= 2 or feedback_fn is None:
        return cands[0]
    pool = cands if guess_pool is None else [g for g in guess_pool if g not in excl]
    if not pool:
        return cands[0]
    cset = set(cands)
    probe = _spread(cands, PROBE)
    if len(pool) > POOL:
        # candidates first (they can win), then an even sample of the rest of the pool
        head = [g for g in pool if g in cset]
        rest = [g for g in pool if g not in cset]
        pool = _spread(head, POOL if not rest else POOL // 2) + _spread(rest, POOL // 2)
    best, best_key = None, None
    for g in pool:
        if best is not None and _expired(deadline):
            break
        groups = Counter(feedback_fn(c, g) for c in probe)
        key = _score(groups, len(probe), mode) + (0 if g in cset else 1,)
        if best_key is None or key < best_key:
            best, best_key = g, key
    return best if best is not None else cands[0]


# ------------------------------------------------------------------ feedback models

def _int(v, name, lo, hi):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ToolError("params.%s must be an integer in %d..%d" % (name, lo, hi))
    return v


def _alphabet(v):
    if isinstance(v, str):
        a = list(dict.fromkeys(v))
    elif isinstance(v, list) and all(isinstance(x, str) and x for x in v):
        a = list(dict.fromkeys(v))
    else:
        raise ToolError("params.alphabet must be a string or a list of symbols")
    if not 2 <= len(a) <= 64:
        raise ToolError("params.alphabet needs 2..64 symbols")
    return a


class NumericModel:
    """Secret integer in lo..hi; feedback 'higher' (secret > guess), 'lower', 'correct'."""
    name = "numeric"

    def __init__(self, params):
        self.lo = _int(params.get("lo"), "lo", -_BIG, _BIG)
        self.hi = _int(params.get("hi"), "hi", -_BIG, _BIG)
        if self.lo > self.hi:
            raise ToolError("params.lo must be <= params.hi")

    def candidates(self):
        n = self.hi - self.lo + 1
        if n > MAX_CANDIDATES * 10:
            raise ToolError("range too large")
        return range(self.lo, self.hi + 1)

    def feedback(self, secret, guess):
        return "correct" if secret == guess else ("higher" if secret > guess else "lower")

    def parse_guess(self, g):
        try:
            return int(str(g).strip())
        except (TypeError, ValueError):
            raise ToolError("guess %r is not an integer" % (g,))

    def parse_feedback(self, f):
        t = str(f).lower()
        for words, tag in ((("too low", "higher", "greater", "bigger", "larger", "up"), "higher"),
                           (("too high", "lower", "smaller", "less", "down"), "lower"),
                           (("correct", "exact", "right", "win", "found"), "correct")):
            if any(w in t for w in words):
                return tag
        raise ToolError("feedback %r not understood (higher/lower/correct)" % (f,))

    def fmt(self, g):
        return str(g)

    def won(self, fb):
        return fb == "correct"


class PegsModel:
    """Secret = `length` symbols from `alphabet`; feedback (exact, partial): right symbol in place / right symbol misplaced."""
    name = "pegs"

    def __init__(self, params):
        self.length = _int(params.get("length"), "length", 1, 12)
        self.alpha = _alphabet(params.get("alphabet"))
        self.repeat = bool(params.get("repeat", True))
        if not self.repeat and self.length > len(self.alpha):
            raise ToolError("length exceeds alphabet size without repetition")
        n = len(self.alpha) ** self.length if self.repeat else math.perm(len(self.alpha), self.length)
        if n > MAX_CANDIDATES:
            raise ToolError("candidate space too large (%d > %d)" % (n, MAX_CANDIDATES))
        self.size = n

    def candidates(self):
        it = (itertools.product(self.alpha, repeat=self.length) if self.repeat
              else itertools.permutations(self.alpha, self.length))
        return list(it)

    def feedback(self, secret, guess):
        exact = sum(1 for a, b in zip(secret, guess) if a == b)
        common = sum((Counter(secret) & Counter(guess)).values())
        return (exact, common - exact)

    def parse_guess(self, g):
        if isinstance(g, (list, tuple)):
            t = tuple(str(x) for x in g)
        else:
            s = str(g).strip()
            t = tuple(s) if all(len(a) == 1 for a in self.alpha) else tuple(s.replace(",", " ").split())
        if len(t) != self.length or any(x not in self.alpha for x in t):
            raise ToolError("guess %r does not fit length/alphabet" % (g,))
        return t

    def parse_feedback(self, f):
        import re
        if isinstance(f, (list, tuple)) and len(f) == 2 and all(isinstance(x, int) for x in f):
            return (f[0], f[1])
        s = str(f).lower()
        mx = re.search(r"(\d+)\s*(?:exact|bull|black|correct pos|right pos|in place|well|hit)", s)
        mp = re.search(r"(\d+)\s*(?:partial|cow|white|misplaced|wrong pos|present|close|blow)", s)
        if mx and mp:
            return (int(mx.group(1)), int(mp.group(1)))
        nums = re.findall(r"\d+", s)
        if len(nums) == 2:
            return (int(nums[0]), int(nums[1]))
        raise ToolError("feedback %r not understood (exact, partial)" % (f,))

    def fmt(self, g):
        return "".join(g) if all(len(a) == 1 for a in self.alpha) else " ".join(g)

    def won(self, fb):
        return fb[0] == self.length


class PositionalModel:
    """Secret word/string; feedback per position: 2 exact, 1 present elsewhere, 0 absent (duplicates counted once)."""
    name = "positional"

    def __init__(self, params, words=None):
        self.length = _int(params.get("length"), "length", 1, 15)
        w = params.get("words") or words
        if isinstance(w, list) and w:
            self.words = [x.lower() if params.get("lower", True) else x for x in w
                          if isinstance(x, str) and len(x) == self.length][:MAX_CANDIDATES]
            self.words = list(dict.fromkeys(self.words))
            if not self.words:
                raise ToolError("no word of length %d in the word list" % self.length)
            self.alpha = None
        else:
            self.words = None
            self.alpha = _alphabet(params.get("alphabet", "abcdefghijklmnopqrstuvwxyz"))
            if len(self.alpha) ** self.length > MAX_CANDIDATES:
                raise ToolError("no word list and space too large; pass params.words")

    def candidates(self):
        if self.words is not None:
            return list(self.words)
        return ["".join(t) for t in itertools.product(self.alpha, repeat=self.length)]

    def feedback(self, secret, guess):
        res = [0] * len(guess)
        left = Counter()
        for i, (s, g) in enumerate(zip(secret, guess)):
            if s == g:
                res[i] = 2
            else:
                left[s] += 1
        for i, g in enumerate(guess):
            if res[i] == 0 and left[g] > 0:
                res[i] = 1
                left[g] -= 1
        return tuple(res)

    def parse_guess(self, g):
        s = str(g).strip().lower() if self.words is not None else str(g).strip()
        if len(s) != self.length:
            raise ToolError("guess %r must have %d characters" % (g, self.length))
        return s

    _MAP = {"g": 2, "2": 2, "+": 2, "c": 2, "y": 1, "1": 1, "?": 1, "p": 1, "x": 0, "0": 0, "-": 0, ".": 0, "_": 0,
            "b": 0, "w": 0, "n": 0, "a": 0,
            "\U0001f7e9": 2, "\U0001f7e8": 1, "⬛": 0, "⬜": 0}
    _WORD = {"green": 2, "correct": 2, "exact": 2, "yellow": 1, "present": 1, "misplaced": 1, "elsewhere": 1,
             "gray": 0, "grey": 0, "absent": 0, "black": 0, "none": 0, "miss": 0}

    def parse_feedback(self, f):
        if isinstance(f, (list, tuple)) and len(f) == self.length and all(isinstance(x, int) for x in f):
            return tuple(f)
        s = str(f).strip().lower()
        toks = s.replace(",", " ").split()
        if len(toks) == self.length and all(t in self._WORD or t in self._MAP for t in toks):
            return tuple(self._WORD[t] if t in self._WORD else self._MAP[t] for t in toks)
        chars = [c for c in s if not c.isspace() and c not in ",|[]()"]
        if len(chars) == self.length and all(c in self._MAP for c in chars):
            return tuple(self._MAP[c] for c in chars)
        raise ToolError("feedback %r not understood (one mark per position)" % (f,))

    def fmt(self, g):
        return g

    def won(self, fb):
        return all(x == 2 for x in fb)


class DistanceModel:
    """Secret integer in lo..hi; feedback = distance, either exact |s-g| or a bucket index from ascending `edges`
    (bucket i = first edge >= distance; hot/cold style). Distance 0 is always its own answer."""
    name = "distance"

    def __init__(self, params):
        self.lo = _int(params.get("lo"), "lo", -_BIG, _BIG)
        self.hi = _int(params.get("hi"), "hi", -_BIG, _BIG)
        if self.lo > self.hi or self.hi - self.lo + 1 > MAX_CANDIDATES * 10:
            raise ToolError("bad or too large range")
        e = params.get("edges")
        if e is None:
            self.edges = None
        else:
            if not (isinstance(e, list) and e and all(isinstance(x, int) and not isinstance(x, bool) for x in e)):
                raise ToolError("params.edges must be a list of integers")
            self.edges = sorted(set(e))

    def candidates(self):
        return range(self.lo, self.hi + 1)

    def feedback(self, secret, guess):
        d = abs(secret - guess)
        if self.edges is None or d == 0:
            return d if self.edges is None else -1
        for i, e in enumerate(self.edges):
            if d <= e:
                return i
        return len(self.edges)

    def parse_guess(self, g):
        try:
            return int(str(g).strip())
        except (TypeError, ValueError):
            raise ToolError("guess %r is not an integer" % (g,))

    def parse_feedback(self, f):
        if isinstance(f, int) and not isinstance(f, bool):
            return f
        import re
        t = str(f).strip().lower()
        if self.edges is None:
            m = re.search(r"-?\d+", t)
            if m:
                return abs(int(m.group(0)))
        else:
            if any(w in t for w in ("correct", "exact", "found")):
                return -1
            m = re.fullmatch(r"-?\d+", t)
            if m:
                return int(t)
        raise ToolError("feedback %r not understood (distance)" % (f,))

    def fmt(self, g):
        return str(g)

    def won(self, fb):
        return fb == 0 if self.edges is None else fb == -1


MODELS = {"numeric": NumericModel, "pegs": PegsModel, "positional": PositionalModel, "distance": DistanceModel}


def make_model(name, params, words=None):
    cls = MODELS.get(name)
    if cls is None:
        raise ToolError("unknown model %r (numeric, pegs, positional, distance)" % (name,))
    if not isinstance(params, dict):
        raise ToolError("params must be an object")
    return cls(params, words) if cls is PositionalModel else cls(params)


# ------------------------------------------------------------------ solving

def _made(entries):
    return [g for g, _ in entries]


def _greedy_depth(cands, fb, mode, deadline, depth=0):
    """Guesses needed along the worst-case-group path with the chosen guesses (an upper bound by greedy play)."""
    if len(cands) <= 1:
        return 0 if not cands else 1
    if depth > 14 or _expired(deadline):
        return None
    g = best_guess(cands, cands, fb, mode, deadline)
    groups = {}
    for c in cands:
        groups.setdefault(fb(c, g), []).append(c)
    worst = max(groups.values(), key=len)
    if worst is cands or len(worst) == len(cands):
        return None
    sub = _greedy_depth(worst, fb, mode, deadline, depth + 1)
    return None if sub is None else 1 + sub


def deduce(model, params, history, mode="entropy", deadline=None, words=None, feedback_model=None):
    """Filter the candidates by `history` [{"guess", "feedback"}] and pick the next guess. Returns a dict:
    next_guess, next_guess_text, candidates (left), guesses_made, certain, max_guesses_needed (greedy bound or None)."""
    if mode not in ("entropy", "minimax"):
        raise ToolError("mode must be entropy or minimax")
    if feedback_model is not None:
        space = list(feedback_model.space())[:MAX_CANDIDATES]
        fb = feedback_model.feedback
        m = None
    else:
        m = make_model(model, params, words)
        space = m.candidates()
        space = list(space)
        fb = m.feedback
    entries = []
    for h in history or []:
        if not isinstance(h, dict) or "guess" not in h or "feedback" not in h:
            raise ToolError("history items need guess and feedback")
        if m is not None:
            entries.append((m.parse_guess(h["guess"]), m.parse_feedback(h["feedback"])))
        else:
            g = h["guess"]
            if space and isinstance(space[0], int) and not isinstance(space[0], bool):
                try:
                    g = int(str(g).strip())
                except ValueError:
                    raise ToolError("guess %r is not an integer" % (g,))
            entries.append((g, h["feedback"]))
    cands = space
    contradictory = False
    for g, f in entries:
        if _expired(deadline):
            break
        kept = [c for c in cands if fb(c, g) == f]
        if not kept:
            contradictory = True       # noisy or misparsed feedback: keep the previous set rather than emptying it
            continue
        cands = kept
    made = _made(entries)
    madeset = set(made)
    left = [c for c in cands if c not in madeset] or list(cands)   # a made guess is only kept if nothing else is left
    guess = best_guess(left, space if len(left) > 2 else left, fb, mode, deadline, exclude=made)
    if guess is None:
        guess = left[0] if left else None
    text = (m.fmt(guess) if m is not None else str(guess)) if guess is not None else None
    already_won = m is not None and any(m.won(f) for _, f in entries)
    res = {"model": model, "candidates": len(left), "next_guess": _jsonable(guess), "next_guess_text": text,
           "guesses_made": len(made), "certain": len(left) == 1 and not already_won,
           "solved": bool(already_won), "contradictory_history": contradictory}
    if len(left) <= 400 and left:
        res["max_guesses_needed"] = _greedy_depth(left, fb, mode, deadline)
    if len(left) <= 8:
        res["remaining"] = [(m.fmt(c) if m is not None else str(c)) for c in left]
    res["explain"] = ("%d candidate%s left; next guess %s." % (len(left), "" if len(left) == 1 else "s", text)
                      if not already_won else "Already solved.")
    return res


def _jsonable(g):
    if isinstance(g, tuple):
        return list(g)
    return g


# ------------------------------------------------------------------ tool

def _deduce_next(args, deadline):
    return deduce(args["model"], args.get("params") or {}, args.get("history") or [], args.get("mode", "entropy"),
                  min(deadline, time.monotonic() + 1.5), words=args.get("words"))


register(ToolSpec(
    name="deduce_next",
    summary=("Hidden-secret guessing with feedback: keep only candidates consistent with the history and give the best next "
             "guess (max information or best worst case), the candidates left, and whether the answer is certain. Models: "
             "numeric (higher/lower; params lo,hi), pegs (exact,partial; params length,alphabet,repeat), positional "
             "(per-position green/yellow/gray; params length, optional words), distance (params lo,hi, optional edges)."),
    params={"type": "object",
            "properties": {
                "model": {"type": "string", "enum": list(MODELS)},
                "params": {"type": "object", "description": "model parameters, see summary"},
                "history": {"type": "array", "maxItems": 100,
                            "description": "guesses so far: {guess, feedback}; pegs feedback like [2,1] or '2 exact 1 partial'; positional like 'gyxxg'",
                            "items": {"type": "object", "required": ["guess", "feedback"]}},
                "mode": {"type": "string", "enum": ["entropy", "minimax"]},
                "words": {"type": "array", "maxItems": 20000, "description": "positional only: allowed words",
                          "items": {"type": "string", "maxLength": 15}}},
            "required": ["model", "params"]},
    fn=_deduce_next, families=("guessing",), model_callable=True, max_ms=2000))
