"""Layer 3, phase M7: deals (auctions, splitting, negotiation).

Tools (catalog, all model-callable): auction_bid, split_offer, reservation_estimate.
Plain data in, plain data out, stdlib only, no eval, no stdout. Inputs are numbers the engine reports (our values,
the opponent's offer amounts as the engine states them), never the opponent's chat text (rules 6.5, 6.7).
"""
import itertools
import math

from solvers import catalog
from solvers.catalog import ToolError, ToolSpec

MAX_ALLOCATIONS = 20000
MAX_OFFERS_SHOWN = 5


def _num(x, label):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or abs(x) == float("inf"):
        raise ToolError("%s must be a finite number" % label)
    return float(x)


# ------------------------------------------------------------------ auction_bid

FORMATS = ("first_price", "second_price", "all_pay")


def auction_bid(args, deadline):
    fmt = args["format"]
    if fmt not in FORMATS:
        raise ToolError("format must be one of %s" % ", ".join(FORMATS))
    v = _num(args["value"], "value")
    n = int(_num(args.get("bidders", 2), "bidders"))
    if n < 2 or n > 1000:
        raise ToolError("bidders must be between 2 and 1000")
    lo = _num(args.get("value_min", 0.0), "value_min")
    hi = _num(args.get("value_max", max(v, 1.0)), "value_max")
    if hi <= lo:
        raise ToolError("value_max must be greater than value_min")
    v = min(max(v, lo), hi)
    u = (v - lo) / (hi - lo)
    if fmt == "second_price":
        bid, why = v, "second-price: bidding your value is a dominant strategy"
    elif fmt == "first_price":
        bid = lo + (v - lo) * (n - 1) / n
        why = "first-price, %d bidders, uniform values: shade to value-min times (n-1)/n" % n
    else:
        bid = lo + (hi - lo) * (n - 1) / n * u ** n
        why = "all-pay, %d bidders, uniform values: bid (n-1)/n * v^n on the unit scale (paid win or lose)" % n
    bid = max(0.0, bid)
    # chance to win against truthful-equilibrium rivals with uniform values: all n-1 other values below ours
    win = u ** (n - 1)
    if fmt == "second_price":
        # we pay the best rival value; given a win that is uniform on [lo, v], mean lo + (v-lo)*(n-1)/n
        surplus = win * (v - (lo + (v - lo) * (n - 1) / n))
    elif fmt == "first_price":
        surplus = (v - bid) * win
    else:
        surplus = v * win - bid
    return {"bid": round(bid, 4), "format": fmt, "win_probability": round(win, 4),
            "expected_surplus": round(surplus, 4), "why": why,
            "explain": "%s: bid %.2f (value %.2f, %d bidders)." % (fmt, bid, v, n)}


catalog.register(ToolSpec(
    name="auction_bid",
    summary="Auctions: equilibrium bid for first-price (shade value by (n-1)/n), second-price (bid your value) or all-pay sealed bids, given our value, bidders and the value range.",
    params={"type": "object",
            "properties": {"format": {"type": "string", "enum": list(FORMATS)},
                           "value": {"type": "number", "description": "what the item is worth to us"},
                           "bidders": {"type": "integer", "minimum": 2, "description": "total bidders including us"},
                           "value_min": {"type": "number"}, "value_max": {"type": "number"}},
            "required": ["format", "value"]},
    fn=auction_bid, families=("deals", "any"), model_callable=True, max_ms=500))


# ------------------------------------------------------------------ split_offer

def _ultimatum(total, history):
    """history: [{"offer": amount given to the responder, "accepted": bool}] -> min acceptable offer estimate."""
    acc = [float(h["offer"]) for h in history if isinstance(h, dict) and h.get("accepted") is True
           and isinstance(h.get("offer"), (int, float))]
    rej = [float(h["offer"]) for h in history if isinstance(h, dict) and h.get("accepted") is False
           and isinstance(h.get("offer"), (int, float))]
    lo = max(rej) if rej else 0.0           # offers up to this were refused
    hi = min(acc) if acc else None          # this was accepted
    if hi is not None and hi <= lo:         # inconsistent history (the responder changed): trust the recent accepted level
        lo = 0.0
    if hi is None:
        est = min(total, max(lo * 1.15 + 0.01 * total, 0.4 * total))
        basis = "no accepted offer yet: probe above the best refused offer"
    elif not rej:
        est = hi * 0.9
        basis = "only accepted offers seen: try a little below the smallest"
    else:
        est = (lo + hi) / 2.0
        basis = "between the highest refused and the lowest accepted offer"
    est = max(0.0, min(total, est))
    return est, lo, hi, basis


