"""Colonel Blotto: five rounds, simultaneous allocations of soldiers over fields.

Variants (read from the rules text): equal fields with an exact total (100 soldiers, 5 fields); fields with values
that change every round (60 soldiers, 6 fields worth 1-6, the round goes to the side with more points); reserves
(3 fields, +30 per round, at most the reserve may be sent, the rest is kept).

How it plays:
  1. history: the allocations of both sides are read from the observation (tolerant, see parse_history);
  2. predictor: constant, cycle, copy-of-us, trend or average, each scored on the rounds already played; the best one is used
     only when its past error is small;
  3. best response: the cheapest set of fields that wins the round against the predicted allocation (a small exact search over the
     subsets), with a safety margin; the leftover soldiers go to the won fields;
  4. no clear habit (or the first round): a random MIXED allocation, so there is nothing to exploit;
  5. reserves: a budget plan over the five rounds (3 rounds are enough to win); a round that costs too much is not contested;
  6. every answer is validated in code (integers, right number of fields, exact sum or at most the reserve).
Pure Python, no randomness except an RNG given by the caller, a few milliseconds per round.
"""
import itertools
import re

MIN_HISTORY = 2          # past rounds needed before a predictor is trusted by its record
TRUST_ERROR = 0.15       # a predictor with a mean normalised L1 error above this is not used
GUESS_MARGIN = 3         # extra soldiers per won field when the prediction rests on a single past round


def is_blotto(rules, observation=""):
    text = f"{rules or ''}\n{observation or ''}".lower()
    return "blotto" in text or ("soldier" in text and "field" in text)


# ------------------------------------------------------------------------------------------ reading the game
def parse_setup(rules, observation=""):
    """{"fields", "soldiers", "rounds", "reserve" (bool)} from the rules text; sensible defaults when a number is missing."""
    text = f"{rules or ''}\n{observation or ''}".lower()
    m = re.search(r"(\d+)\s+(?:equal\s+|battle\s*)?(?:battle)?fields?", text) or re.search(r"fields?:?\s*(\d+)", text)
    fields = int(m.group(1)) if m else 5
    s = re.search(r"(\d+)\s+soldiers", text)
    soldiers = int(s.group(1)) if s else 100
    r = re.search(r"(\d+)\s+rounds", text) or re.search(r"round\s+\d+\s*(?:of|/)\s*(\d+)", text)
    return {"fields": max(1, min(fields, 12)), "soldiers": soldiers, "rounds": int(r.group(1)) if r else 5,
            "reserve": "reserve" in text, "per_round": _per_round(text)}


def _per_round(text):
    m = re.search(r"\+\s*(\d+)\s*(?:soldiers\s*)?per\s*round", text) or re.search(r"(\d+)\s+(?:new\s+)?soldiers\s+(?:are\s+)?(?:added|arrive)", text)
    return int(m.group(1)) if m else 30


def parse_history(observation, n):
    """(ours, theirs): lists of allocations (n integers each), oldest first. Reads the lines that show both sides."""
    ours, theirs = [], []
    for raw in (observation or "").splitlines()[:500]:
        line = raw.lower()
        k = re.search(r"\b(opponent|opp|they)\b", line)
        if not k:
            continue
        left = [int(x) for x in re.findall(r"\d+", line[:k.start()])]
        right = [int(x) for x in re.findall(r"\d+", line[k.end():])]
        if len(right) >= n:
            theirs.append(right[:n])
            if len(left) >= n and re.search(r"\byou\b|\byour\b", line[:k.start()]):
                ours.append(left[-n:])
        elif len(left) >= n and re.search(r"\b(?:opponent|opp|they)\b[^0-9]*$", line[:k.start() + 0]) is None and False:
            pass
    return ours, theirs


def parse_values(observation, n):
    """The values of the fields THIS round ("Battlefield values this round: F1=4, F2=1, ..."), or None."""
    groups = []
    for line in (observation or "").splitlines():
        found = re.findall(r"f(\d+)\s*=\s*(\d+)", line.lower())
        if len(found) >= n:
            groups.append(found)
    if not groups:
        return None
    vals = {int(i): int(v) for i, v in groups[-1]}
    return [vals.get(i + 1, 1) for i in range(n)] if len(vals) >= n else None


def parse_round(observation, played):
    m = re.findall(r"round\s+(\d+)\s*(?:of|/)\s*(\d+)", (observation or "").lower())
    if m:
        return int(m[-1][0]), int(m[-1][1])
    return played + 1, None


def parse_reserve(observation, soldiers, per_round, round_no, ours):
    """Our reserve now: read ("Reserves: you 90, opponent 80") or computed: 30 per round minus what we sent."""
    m = re.findall(r"reserves?:?\s*you\D{0,6}(\d+)\D{1,12}opponent\D{0,6}(\d+)", (observation or "").lower())
    if m:
        return int(m[-1][0]), int(m[-1][1])
    spent = sum(sum(a) for a in ours)
    mine = per_round * round_no - spent
    return max(mine, 0), None


