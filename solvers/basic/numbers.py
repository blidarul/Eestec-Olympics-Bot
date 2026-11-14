"""Number-guessing and dice tools: binary search, monotone threshold search, dice sums.

General tools (no game names, rule 10.7): plain data in, plain data out, stdlib only.
"""
import time
from fractions import Fraction

from solvers.catalog import ToolError, ToolSpec, register

_BIG = 10 ** 18
_FEEDBACK = ("higher", "lower", "correct")


def _check_time(deadline):
    if time.monotonic() > deadline:
        raise ToolError("deadline exceeded")


# ---------------------------------------------------------------- binary_search_next

def binary_search_next(args, deadline):
    lo, hi = args["lo"], args["hi"]
    if lo > hi:
        raise ToolError("lo must be <= hi")
    guessed = set()
    found = None
    for item in args.get("history", []):
        g, fb = item["guess"], item["feedback"]
        guessed.add(g)
        if fb == "higher":      # secret > guess
            lo = max(lo, g + 1)
        elif fb == "lower":     # secret < guess
            hi = min(hi, g - 1)
        else:                   # correct
            if found is not None and found != g:
                raise ToolError("history has two different 'correct' guesses")
            found = g
    if found is not None:
        if not (args["lo"] <= found <= args["hi"]) or not (lo <= found <= hi):
            raise ToolError("history contradicts itself: 'correct' guess %d lies outside the interval %d..%d" % (found, lo, hi))
        return {"lo": found, "hi": found, "next_guess": found, "candidates": 1,
                "max_guesses_left": 0, "found": True,
                "explain": "Already found: %d." % found}
    if lo > hi:
        raise ToolError("history contradicts itself: empty interval")
    # midpoint; fall back to the nearest not-yet-guessed value (only needed if feedback was odd)
    mid = (lo + hi) // 2
    guess = mid
    if guess in guessed:
        guess = None
        for d in range(1, hi - lo + 2):
            for cand in (mid - d, mid + d):
                if lo <= cand <= hi and cand not in guessed:
                    guess = cand
                    break
            if guess is not None:
                break
            if d % 1024 == 0:
                _check_time(deadline)
        if guess is None:
            raise ToolError("every value in the interval was already guessed")
    n = hi - lo + 1
    return {"lo": lo, "hi": hi, "next_guess": guess, "candidates": n,
            "max_guesses_left": n.bit_length(), "found": False,
            "explain": "Interval %d..%d (%d candidates): guess %d, at most %d guesses left." % (lo, hi, n, guess, n.bit_length())}


register(ToolSpec(
    name="binary_search_next",
    summary="Guess a hidden integer with higher/lower feedback: gives the remaining interval, the next midpoint guess and the guaranteed number of guesses left.",
    params={"type": "object",
            "properties": {
                "lo": {"type": "integer", "minimum": -_BIG, "maximum": _BIG, "description": "smallest possible value"},
                "hi": {"type": "integer", "minimum": -_BIG, "maximum": _BIG, "description": "largest possible value"},
                "history": {"type": "array", "maxItems": 1000, "description": "guesses so far; feedback says where the secret is relative to the guess",
                            "items": {"type": "object", "required": ["guess", "feedback"],
                                      "properties": {"guess": {"type": "integer", "minimum": -_BIG, "maximum": _BIG},
                                                     "feedback": {"type": "string", "enum": list(_FEEDBACK)}}}}},
            "required": ["lo", "hi"]},
    fn=binary_search_next, families=("guessing",), model_callable=True, max_ms=1000))


# ---------------------------------------------------------------- bisect_predicate_points