def split_offer(args, deadline):
    items = args.get("items")
    history = args.get("history") if isinstance(args.get("history"), list) else []
    if not items:
        total = _num(args.get("total", 0), "total")
        if total <= 0:
            raise ToolError("give items, or total (and history) for an ultimatum")
        est, lo, hi, basis = _ultimatum(total, history)
        keep = total - est
        return {"mode": "ultimatum", "offer_to_opponent": round(est, 4), "we_keep": round(keep, 4),
                "refused_up_to": lo, "accepted_from": hi, "basis": basis,
                "explain": "Ultimatum of %g: offer %.2f, keep %.2f (%s)." % (total, est, keep, basis)}
    if not isinstance(items, list) or len(items) > 8:
        raise ToolError("items must be a list of at most 8 entries")
    parsed = []
    for it in items:
        if not isinstance(it, dict):
            raise ToolError("each item must be an object")
        qty = int(_num(it.get("quantity", 1), "quantity"))
        if qty < 1 or qty > 50:
            raise ToolError("quantity must be between 1 and 50")
        ours = _num(it["our_value"], "our_value")
        theirs = _num(it.get("opp_value", ours), "opp_value")
        parsed.append((str(it.get("name", "item%d" % len(parsed)))[:40], qty, ours, theirs))
    space = 1
    for _, q, _, _ in parsed:
        space *= q + 1
        if space > MAX_ALLOCATIONS:
            raise ToolError("too many allocations (> %d): reduce quantities" % MAX_ALLOCATIONS)
    fallback = _num(args.get("our_fallback", 0.0), "our_fallback")
    reserve = _num(args.get("opp_reservation", 0.0), "opp_reservation")
    opp_total = sum(q * t for _, q, _, t in parsed)
    our_total = sum(q * o for _, q, o, _ in parsed)
    scale = max(opp_total, 1e-9)
    rows = []
    for keep in itertools.product(*[range(q + 1) for _, q, _, _ in parsed]):
        ours = sum(k * o for k, (_, _, o, _) in zip(keep, parsed))
        theirs = sum((q - k) * t for k, (_, q, _, t) in zip(keep, parsed))
        z = 10.0 * (theirs - reserve) / scale        # acceptance estimate: logistic in the opponent's surplus
        p = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))
        rows.append((p * ours + (1 - p) * fallback, p, ours, theirs, keep))
    rows.sort(key=lambda r: (-r[0], -r[1]))
    out = []
    for score, p, ours, theirs, keep in rows[:MAX_OFFERS_SHOWN]:
        out.append({"we_keep": {parsed[i][0]: keep[i] for i in range(len(parsed))},
                    "they_get": {parsed[i][0]: parsed[i][1] - keep[i] for i in range(len(parsed))},
                    "our_utility": round(ours, 4), "their_utility": round(theirs, 4),
                    "acceptance_estimate": round(p, 3), "expected_utility": round(score, 4)})
    best = out[0]
    return {"offers": out, "best": best, "our_total": round(our_total, 4), "their_total": round(opp_total, 4),
            "explain": "Best offer: keep %s, expected utility %.2f (acceptance ~%.0f%%)." % (
                best["we_keep"], best["expected_utility"], 100 * best["acceptance_estimate"])}


catalog.register(ToolSpec(
    name="split_offer",
    summary="Negotiation: rank ways to divide items by our expected utility given our values, the estimated opponent values and an acceptance estimate; or, with only `total` and past offers, the smallest ultimatum offer likely to be accepted.",
    params={"type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "object"},
                                     "description": "[{name, quantity, our_value, opp_value}] values per unit"},
                           "total": {"type": "number", "description": "ultimatum: amount to divide"},
                           "history": {"type": "array", "items": {"type": "object"},
                                       "description": "ultimatum: [{offer: amount given to responder, accepted: bool}]"},
                           "our_fallback": {"type": "number", "description": "our utility if no deal"},
                           "opp_reservation": {"type": "number", "description": "opponent utility below which they refuse"}}},
    fn=split_offer, families=("deals", "any"), model_callable=True, max_ms=1500))


# ------------------------------------------------------------------ reservation_estimate

def reservation_estimate(args, deadline):
    offers = args["offers"]
    if not isinstance(offers, list) or not (1 <= len(offers) <= 200):
        raise ToolError("offers must be a list of 1 to 200 numbers")
    xs = [_num(x, "offer") for x in offers]
    last = xs[-1]
    if len(xs) < 2:
        return {"estimate": round(last, 4), "low": round(last, 4), "high": None, "direction": "unknown",
                "confidence": 0.1, "explain": "One offer only: the reservation value is at or beyond %.2f." % last}
    steps = [b - a for a, b in zip(xs, xs[1:])]
    direction = "up" if xs[-1] > xs[0] else ("down" if xs[-1] < xs[0] else "flat")
    if direction == "flat":
        return {"estimate": round(last, 4), "low": round(last, 4), "high": round(last, 4), "direction": "flat",
                "confidence": 0.3, "explain": "The opponent has not moved: treat %.2f as close to its limit." % last}
    sign = 1.0 if direction == "up" else -1.0
    conc = [max(0.0, s * sign) for s in steps]          # concession sizes, in the direction they move
    recent = conc[-3:]
    ratios = [b / a for a, b in zip(conc, conc[1:]) if a > 1e-12]
    r = sum(ratios[-3:]) / len(ratios[-3:]) if ratios else 1.0
    r = max(0.0, min(r, 1.5))
    step = conc[-1] if conc[-1] > 0 else (sum(recent) / len(recent))
    if r < 0.95:
        remaining = step * r / (1.0 - r)                 # geometric tail of concessions
        conf = 0.6
    else:
        remaining = step * 2.0                           # constant or growing concessions: limit unknown, guess two more steps
        conf = 0.3
    remaining = min(remaining, abs(last - xs[0]) * 3.0 + step)
    est = last + sign * remaining
    low, high = (last, est + sign * step) if sign > 0 else (est + sign * step, last)
    return {"estimate": round(est, 4), "low": round(min(low, high), 4), "high": round(max(low, high), 4),
            "direction": direction, "concession_ratio": round(r, 3), "last_step": round(step, 4),
            "confidence": conf,
            "explain": "Offers move %s, concessions shrink by %.2f per round: reservation near %.2f." % (direction, r, est)}


catalog.register(ToolSpec(
    name="reservation_estimate",
    summary="Negotiation: estimate the opponent's reservation value (their limit) from the sequence of offer amounts they made, by extrapolating how fast their concessions shrink.",
    params={"type": "object",
            "properties": {"offers": {"type": "array", "items": {"type": "number"},
                                      "description": "the opponent's successive offer amounts, oldest first"}},
            "required": ["offers"]},
    fn=reservation_estimate, families=("deals", "any"), model_callable=True, max_ms=500))
