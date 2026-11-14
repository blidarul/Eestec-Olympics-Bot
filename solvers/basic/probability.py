"""Probability and decision tools (TOOLS_PLAN.md phase P3).

General tools (no game names, rule 10.7): plain data in, plain data out, stdlib only, no eval.
Exact arithmetic with `fractions` (strings like "1/36") plus a decimal next to every probability.
Probabilities may be given as numbers (0.25), decimal strings ("0.25") or fractions ("1/4").
"""
import math
import random
import time
from fractions import Fraction

from solvers.catalog import ToolError, ToolSpec, register

MAX_N = 2000           # largest n / population / number of trials
MAX_ITEMS = 200


def _check_time(deadline):
    if time.monotonic() > deadline:
        raise ToolError("deadline exceeded")


def _dec(f):
    return float("%.6g" % float(f))


def _fs(f):
    return str(Fraction(f))


def _big(n):
    """JSON-safe integer: huge values become strings, with their digit count."""
    return n if abs(n) < 10 ** 15 else str(n)


def _prob(x, label="p"):
    try:
        f = Fraction(str(x).strip())
    except (ValueError, ZeroDivisionError):
        raise ToolError("%s must be a number or a fraction like '1/6', got %r" % (label, x))
    if not 0 <= f <= 1:
        raise ToolError("%s must be between 0 and 1, got %s" % (label, x))
    return f


def _num(x, label="value"):
    if isinstance(x, bool):
        raise ToolError("%s must be a number" % label)
    try:
        return Fraction(str(x).strip())
    except (ValueError, ZeroDivisionError):
        raise ToolError("%s must be a number, got %r" % (label, x))


_P = {"type": ["number", "string"], "description": "probability 0..1: number, decimal string or fraction string like '1/6'"}
_V = {"type": ["number", "string"], "description": "number (or fraction string)"}


# ---------------------------------------------------------------- combinatorics

def combinatorics(args, deadline):
    kind = args["kind"]
    if kind == "multinomial":
        parts = args.get("parts")
        if not parts:
            raise ToolError("multinomial needs 'parts' (list of group sizes)")
        if sum(parts) > MAX_N:
            raise ToolError("sum of parts too large (max %d)" % MAX_N)
        v = math.factorial(sum(parts))
        for p in parts:
            v //= math.factorial(p)
        text = "multinomial%s = %s" % (parts, _short(v))
    elif kind == "factorial":
        n = _need_n(args)
        v = math.factorial(n)
        text = "%d! = %s" % (n, _short(v))
    else:
        n = _need_n(args)
        k = args.get("k")
        if k is None:
            raise ToolError("%s needs 'k'" % kind)
        if k > n:
            v = 0
        else:
            v = math.comb(n, k) if kind == "ncr" else math.perm(n, k)
        text = "%s(%d,%d) = %s" % ("C" if kind == "ncr" else "P", n, k, _short(v))
    return {"kind": kind, "value": _big(v), "digits": len(str(v)), "explain": text}


def _need_n(args):
    n = args.get("n")
    if n is None:
        raise ToolError("'n' is required for this kind")
    return n


def _short(v):
    s = str(v)
    return s if len(s) <= 24 else "%s... (%d digits)" % (s[:12], len(s))


register(ToolSpec(
    name="combinatorics",
    summary="Exact counting: nCr (combinations), nPr (ordered arrangements), n! or a multinomial coefficient from group sizes.",
    params={"type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["ncr", "npr", "factorial", "multinomial"]},
                "n": {"type": "integer", "minimum": 0, "maximum": MAX_N},
                "k": {"type": "integer", "minimum": 0, "maximum": MAX_N},
                "parts": {"type": "array", "maxItems": MAX_ITEMS, "items": {"type": "integer", "minimum": 0, "maximum": MAX_N},
                          "description": "group sizes for multinomial: (sum)! / prod(part!)"}},
            "required": ["kind"]},
    fn=combinatorics, families=("any",), model_callable=True, max_ms=500))


# ---------------------------------------------------------------- count_hands

