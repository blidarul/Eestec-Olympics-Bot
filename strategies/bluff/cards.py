"""Hidden-information card games: hand strength, action categories and a mixed betting policy (no I/O, seeded RNG).

Strength is 0..1 inside the deck of the game: Kuhn poker (J, Q, K) gives 0, 0.5, 1; a normal deck gives 2..A.
The policy mixes value bets, calibrated bluffs and calls (the game-theoretic idea of Kuhn poker: bluff about a
quarter of the time with the worst hands, call a third of the time with the middle ones), so the opponent cannot
exploit a fixed pattern. All the randomness comes from a seeded RNG given by the caller.
"""
import re

RANKS = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10, "t": 10, "j": 11, "q": 12, "k": 13, "a": 14,
         "jack": 11, "queen": 12, "king": 13, "ace": 14}
_CARD = re.compile(r"(?<![A-Za-z0-9])(10|[2-9]|[JQKAjqka]|jack|queen|king|ace)(?=[SHDCshdc♠♥♦♣]?(?![A-Za-z0-9]))", re.I)
_PRIVATE_LINE = re.compile(r"\b(?:your|you)\s+(?:hand|cards?|card|hold|holding|have|are\s+holding|dice)\b", re.I)

BLUFF_FREQUENCY = 0.25      # weak hands bet or raise as a bluff this often (inside the 15-33 percent band)
SLOWPLAY = 0.10             # strong hands check / just call this often so the bets are not a tell
MEDIUM_CALL = 1.0 / 3.0     # middle hands call a bet this often (Kuhn poker equilibrium)
STRONG, WEAK = 0.75, 0.35   # strength limits


def deck_range(rules):
    """(lowest, highest) rank of the deck: Kuhn poker (J, Q, K) or a normal 2..A deck."""
    low = (rules or "").lower()
    if "kuhn" in low:
        return 11, 13
    found = {RANKS[m.lower()] for m in re.findall(r"\b(?:jack|queen|king|ace)\b|(?<![A-Za-z0-9])[JQKA](?![A-Za-z0-9])", rules or "", re.I)}
    if found and max(found) - min(found) <= 2 and 2 not in found and "deck" not in low:
        return min(found), max(found)
    return 2, 14


def parse_hand(observation):
    """Rank numbers of OUR private cards, from the observation lines that show them ("Your hand: KS, 10H")."""
    ranks = []
    if not isinstance(observation, str):
        return ranks
    for line in observation.splitlines()[:60]:
        if _PRIVATE_LINE.search(line):
            part = line.split(":", 1)[1] if ":" in line else line
            for m in _CARD.finditer(part):
                ranks.append(RANKS[m.group(1).lower()])
    return ranks[:10]


def strength(ranks, rules=""):
    """0..1 (0.5 when we cannot read the hand). A pair or better in a multi-card hand adds a bonus."""
    if not ranks:
        return 0.5
    lo, hi = deck_range(rules)
    span = max(1, hi - lo)
    base = sum(min(max(r, lo), hi) - lo for r in ranks) / (len(ranks) * span)
    if len(ranks) > 1 and len(set(ranks)) < len(ranks):
        base = min(1.0, base + 0.25)
    return max(0.0, min(1.0, base))


def categorize(action):
    """"fold", "call", "bet" (bet / raise / all-in), "check" (check / pass) or "other"."""
    words = set(re.findall(r"[a-z]+", str(action).lower()))
    if words & {"fold", "resign", "muck"}:
        return "fold"
    if words & {"raise", "bet", "wager", "allin", "shove", "open"} or "all-in" in str(action).lower():
        return "bet"
    if words & {"call", "match", "see"}:
        return "call"
    if words & {"check", "pass", "stay"}:
        return "check"
    return "other"


def by_category(legal):
    """{category: first legal action of it}."""
    out = {}
    for a in legal or []:
        out.setdefault(categorize(a), a)
    return out


def choose(s, cats, rng, call_bias=0.0):
    """The category to play: one of "bet", "call", "check", "fold". `cats` = the categories that are legal.
    `call_bias` (0..0.15) is the only way public chat signals reach this function: it can only make a middle hand call
    more often, never fold or bet."""
    facing = "fold" in cats and ("call" in cats)
    if facing:
        if s >= STRONG:
            return "bet" if ("bet" in cats and rng.random() < 0.5) else "call"
        if s >= WEAK:
            return "call" if rng.random() < MEDIUM_CALL + call_bias else "fold"
        if "bet" in cats and rng.random() < BLUFF_FREQUENCY:
            return "bet"                     # a calibrated bluff-raise
        return "fold"
    if s >= STRONG:
        return "bet" if ("bet" in cats and rng.random() >= SLOWPLAY) else ("check" if "check" in cats else "call")
    if s >= WEAK:
        return "bet" if ("bet" in cats and rng.random() < 0.15) else ("check" if "check" in cats else "call")
    if "bet" in cats and rng.random() < BLUFF_FREQUENCY:
        return "bet"                         # a calibrated bluff
    return "check" if "check" in cats else ("fold" if "fold" in cats else "call")
