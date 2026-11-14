"""Layer 3, phase M4: bluff and chance.

Tools (catalog): call_ev, bluff_frequency, claim_probability, card_equity (all model-callable; the Monte Carlo
core `monte_carlo_equity` is also a plain harness function). Plain data in, plain data out, stdlib only, no eval,
no stdout. Only numbers and cards the game engine reports are inputs, never the opponent's chat (rules 6.5, 6.7).
The code decides bluffs with a seeded RNG: models are reluctant to lie (the decision is still one move + chat).
"""
import itertools
import math
import random
import time

from solvers import catalog
from solvers.catalog import ToolError, ToolSpec

RANKS = "23456789TJQKA"
SUITS = "SHDC"
MAX_DICE = 200
MAX_SIMS = 20000


def _num(x, label):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or abs(x) == float("inf"):
        raise ToolError("%s must be a finite number" % label)
    return float(x)


def _prob(x, label):
    p = _num(x, label)
    if not 0.0 <= p <= 1.0:
        raise ToolError("%s must be between 0 and 1" % label)
    return p


# ------------------------------------------------------------------ call_ev

def call_ev(args, deadline):
    pot = _num(args["pot"], "pot")
    to_call = _num(args["to_call"], "to_call")
    p = _prob(args["win_prob"], "win_prob")
    tie = _prob(args.get("tie_prob", 0.0), "tie_prob")
    if pot < 0 or to_call < 0:
        raise ToolError("pot and to_call must be >= 0")
    if p + tie > 1.0 + 1e-9:
        raise ToolError("win_prob + tie_prob must be <= 1")
    lose = 1.0 - p - tie
    # pot = what is already in the middle (including the opponent's bet); calling risks to_call more.
    ev_call = p * pot - lose * to_call            # a tie returns our call: net 0
    required = to_call / (pot + to_call) if pot + to_call > 0 else 0.0
    equity = p + tie / 2.0
    decision = "call" if ev_call > 0 else ("call" if ev_call == 0 and to_call == 0 else "fold")
    return {"ev_call": round(ev_call, 4), "ev_fold": 0.0, "required_equity": round(required, 4),
            "equity": round(equity, 4), "decision": decision,
            "explain": "Call EV %.2f vs fold 0: need %.0f%% equity, have %.0f%% -> %s." % (
                ev_call, 100 * required, 100 * equity, decision)}


catalog.register(ToolSpec(
    name="call_ev",
    summary="Betting games: expected value of calling vs folding from the pot (including the opponent's bet), the amount to call and our win probability; returns required equity and call/fold.",
    params={"type": "object",
            "properties": {"pot": {"type": "number", "description": "chips already in the pot, including the bet we face"},
                           "to_call": {"type": "number", "description": "extra chips we must put in to call"},
                           "win_prob": {"type": "number", "minimum": 0, "maximum": 1},
                           "tie_prob": {"type": "number", "minimum": 0, "maximum": 1}},
            "required": ["pot", "to_call", "win_prob"]},
    fn=call_ev, families=("bluff", "any"), model_callable=True, max_ms=500))


# ------------------------------------------------------------------ bluff_frequency

def bluff_frequency(args, deadline):
    bet = _num(args["bet"], "bet")
    pot = _num(args["pot"], "pot")
    if bet <= 0 or pot < 0:
        raise ToolError("bet must be > 0 and pot >= 0")
    ratio = bet / (pot + 2.0 * bet)               # bluffs / (bluffs + value bets) that makes the caller indifferent
    defend = pot / (pot + bet)                    # how often the opponent must call to stop all bluffs
    value_share = args.get("value_share", 0.3)
    value_share = _prob(value_share, "value_share")
    # chance a hand outside the value range should bluff so that bluffs make `ratio` of the betting range
    if value_share >= 1.0:
        weak_bluff = 0.0
    else:
        weak_bluff = min(1.0, ratio * value_share / ((1.0 - ratio) * (1.0 - value_share))) if value_share > 0 else 0.0
    res = {"bluff_ratio": round(ratio, 4), "opponent_defend_freq": round(defend, 4),
           "bluff_prob_weak_hand": round(weak_bluff, 4)}
    strength = args.get("hand_strength")
    if strength is None:
        res["guidance"] = "Bet strong hands for value; with weak hands bluff about %.0f%% of the time." % (100 * weak_bluff)
        res["explain"] = res["guidance"]
        return res
    s = _prob(strength, "hand_strength")
    value_min = _prob(args.get("value_threshold", 0.65), "value_threshold")
    rng = random.Random(int(args.get("seed", 0) or 0))
    roll = rng.random()
    if s >= value_min:
        action, why = "bet", "value bet (strong hand)"
    elif roll < weak_bluff:
        action, why = "bet", "bluff (sampled %.2f < %.2f)" % (roll, weak_bluff)
    else:
        action, why = "check_or_fold", "weak hand, no bluff this time (sampled %.2f >= %.2f)" % (roll, weak_bluff)
    res.update({"action": action, "is_bluff": action == "bet" and s < value_min, "why": why})
    res["explain"] = "%s; bluff ratio %.2f, opponent must defend %.0f%%." % (why, ratio, 100 * defend)
    return res