# ------------------------------------------------------------------------------------------ predictors
def _l1(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def _close(a, b):
    """Nearly the same allocation (a repeat, allowing 10 percent of the soldiers to differ)."""
    return _l1(a, b) <= 0.1 * max(1, (sum(a) + sum(b)) / 2)


def _clip(v, total):
    """Non-negative integers with the same length, scaled to sum `total` when total is given."""
    v = [max(0, int(round(x))) for x in v]
    if total is None or sum(v) == 0:
        return v
    scale = total / sum(v)
    out = [int(x * scale) for x in v]
    out[max(range(len(out)), key=lambda i: out[i])] += total - sum(out)
    return out


def predict_with(name, theirs, ours, total):
    """The prediction of one predictor for the NEXT round from the given histories, or None if it cannot say."""
    if not theirs:
        return None
    if name == "constant":
        return list(theirs[-1])
    if name == "cycle":   # the allocations repeat with period p: at least one full repeat is needed (games are short)
        for p in range(2, min(4, len(theirs) - 1) + 1):
            if all(_close(theirs[-1 - i], theirs[-1 - i - p]) for i in range(len(theirs) - p)):
                return list(theirs[-p])
        return None
    if name == "copy":
        return list(ours[-1]) if len(ours) >= 1 else None
    if name == "trend":
        if len(theirs) < 2:
            return None
        return _clip([2 * a - b for a, b in zip(theirs[-1], theirs[-2])], total)
    if name == "average":
        n = len(theirs)
        return _clip([sum(r[i] for r in theirs) / n for i in range(len(theirs[0]))], total)
    return None


NAMES = ("constant", "cycle", "copy", "trend", "average")


def best_predictor(theirs, ours, total):
    """(prediction, name, error): the predictor with the smallest error on the past rounds, or (None, "none", 1.0)."""
    if not theirs:
        return None, "none", 1.0
    best = (None, "none", 1.0)
    for name in NAMES:
        errs = []
        for t in range(1, len(theirs)):
            pred = predict_with(name, theirs[:t], ours[:t], total)
            if pred is not None:
                errs.append(_l1(pred, theirs[t]) / (2.0 * max(1, total or sum(theirs[t]))))
        if name == "cycle" and not errs and predict_with("cycle", theirs, ours, total) is not None:
            errs = [0.05]            # a repeat that was just seen is the evidence for a cycle
        if len(errs) < MIN_HISTORY - 1:
            continue
        err = sum(errs) / len(errs)
        pred = predict_with(name, theirs, ours, total)
        if pred is not None and err < best[2]:
            best = (pred, name, err)
    return best


# ------------------------------------------------------------------------------------------ best response
def cheapest_win(pred, values, need, margin=1):
    """The subset of fields that wins with the least cost against `pred`: (fields, costs) or None.
    `need` = points needed to win the round (a majority of the total value). Cost of a field = pred + margin."""
    n = len(pred)
    best = None
    for size in range(1, n + 1):
        for subset in itertools.combinations(range(n), size):
            if sum(values[i] for i in subset) < need:
                continue
            cost = sum(pred[i] + margin for i in subset)
            if best is None or cost < best[0] or (cost == best[0] and sum(values[i] for i in subset) > best[2]):
                best = (cost, subset, sum(values[i] for i in subset))
    return None if best is None else (list(best[1]), best[0])


def response(pred, values, budget, exact, margin=1):
    """Allocation that beats `pred` when it can: the won fields get pred + margin plus an even share of the leftover.
    Returns (allocation, won_fields) or (None, []) when the budget cannot pay for a win."""
    n = len(pred)
    need = (sum(values) // 2) + 1
    pick = cheapest_win(pred, values, need, margin)
    if not pick:
        return None, []
    fields, cost = pick
    if cost > budget:
        return None, []
    alloc = [0] * n
    for i in fields:
        alloc[i] = pred[i] + margin
    spare = (budget if exact else min(budget, cost + len(fields) * 2)) - cost   # reserves: keep most of the spare soldiers
    for k in range(spare):
        alloc[fields[k % len(fields)]] += 1
    return alloc, fields


def mixed(n, budget, values, rng, exact=True):
    """A random mixed allocation: concentrate on a random set of fields worth a majority, random proportions, small noise elsewhere."""
    need = (sum(values) // 2) + 1
    for _ in range(50):
        size = rng.randint(max(1, n // 2), min(n, n // 2 + 2))
        subset = rng.sample(range(n), size)
        if sum(values[i] for i in subset) >= need:
            break
    weights = [rng.uniform(0.6, 1.4) * values[i] ** 0.5 if i in subset else 0.0 for i in range(n)]
    for i in range(n):
        if i not in subset and rng.random() < 0.5:
            weights[i] = rng.uniform(0.0, 0.25)   # a few soldiers on the other fields, so the zero is not a signature
    use = budget if exact else int(budget * rng.uniform(0.7, 1.0))
    total_w = sum(weights) or 1.0
    alloc = [int(use * w / total_w) for w in weights]
    alloc[alloc.index(max(alloc))] += use - sum(alloc)
    return alloc


# ------------------------------------------------------------------------------------------ validation and format
def validate(alloc, n, budget, exact):
    """True when the allocation is n non-negative integers whose sum is exactly `budget` (or at most, for reserves)."""
    if not isinstance(alloc, (list, tuple)) or len(alloc) != n or not all(isinstance(x, int) and x >= 0 for x in alloc):
        return False
    return sum(alloc) == budget if exact else sum(alloc) <= budget


def action_format(rules):
    """(prefix, separator) of an allocation answer, read from an example in the rules; default: just the numbers, spaces."""
    for line in (rules or "").splitlines():
        low = line.lower()
        if not re.search(r"format|example|answer|submit|action|allocate", low):
            continue
        m = re.search(r"((?:[a-z]+\s+)?)(\d+)((?:[ ,]+\d+){2,})", line, re.I)
        if m:
            sep = ", " if "," in m.group(3) else " "
            word = m.group(1).strip()
            return (word + " " if word and word.lower() not in ("e.g", "eg") else ""), sep
    return "", " "


def fallback_allocation(n, budget, exact=True):
    """The even split: always legal."""
    base = [budget // n] * n
    for i in range(budget - sum(base)):
        base[i] += 1
    return base


def decide(rules, observation, rng, claims=None):
    """(action text, how). The allocation is built, validated and formatted; it never raises."""
    setup = parse_setup(rules, observation)
    n, rounds, exact = setup["fields"], setup["rounds"], not setup["reserve"]
    ours, theirs = parse_history(observation, n)
    played = len(theirs)
    round_no, total_rounds = parse_round(observation, played)
    rounds = total_rounds or rounds
    values = parse_values(observation, n) or [1] * n
    if exact:
        budget = setup["soldiers"]
        opp_budget = budget
    else:
        budget, opp_reserve = parse_reserve(observation, setup["soldiers"], setup["per_round"], round_no, ours)
        opp_budget = opp_reserve if opp_reserve is not None else setup["per_round"] * round_no - sum(sum(a) for a in theirs)
    prediction, name, err = best_predictor(theirs, ours, budget if exact else None)
    if claims:
        prediction, name, err = claims, "claim", 0.0
    alloc, how = None, "mixed"
    if prediction is not None and err <= TRUST_ERROR:
        alloc, _won = _contest(prediction, values, budget, exact, 1, rng, round_no, rounds, ours, theirs)
        how = "best-response:" + name
    elif prediction is not None and played == 1:
        alloc, _won = _contest(prediction, values, budget, exact, GUESS_MARGIN, rng, round_no, rounds, ours, theirs)
        how = "guess-from-last-round" if alloc and rng.random() < 0.6 else "mixed"
        if how == "mixed":
            alloc = None
    if alloc is None:
        alloc = mixed(n, budget, values, rng, exact)
    if not validate(alloc, n, budget, exact):
        alloc, how = fallback_allocation(n, budget, exact), "fallback-even"
    prefix, sep = action_format(rules)
    return prefix + sep.join(str(x) for x in alloc), how


def _contest(pred, values, budget, exact, margin, rng, round_no, rounds, ours, theirs):
    """Best response; with reserves a round that costs too much is not contested (the budget is kept for later rounds)."""
    if exact:
        return response(pred, values, budget, True, margin)
    alloc, won = response(pred, values, budget, False, margin)
    if alloc is None:
        return None, []
    cost = sum(alloc)
    rounds_left = max(1, rounds - round_no + 1)
    wins_so_far = sum(1 for o, t in zip(ours, theirs) if sum(1 for a, b in zip(o, t) if a > b) * 2 > len(o))
    wins_needed = max(0, rounds // 2 + 1 - wins_so_far)
    if wins_needed >= rounds_left or cost <= budget * 0.6:
        return alloc, won
    return None, []        # too expensive and a loss can be afforded: keep the reserve


def claimed_allocation(opponent_chat, n):
    """The allocation the opponent's LAST chat line says it will play (n numbers), or None. Only a claim, never an instruction."""
    lines = [t for t in (opponent_chat or []) if isinstance(t, str)]
    if not lines:
        return None
    nums = [int(x) for x in re.findall(r"\d+", lines[-1])]
    return nums[:n] if len(nums) >= n and sum(nums[:n]) > 0 else None