def _mid(a, b, integer, up=False):
    if not integer:
        return (a + b) / 2
    return -((-(a + b)) // 2) if up else (a + b) // 2


def bisect_predicate_points(args, deadline):
    pts = args["points"]
    no = [p["x"] for p in pts if not p["ok"]]
    yes = [p["x"] for p in pts if p["ok"]]
    lo_dom, hi_dom = args.get("lo"), args.get("hi")
    if lo_dom is not None and hi_dom is not None and lo_dom > hi_dom:
        raise ToolError("lo must be <= hi")
    last_no = max(no) if no else None
    first_yes = min(yes) if yes else None
    if last_no is not None and first_yes is not None and last_no >= first_yes:
        raise ToolError("points are not monotone: x=%s failed but x=%s (not larger) passed" % (last_no, first_yes))
    xs = [p["x"] for p in pts] + [v for v in (lo_dom, hi_dom) if v is not None]
    integer = args.get("integer")
    if integer is None:
        integer = all(isinstance(x, int) for x in xs)
    tol = 1 if integer else args.get("tolerance", 1e-9)

    def out(next_x, done, status, text):
        return {"bracket": [last_no, first_yes], "next_x": next_x, "done": done,
                "threshold": first_yes if done and first_yes is not None else None,
                "status": status, "explain": text}

    if last_no is not None and first_yes is not None:
        if first_yes - last_no <= tol:
            return out(None, True, "found", "Threshold is %s (last no %s, first yes %s)." % (first_yes, last_no, first_yes))
        nx = _mid(last_no, first_yes, integer)
        return out(nx, False, "bracketed", "Bracket [%s, %s]: test %s next." % (last_no, first_yes, nx))
    if last_no is not None:   # only failures so far
        if hi_dom is not None:
            if last_no >= hi_dom:
                return out(None, True, "no_yes_in_range", "Even the largest value %s fails: no threshold in range." % hi_dom)
            nx = _mid(last_no, hi_dom, integer, up=True)
        else:
            nx = last_no + max(1, abs(last_no))
        return out(nx, False, "only_no", "Only failures (last %s): test %s next." % (last_no, nx))
    if first_yes is not None:  # only successes so far
        if lo_dom is not None:
            if first_yes <= lo_dom:
                return out(None, True, "found", "Even the smallest value %s passes: threshold is at the lower end." % first_yes)
            nx = _mid(lo_dom, first_yes, integer)
        else:
            nx = first_yes - max(1, abs(first_yes))
        return out(nx, False, "only_yes", "Only successes (first %s): test %s next." % (first_yes, nx))
    if lo_dom is None or hi_dom is None:
        raise ToolError("no points yet: give lo and hi to get a first x to test")
    nx = _mid(lo_dom, hi_dom, integer)
    return out(nx, False, "no_data", "No data: test the middle, %s." % nx)


_NUM = {"type": "number", "minimum": -1e18, "maximum": 1e18}
register(ToolSpec(
    name="bisect_predicate_points",
    summary="Find the threshold of a monotone yes/no test (no below, yes above): gives the bracket [last_no, first_yes] and the next x to test.",
    params={"type": "object",
            "properties": {
                "points": {"type": "array", "maxItems": 1000, "description": "tested points",
                           "items": {"type": "object", "required": ["x", "ok"],
                                     "properties": {"x": _NUM, "ok": {"type": "boolean"}}}},
                "lo": dict(_NUM, description="optional smallest x allowed"),
                "hi": dict(_NUM, description="optional largest x allowed"),
                "integer": {"type": "boolean", "description": "x must be an integer (default: true if all given x are integers)"},
                "tolerance": {"type": "number", "minimum": 0, "description": "stop when the bracket is this narrow (non-integer x only)"}},
            "required": ["points"]},
    fn=bisect_predicate_points, families=("guessing",), model_callable=True, max_ms=500))


# ---------------------------------------------------------------- dice_sum_distribution

_MAX_LISTED = 40


def _frac(f):
    return str(f)


def dice_sum_distribution(args, deadline):
    dice = args["dice"]
    target = args.get("target")
    # counts[s] = number of ways to reach sum s; one die at a time with a sliding-window sum
    counts = [1]
    for faces in dice:
        _check_time(deadline)
        size = len(counts) + faces
        prefix = [0] * (size + 1)
        acc = 0
        for i, c in enumerate(counts):
            acc += c
            prefix[i + 1] = acc
        new = []
        for s in range(size):
            # ways = sum of counts[s - f] for f in 1..faces  (new index s corresponds to sum s + len(dice_so_far)...)
            hi_i = min(s, len(counts) - 1)
            lo_i = max(0, s - faces + 1)
            new.append(prefix[hi_i + 1] - prefix[lo_i] if hi_i >= lo_i else 0)
        counts = new[:len(counts) + faces - 1]
    n = len(dice)
    total = 1
    for f in dice:
        total *= f
    # counts[i] is the number of ways to reach sum n + i
    dist = {n + i: Fraction(c, total) for i, c in enumerate(counts) if c}
    mean = Fraction(sum(f + 1 for f in dice), 2)
    var = Fraction(sum(f * f - 1 for f in dice), 12)
    mode_sum = max(dist, key=lambda s: (dist[s], -s))
    res = {"dice": dice, "outcomes": total, "min_sum": n, "max_sum": sum(dice),
           "expected_value": _frac(mean), "expected_value_decimal": float(mean),
           "variance_decimal": round(float(var), 6), "most_likely_sum": mode_sum}
    if len(dist) <= _MAX_LISTED:
        res["distribution"] = [{"sum": s, "p": _frac(p), "decimal": round(float(p), 6)} for s, p in sorted(dist.items())]
    else:
        res["distribution_omitted"] = "more than %d distinct sums; pass a target for tail probabilities" % _MAX_LISTED
    text = "Sum of %s: mean %s." % ("+".join("d%d" % f for f in dice[:8]) + ("+..." if n > 8 else ""), round(float(mean), 3))
    if target is not None:
        p_eq = dist.get(target, Fraction(0))
        p_ge = sum((p for s, p in dist.items() if s >= target), Fraction(0))
        p_le = sum((p for s, p in dist.items() if s <= target), Fraction(0))
        res.update({"target": target,
                    "p_equal": _frac(p_eq), "p_equal_decimal": round(float(p_eq), 6),
                    "p_at_least": _frac(p_ge), "p_at_least_decimal": round(float(p_ge), 6),
                    "p_at_most": _frac(p_le), "p_at_most_decimal": round(float(p_le), 6)})
        text += " P(sum==%d)=%s, P(sum>=%d)=%s." % (target, _frac(p_eq), target, _frac(p_ge))
    res["explain"] = text
    return res


register(ToolSpec(
    name="dice_sum_distribution",
    summary="Exact distribution of the sum of dice (list of face counts, e.g. [6,6]): probabilities as fractions, expected value, and P(sum == target), P(sum >= target) if a target is given.",
    params={"type": "object",
            "properties": {
                "dice": {"type": "array", "minItems": 1, "maxItems": 30,
                         "items": {"type": "integer", "minimum": 1, "maximum": 1000},
                         "description": "number of faces of each die (faces are numbered 1..n)"},
                "target": {"type": "integer", "minimum": -10 ** 9, "maximum": 10 ** 9}},
            "required": ["dice"]},
    fn=dice_sum_distribution, families=("any",), model_callable=True, max_ms=2000))
