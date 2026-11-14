"""CONCEDE_PRESSURE: the phrase bank, the seeded choice and the frequency limiter.

One-sided pressure only (rule 6.3 "pressure"; collusion is an offence, rule 13.1.f): every line is a cold
statement about the position, the odds or the rational choice. No offer, no request for agreement, no "let us
win", no points/standings, no threat, no insult, no arena voice. The bank is audited by the tests with the
full filter chain (leak, conduct, collusion, strategy-leak, tone, impersonation, no-deal).

Four sub-styles: DIRECT ("You should resign."), POSITIONAL ("Your position is lost."), FUTILITY ("Continuing
is pointless."), RATIONAL ("Resigning is the rational move."). English and Romanian sets (config.CONCEDE_LANGUAGE).

Claims about the position are bluffing, which the chat rules allow (6.3, 6.7), but NOT where a game restricts
speech or asks for honesty: pipeline.active_intents() switches the intent off there.

ConcedeLimiter (all numbers in config.py): at most one line per CONCEDE_MIN_GAP of our turns (so never twice in
a row), CONCEDE_MAX_PER_GAME per game, CONCEDE_MAX_PER_MATCH per match, never the same line twice in a game.
The choice of sub-style and line is seeded by (match, game, turn): it never looks at our hand or our move.
"""
import random

from . import config

BANK_EN = {
    "DIRECT": ["You should resign.", "You should fold.", "Concede.", "Resign.", "You should concede.", "Fold.",
               "Time to resign.", "Resigning is in order.", "You ought to concede.", "Conceding is due."],
    "POSITIONAL": ["Your position is lost.", "You have no winning line.", "Every continuation loses.",
                   "The position is decided.", "Your position cannot be saved.", "The odds are against you.",
                   "You are lost here.", "There is no winning path for you.", "Your chances are negligible.",
                   "The outcome is decided.", "Every line from here loses for you."],
    "FUTILITY": ["Continuing is pointless.", "Further play changes nothing.", "You cannot recover from this.",
                 "Playing on is futile.", "Nothing you do changes the outcome.", "The rest is a formality.",
                 "Recovery is not possible.", "More moves, same outcome.", "There is nothing left to play for.",
                 "This cannot be turned around."],
    "RATIONAL": ["Resigning is the rational move.", "Folding is the rational option now.",
                 "Conceding is the correct decision.", "Conceding is optimal.", "The rational choice is to resign.",
                 "Resignation is the correct move.", "A rational player resigns here.", "Folding is correct here.",
                 "Resigning is the logical conclusion.", "The sound decision is to concede."],
}
BANK_RO = {
    "DIRECT": ["Ar trebui să renunți.", "Renunță.", "Cedează.", "Ar trebui să cedezi.", "E momentul să renunți."],
    "POSITIONAL": ["Poziția ta este pierdută.", "Nu ai nicio linie câștigătoare.", "Orice continuare pierde.",
                   "Șansele tale sunt neglijabile.", "Partida este decisă."],
    "FUTILITY": ["Continuarea este inutilă.", "Nimic nu mai modifică rezultatul.", "Nu mai poți reveni.",
                 "Restul este o formalitate."],
    "RATIONAL": ["Renunțarea este mutarea rațională.", "Cedarea este decizia corectă.",
                 "Alegerea rațională este să renunți.", "Un jucător rațional renunță aici."],
}
STYLES = ("DIRECT", "POSITIONAL", "FUTILITY", "RATIONAL")


def bank(language=None):
    """The active bank: {style: [lines]} for "en", "ro" or "mix"."""
    language = language or config.CONCEDE_LANGUAGE
    if language == "ro":
        return BANK_RO
    if language == "mix":
        return {s: BANK_EN[s] + BANK_RO[s] for s in STYLES}
    return BANK_EN


def all_lines():
    """Every concession line of both languages: (style, line). For the audit tests and the sample."""
    for b in (BANK_EN, BANK_RO):
        for style in STYLES:
            for line in b[style]:
                yield style, line


def pick(seed, used=(), language=None):
    """(line, style): a seeded sub-style, then a seeded line of it that was not used in this game."""
    b = bank(language)
    rng = random.Random(f"{seed}|concede")
    styles = list(STYLES)
    rng.shuffle(styles)
    for style in styles:
        lines = [l for l in b[style] if l not in used]
        if lines:
            return rng.choice(lines), style
    return None, None  # every line was used in this game


def safe_line(seed=0, avoid=()):
    """A line of the DIRECT / POSITIONAL bank: the replacement for a pressure line that failed the no-deal
    filter. Never a rewritten version of the offending text."""
    lines = [l for l in BANK_EN["DIRECT"] + BANK_EN["POSITIONAL"] if l not in avoid]
    lines = lines or BANK_EN["POSITIONAL"]
    return lines[random.Random(f"{seed}|safe").randrange(len(lines))]


class ConcedeLimiter:
    """Counts our concession lines. One object per ChatDefense (per container and game)."""

    def __init__(self):
        self.match = 0
        self.reset_game()

    def reset_match(self):
        self.match = 0
        self.reset_game()

    def reset_game(self):
        self.game = 0
        self.used = set()       # lines already said in this game
        self.our_turn = 0       # how many answers we gave in this game
        self.last_use = None    # value of our_turn at the last concession line

    def tick(self):
        """Call once for every answer we give."""
        self.our_turn += 1

    def allowed(self):
        if not config.ENABLE_CONCEDE_PRESSURE:
            return False
        if self.game >= config.CONCEDE_MAX_PER_GAME or self.match >= config.CONCEDE_MAX_PER_MATCH:
            return False
        if self.last_use is not None and self.our_turn - self.last_use < config.CONCEDE_MIN_GAP:
            return False
        return True

    def record(self, line):
        self.game += 1
        self.match += 1
        self.used.add(line)
        self.last_use = self.our_turn