def count_hands(args, deadline):
    cats = args["categories"]
    k = args["k"]
    total_cards = sum(c["count"] for c in cats)
    if total_cards > MAX_N:
        raise ToolError("deck too large (max %d cards)" % MAX_N)
    if k > total_cards:
        raise ToolError("cannot draw %d cards from a deck of %d" % (k, total_cards))
    # poly[j] = number of ways to take j cards from the categories processed so far
    poly = {0: 1}
    for c in cats:
        _check_time(deadline)
        lo = c.get("min", 0)
        hi = min(c.get("max", c["count"]), c["count"])
        if lo > hi:
            raise ToolError("category %r: min %d is above what is possible (%d)" % (c.get("name", "?"), lo, hi))
        new = {}
        for j, ways in poly.items():
            for t in range(lo, hi + 1):
                if j + t <= k:
                    new[j + t] = new.get(j + t, 0) + ways * math.comb(c["count"], t)
        poly = new
    ways = poly.get(k, 0)
    total = math.comb(total_cards, k)
    p = Fraction(ways, total) if total else Fraction(0)
    return {"ways": _big(ways), "total_hands": _big(total), "probability": _fs(p), "probability_decimal": _dec(p),
            "explain": "%s of %s possible %d-card draws fit the constraints: P = %s (%.4g)." % (
                _short(ways), _short(total), k, _fs(p) if len(_fs(p)) < 30 else "~" + str(_dec(p)), float(p))}