catalog.register(ToolSpec(
    name="bluff_frequency",
    summary="Betting games: equilibrium bluff ratio bet/(pot+2*bet), how often the opponent must call, and (with hand_strength) a seeded value-bet / bluff / give-up decision made by code, not by you.",
    params={"type": "object",
            "properties": {"bet": {"type": "number", "description": "size of the bet we would make"},
                           "pot": {"type": "number", "description": "pot before our bet"},
                           "hand_strength": {"type": "number", "minimum": 0, "maximum": 1,
                                             "description": "our win probability or hand percentile; omit for guidance only"},
                           "value_threshold": {"type": "number", "minimum": 0, "maximum": 1, "description": "strength from which we bet for value (default 0.65)"},
                           "value_share": {"type": "number", "minimum": 0, "maximum": 1, "description": "share of hands that are value bets (default 0.3)"},
                           "seed": {"type": "integer", "description": "use a different seed each turn"}},
            "required": ["bet", "pot"]},
    fn=bluff_frequency, families=("bluff", "any"), model_callable=True, max_ms=500))


# ------------------------------------------------------------------ claim_probability

def _binom_tail(n, k, p):
    """P(X >= k), X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    total = 0.0
    for i in range(k, n + 1):
        total += math.comb(n, i) * p ** i * (1 - p) ** (n - i)
    return min(1.0, max(0.0, total))


def _claim_p(own, hidden, count, face, sides, wild):
    match = {face} | set(wild)
    mine = sum(1 for d in own if d in match)
    p = len(match) / float(sides)
    return _binom_tail(hidden, count - mine, p), mine


def claim_probability(args, deadline):
    sides = int(args.get("sides", 6))
    total = int(args["total_dice"])
    own = [int(d) for d in args.get("our_dice", [])]
    count, face = int(args["claim_count"]), int(args["claim_face"])
    wild = sorted({int(w) for w in args.get("wild_faces", [])})
    if not (2 <= sides <= 100) or not (1 <= total <= MAX_DICE) or len(own) > total:
        raise ToolError("need 2..100 sides, 1..%d total dice, our dice <= total" % MAX_DICE)
    if any(not 1 <= d <= sides for d in own + [face] + wild):
        raise ToolError("faces must be between 1 and sides")
    hidden = total - len(own)
    p, mine = _claim_p(own, hidden, count, face, sides, wild)
    threshold = _prob(args.get("challenge_below", 0.5), "challenge_below")
    rec = "challenge" if p < threshold else "raise"
    res = {"p_true": round(p, 4), "our_matching": mine, "hidden_dice": hidden, "recommendation": rec}
    # most likely safe raises: for each face, the largest count that is still at least `threshold` likely
    options = []
    for f in range(1, sides + 1):
        best = 0
        for c in range(1, total + 1):
            q, _ = _claim_p(own, hidden, c, f, sides, wild)
            if q >= threshold:
                best = c
            else:
                break
        if best:
            q, _ = _claim_p(own, hidden, best, f, sides, wild)
            options.append({"count": best, "face": f, "p_true": round(q, 4)})
    options.sort(key=lambda o: (-o["count"], -o["p_true"]))
    res["safe_claims"] = options[:6]
    res["explain"] = "Claim %dx%d true with p=%.2f (we hold %d, %d hidden dice) -> %s." % (count, face, p, mine, hidden, rec)
    return res


catalog.register(ToolSpec(
    name="claim_probability",
    summary="Dice-bidding games (liar's dice): probability that a claim 'count dice show face' is true given our own dice, the hidden dice and wild faces (binomial), with raise/challenge advice and the biggest still-likely claims.",
    params={"type": "object",
            "properties": {"total_dice": {"type": "integer", "minimum": 1, "maximum": MAX_DICE, "description": "all dice in play, ours included"},
                           "our_dice": {"type": "array", "maxItems": MAX_DICE, "items": {"type": "integer"}},
                           "claim_count": {"type": "integer", "minimum": 0},
                           "claim_face": {"type": "integer", "minimum": 1},
                           "sides": {"type": "integer", "minimum": 2, "maximum": 100, "description": "default 6"},
                           "wild_faces": {"type": "array", "maxItems": 10, "items": {"type": "integer"}, "description": "faces that count as any face, e.g. [1]"},
                           "challenge_below": {"type": "number", "minimum": 0, "maximum": 1, "description": "challenge when p_true is below this (default 0.5)"}},
            "required": ["total_dice", "claim_count", "claim_face"]},
    fn=claim_probability, families=("bluff", "any"), model_callable=True, max_ms=1000))


# ------------------------------------------------------------------ card_equity

def parse_card(s):
    """'As', '10h', 'T♠' -> (rank_index, suit_letter) or raises ToolError."""
    t = str(s).strip().upper().replace("♠", "S").replace("♥", "H").replace("♦", "D").replace("♣", "C")
    t = t.replace("10", "T")
    if len(t) != 2 or t[0] not in RANKS or t[1] not in SUITS:
        raise ToolError("bad card %r (use e.g. AS, TH, 9D)" % (s,))
    return RANKS.index(t[0]), t[1]


def _eval5(cards):
    ranks = sorted((r for r, _ in cards), reverse=True)
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    flush = len({s for _, s in cards}) == 1
    uniq = sorted(counts, reverse=True)
    straight_hi = None
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_hi = uniq[0]
        elif uniq == [12, 3, 2, 1, 0]:
            straight_hi = 3
    shape = [c for _, c in groups]
    key = tuple(r for r, _ in groups)
    if straight_hi is not None and flush:
        return (8, straight_hi)
    if shape == [4, 1]:
        return (7,) + key
    if shape == [3, 2]:
        return (6,) + key
    if flush:
        return (5,) + tuple(ranks)
    if straight_hi is not None:
        return (4, straight_hi)
    if shape == [3, 1, 1]:
        return (3,) + key
    if shape == [2, 2, 1]:
        return (2,) + key
    if shape == [2, 1, 1, 1]:
        return (1,) + key
    return (0,) + tuple(ranks)


def eval_poker(cards):
    """Best 5-card rank tuple from 5..7 cards (higher is better)."""
    if len(cards) < 5:
        return (-1,) + tuple(sorted((r for r, _ in cards), reverse=True))
    return max(_eval5(c) for c in itertools.combinations(cards, 5))


def _eval_high(cards):
    return tuple(sorted((r for r, _ in cards), reverse=True))


def _make_sum_eval(target, ace_value, no_bust):
    def val(r):
        ch = RANKS[r]
        if ch == "A":
            return ace_value
        if ch in "TJQK":
            return 10
        return int(ch)

    def ev(cards):
        total = sum(val(r) for r, _ in cards)
        if total > target and no_bust:
            return (0, -total)
        return (1, -abs(target - total))
    return ev


def monte_carlo_equity(ours, board, opponents, comparator="poker5", board_size=None, hand_size=None,
                       deadline=None, max_sims=MAX_SIMS, seed=0, target=21, ace_value=11, no_bust=True, deck=None):
    """Win/tie probability by simulation until `deadline`. Cards are (rank_index, suit) tuples.
    opponents: a list with one entry per opponent giving how many hidden cards each holds."""
    known = set(ours) | set(board)
    deck = [c for c in (deck if deck is not None else [(r, s) for r in range(13) for s in SUITS]) if c not in known]
    board_size = len(board) if board_size is None else board_size
    need_board = max(0, board_size - len(board))
    need = need_board + sum(opponents)
    if need > len(deck):
        raise ToolError("not enough cards left in the deck for that many hidden cards")
    if comparator == "poker5":
        ev = eval_poker
    elif comparator == "high_card":
        ev = _eval_high
    elif comparator == "sum_closest_to":
        ev = _make_sum_eval(target, ace_value, no_bust)
    else:
        raise ToolError("comparator must be high_card, sum_closest_to or poker5")
    rng = random.Random(seed)
    win = tie = n = 0
    end = deadline if deadline is not None else time.monotonic() + 1.0
    while n < max_sims and (n < 20 or time.monotonic() < end):
        draw = rng.sample(deck, need)
        full_board = list(board) + draw[:need_board]
        mine = ev(list(ours) + full_board)
        best_opp, i = None, need_board
        for k in opponents:
            theirs = ev(draw[i:i + k] + full_board)
            i += k
            if best_opp is None or theirs > best_opp:
                best_opp = theirs
        if best_opp is None or mine > best_opp:
            win += 1
        elif mine == best_opp:
            tie += 1
        n += 1
    return {"win": win / n, "tie": tie / n, "equity": (win + tie / 2.0) / n, "samples": n}


def card_equity(args, deadline):
    ours = [parse_card(c) for c in args["our_cards"]]
    board = [parse_card(c) for c in args.get("visible_cards", [])]
    if len(set(ours) | set(board)) != len(ours) + len(board):
        raise ToolError("duplicate cards in our_cards / visible_cards")
    n_opp = int(args.get("opponents", 1))
    cmp_ = args.get("comparator", "poker5")
    per_opp = int(args.get("opponent_cards", len(ours)))
    if not (1 <= n_opp <= 8) or not (0 <= per_opp <= 10):
        raise ToolError("opponents must be 1..8, opponent_cards 0..10")
    board_size = args.get("board_size")
    if board_size is None and cmp_ == "poker5" and len(ours) < 5:
        board_size = 5
    r = monte_carlo_equity(ours, board, [per_opp] * n_opp, cmp_, board_size, None,
                           min(deadline - 0.05, time.monotonic() + 1.2), int(args.get("max_samples", MAX_SIMS)),
                           int(args.get("seed", 0) or 0), args.get("target", 21), args.get("ace_value", 11),
                           bool(args.get("no_bust", True)))
    res = {k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()}
    res["explain"] = "Win %.0f%%, tie %.0f%% (%d simulations, %d opponent(s))." % (100 * r["win"], 100 * r["tie"], r["samples"], n_opp)
    return res


catalog.register(ToolSpec(
    name="card_equity",
    summary="Card games: Monte Carlo win/tie probability of our cards against hidden opponent cards from a standard 52-card deck, for poker5 (best 5 of up to 7), high_card, or sum_closest_to a target. Cards like 'AS', 'TH', '9D'.",
    params={"type": "object",
            "properties": {"our_cards": {"type": "array", "minItems": 1, "maxItems": 10, "items": {"type": "string", "maxLength": 3}},
                           "visible_cards": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 3},
                                             "description": "shared cards on the table"},
                           "board_size": {"type": "integer", "minimum": 0, "maximum": 10, "description": "final number of shared cards (poker5 default 5)"},
                           "opponents": {"type": "integer", "minimum": 1, "maximum": 8},
                           "opponent_cards": {"type": "integer", "minimum": 0, "maximum": 10, "description": "hidden cards per opponent (default: as many as ours)"},
                           "comparator": {"type": "string", "enum": ["high_card", "sum_closest_to", "poker5"]},
                           "target": {"type": "integer", "description": "for sum_closest_to (default 21)"},
                           "ace_value": {"type": "integer", "description": "for sum_closest_to (default 11)"},
                           "no_bust": {"type": "boolean", "description": "sum_closest_to: going over the target loses (default true)"},
                           "max_samples": {"type": "integer", "minimum": 20, "maximum": MAX_SIMS},
                           "seed": {"type": "integer"}},
            "required": ["our_cards"]},
    fn=card_equity, families=("bluff", "any"), model_callable=True, max_ms=1500))