register(ToolSpec(
    name="count_hands",
    summary="Number and probability of drawing k cards (or items) from a deck described as categories with counts, where each category has an optional min/max number drawn (e.g. exactly 2 aces, at most 1 king).",
    params={"type": "object",
            "properties": {
                "categories": {"type": "array", "minItems": 1, "maxItems": 30,
                               "description": "partition of the deck; cards left over belong in an 'other' category",
                               "items": {"type": "object", "required": ["count"],
                                         "properties": {"name": {"type": "string", "maxLength": 40},
                                                        "count": {"type": "integer", "minimum": 0, "maximum": MAX_N, "description": "cards of this category in the deck"},
                                                        "min": {"type": "integer", "minimum": 0, "description": "at least this many drawn (default 0)"},
                                                        "max": {"type": "integer", "minimum": 0, "description": "at most this many drawn (default all)"}}}},
                "k": {"type": "integer", "minimum": 0, "maximum": MAX_N, "description": "number of cards drawn"}},
            "required": ["categories", "k"]},
    fn=count_hands, families=("any",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- hypergeometric / binomial_tail

def _tails(pmf, x, lo, hi):
    exact = pmf.get(x, Fraction(0))
    ge = sum((v for s, v in pmf.items() if s >= x), Fraction(0))
    le = sum((v for s, v in pmf.items() if s <= x), Fraction(0))
    return exact, ge, le


def _tail_result(pmf, x, mean, text_head):
    exact, ge, le = _tails(pmf, x, None, None)
    return {"x": x, "p_exactly": _fs(exact), "p_exactly_decimal": _dec(exact),
            "p_at_least": _fs(ge), "p_at_least_decimal": _dec(ge),
            "p_at_most": _fs(le), "p_at_most_decimal": _dec(le),
            "mean": _dec(mean),
            "explain": "%s: P(=%d)=%.4g, P(>=%d)=%.4g, P(<=%d)=%.4g, mean %.4g." % (
                text_head, x, float(exact), x, float(ge), x, float(le), float(mean))}


def hypergeometric(args, deadline):
    N, K, n, x = args["population"], args["successes"], args["draws"], args["x"]
    if K > N:
        raise ToolError("successes cannot exceed population")
    if n > N:
        raise ToolError("draws cannot exceed population")
    total = math.comb(N, n)
    pmf = {}
    for s in range(max(0, n - (N - K)), min(K, n) + 1):
        _check_time(deadline)
        pmf[s] = Fraction(math.comb(K, s) * math.comb(N - K, n - s), total)
    return _tail_result(pmf, x, Fraction(n * K, N) if N else Fraction(0),
                        "Drawing %d from %d with %d successes inside" % (n, N, K))


register(ToolSpec(
    name="hypergeometric",
    summary="Drawing without replacement: probability of exactly / at least / at most x successes when drawing 'draws' items from a population holding 'successes' good ones (cards left in the deck).",
    params={"type": "object",
            "properties": {
                "population": {"type": "integer", "minimum": 1, "maximum": MAX_N, "description": "items in the deck/pool"},
                "successes": {"type": "integer", "minimum": 0, "maximum": MAX_N, "description": "good items among them"},
                "draws": {"type": "integer", "minimum": 0, "maximum": MAX_N},
                "x": {"type": "integer", "minimum": 0, "maximum": MAX_N, "description": "number of successes asked about"}},
            "required": ["population", "successes", "draws", "x"]},
    fn=hypergeometric, families=("any",), model_callable=True, max_ms=1500))


def binomial_tail(args, deadline):
    n, x = args["n"], args["x"]
    p = _prob(args["p"])
    q = 1 - p
    pmf = {}
    for s in range(n + 1):
        if s % 64 == 0:
            _check_time(deadline)
        pmf[s] = math.comb(n, s) * p ** s * q ** (n - s)
    return _tail_result(pmf, x, n * p, "%d independent trials with success chance %s" % (n, _fs(p)))


register(ToolSpec(
    name="binomial_tail",
    summary="Independent trials (dice showing a face, repeated coin flips): probability of exactly / at least / at most x successes in n trials with success chance p. Use for dice bids: n = dice in play, p = 1/6.",
    params={"type": "object",
            "properties": {
                "n": {"type": "integer", "minimum": 0, "maximum": 500, "description": "number of trials (e.g. unseen dice)"},
                "p": _P,
                "x": {"type": "integer", "minimum": 0, "maximum": MAX_N, "description": "number of successes asked about"}},
            "required": ["n", "p", "x"]},
    fn=binomial_tail, families=("any",), model_callable=True, max_ms=1500))


# ---------------------------------------------------------------- expected_value / best_option

_OUTCOMES = {"type": "array", "minItems": 1, "maxItems": MAX_ITEMS,
             "items": {"type": "object", "required": ["p", "value"], "properties": {"p": _P, "value": _V}},
             "description": "list of {p, value}; probabilities should sum to 1"}


def _outcomes(items, normalize, label="outcomes"):
    ps = [_prob(o["p"], "%s p" % label) for o in items]
    vs = [_num(o["value"], "%s value" % label) for o in items]
    s = sum(ps, Fraction(0))
    if normalize:
        if s == 0:
            raise ToolError("%s: probabilities sum to 0" % label)
        ps = [p / s for p in ps]
    elif abs(s - 1) > Fraction(1, 10 ** 6):
        raise ToolError("%s: probabilities sum to %s, not 1 (pass normalize=true to rescale)" % (label, _dec(s)))
    return ps, vs


def _ev_var(ps, vs):
    ev = sum((p * v for p, v in zip(ps, vs)), Fraction(0))
    var = sum((p * (v - ev) ** 2 for p, v in zip(ps, vs)), Fraction(0))
    return ev, var


def expected_value(args, deadline):
    ps, vs = _outcomes(args["outcomes"], args.get("normalize", False))
    ev, var = _ev_var(ps, vs)
    return {"expected_value": _fs(ev), "expected_value_decimal": _dec(ev), "variance": _dec(var),
            "std_dev": _dec(math.sqrt(float(var))), "best_case": _dec(max(vs)), "worst_case": _dec(min(vs)),
            "explain": "EV %.4g (std %.4g), range %.4g..%.4g." % (float(ev), math.sqrt(float(var)), float(min(vs)), float(max(vs)))}


register(ToolSpec(
    name="expected_value",
    summary="Expected value and variance of a gamble given a list of {p, value} outcomes (also best and worst case).",
    params={"type": "object", "properties": {"outcomes": _OUTCOMES,
                                             "normalize": {"type": "boolean", "description": "rescale probabilities to sum to 1 instead of rejecting"}},
            "required": ["outcomes"]},
    fn=expected_value, families=("any",), model_callable=True, max_ms=500))


def best_option(args, deadline):
    rows = []
    for i, opt in enumerate(args["options"]):
        name = opt.get("name") or "option %d" % (i + 1)
        ps, vs = _outcomes(opt["outcomes"], args.get("normalize", False), label=name)
        ev, var = _ev_var(ps, vs)
        rows.append((ev, var, name, i))
    ranked = sorted(rows, key=lambda r: (-r[0], r[3]))
    best = ranked[0]
    margin = best[0] - ranked[1][0] if len(ranked) > 1 else None
    res = {"best": best[2], "best_index": best[3], "best_ev": _dec(best[0]),
           "margin": _dec(margin) if margin is not None else None,
           "tie": margin is not None and margin == 0,
           "ranking": [{"name": r[2], "ev": _fs(r[0]) if len(_fs(r[0])) < 20 else None, "ev_decimal": _dec(r[0]),
                        "std_dev": _dec(math.sqrt(float(r[1])))} for r in ranked[:20]]}
    res["explain"] = "Best by expected value: %s (EV %.4g)%s." % (
        best[2], float(best[0]), "" if margin is None else ", ahead by %.4g" % float(margin) + (" (tie)" if margin == 0 else ""))
    return res


register(ToolSpec(
    name="best_option",
    summary="Compare several options, each a list of {p, value} outcomes: returns the option with the highest expected value, the margin over the runner-up and the full ranking.",
    params={"type": "object",
            "properties": {
                "options": {"type": "array", "minItems": 1, "maxItems": 50,
                            "items": {"type": "object", "required": ["outcomes"],
                                      "properties": {"name": {"type": "string", "maxLength": 60}, "outcomes": _OUTCOMES}}},
                "normalize": {"type": "boolean", "description": "rescale each option's probabilities to sum to 1"}},
            "required": ["options"]},
    fn=best_option, families=("any",), model_callable=True, max_ms=1000))


# ---------------------------------------------------------------- bayes_update

def bayes_update(args, deadline):
    hyps = args["hypotheses"]
    names = [h.get("name") or "h%d" % (i + 1) for i, h in enumerate(hyps)]
    if len(set(names)) != len(names):
        raise ToolError("hypothesis names must be distinct")
    priors = [_prob(h["prior"], "prior of %s" % n) for h, n in zip(hyps, names)]
    liks = [_prob(h["likelihood"], "likelihood of %s" % n) for h, n in zip(hyps, names)]
    joint = [p * l for p, l in zip(priors, liks)]
    evidence = sum(joint, Fraction(0))
    if evidence == 0:
        raise ToolError("the observed evidence has probability 0 under every hypothesis (check the likelihoods)")
    post = [j / evidence for j in joint]
    top = max(range(len(names)), key=lambda i: (post[i], -i))
    return {"posterior": [{"name": n, "posterior": _fs(p), "posterior_decimal": _dec(p), "prior_decimal": _dec(pr / sum(priors, Fraction(0)))}
                          for n, p, pr in zip(names, post, priors)],
            "most_likely": names[top], "evidence_probability": _dec(evidence / sum(priors, Fraction(0))),
            "explain": "Most likely: %s at %.4g after the evidence." % (names[top], float(post[top]))}


register(ToolSpec(
    name="bayes_update",
    summary="Bayes' rule over a list of hypotheses: each has a prior and the likelihood of the evidence you just saw; returns the normalised posteriors and the most likely hypothesis.",
    params={"type": "object",
            "properties": {
                "hypotheses": {"type": "array", "minItems": 1, "maxItems": MAX_ITEMS,
                               "items": {"type": "object", "required": ["prior", "likelihood"],
                                         "properties": {"name": {"type": "string", "maxLength": 60},
                                                        "prior": _P,
                                                        "likelihood": dict(_P, description="P(evidence | this hypothesis), 0..1")}}}},
            "required": ["hypotheses"]},
    fn=bayes_update, families=("any",), model_callable=True, max_ms=500))


# ---------------------------------------------------------------- monte_carlo_estimate (harness only)

def monte_carlo_estimate(args, deadline):
    sampler = args["sampler"]
    if not callable(sampler):
        raise ToolError("sampler must be a callable sampler(rng) -> number or bool")
    max_samples = int(args.get("max_samples", 100000))
    rng = random.Random(args.get("seed", 0))
    stop = deadline - 0.03                       # leave room for call()'s own grace period
    n, mean, m2 = 0, 0.0, 0.0                    # Welford
    while n < max_samples and (n == 0 or time.monotonic() < stop):
        x = float(sampler(rng))
        n += 1
        d = x - mean
        mean += d / n
        m2 += d * (x - mean)
    var = m2 / (n - 1) if n > 1 else 0.0
    se = math.sqrt(var / n) if n > 1 else float("nan")
    return {"mean": mean, "stderr": se if n > 1 else None, "n": n, "stopped_by": "samples" if n >= max_samples else "deadline",
            "explain": "Monte Carlo mean %.4g +/- %.2g over %d samples." % (mean, se if n > 1 else 0.0, n)}


register(ToolSpec(
    name="monte_carlo_estimate",
    summary="Harness-only: run sampler(rng) -> number/bool repeatedly until the deadline or max_samples; returns mean, standard error and n.",
    params={"type": "object",
            "properties": {"sampler": {"description": "callable sampler(rng: random.Random) -> number or bool (Python only)"},
                           "max_samples": {"type": "integer", "minimum": 1, "maximum": 10 ** 7},
                           "seed": {"type": "integer"}},
            "required": ["sampler"]},
    fn=monte_carlo_estimate, families=("any",), model_callable=False, max_ms=1000))


# ---------------------------------------------------------------- abstain_threshold

def abstain_threshold(args, deadline):
    rc = _num(args["reward_correct"], "reward_correct")
    pw = _num(args["penalty_wrong"], "penalty_wrong")
    ru = _num(args["reward_unknown"], "reward_unknown")
    if pw < 0:
        raise ToolError("penalty_wrong is the size of the loss: give it as a positive number")
    if rc + pw <= 0:
        raise ToolError("reward_correct + penalty_wrong must be positive")
    t = (ru + pw) / (rc + pw)                    # answer when p*rc - (1-p)*pw >= ru
    res = {"threshold": _fs(max(Fraction(0), min(t, Fraction(1)))) if 0 <= t <= 1 else _fs(t),
           "threshold_decimal": _dec(t)}
    if t <= 0:
        res["policy"] = "always answer"
    elif t > 1:
        res["policy"] = "never answer (saying unknown is better even at 100% confidence)"
    else:
        res["policy"] = "answer only if confidence >= %s" % _dec(t)
    text = res["policy"]
    if args.get("confidence") is not None:
        c = _prob(args["confidence"], "confidence")
        ev = c * rc - (1 - c) * pw
        res["decision"] = "answer" if ev >= ru and t <= 1 else "unknown"
        res["ev_answer"] = _dec(ev)
        res["ev_unknown"] = _dec(ru)
        text += "; at confidence %.3g: %s (EV answer %.4g vs unknown %.4g)" % (float(c), res["decision"], float(ev), float(ru))
    res["explain"] = text[0].upper() + text[1:] + "."
    return res


register(ToolSpec(
    name="abstain_threshold",
    summary="Truth/QA scoring: the minimum confidence at which answering beats saying 'unknown', from the reward for a correct answer, the penalty for a wrong one and the reward for unknown; optionally decides for a given confidence.",
    params={"type": "object",
            "properties": {
                "reward_correct": dict(_V, description="points for a correct answer"),
                "penalty_wrong": dict(_V, description="points LOST for a wrong answer, as a positive number (0 if none)"),
                "reward_unknown": dict(_V, description="points for answering 'unknown' (often 0)"),
                "confidence": dict(_P, description="optional: your probability of being right, to get a decision")},
            "required": ["reward_correct", "penalty_wrong", "reward_unknown"]},
    fn=abstain_threshold, families=("truth", "any"), model_callable=True, max_ms=500))
