"""Tone filter: our chat is COLD. Deadpan, terse, unimpressed. No friendliness, no social content.

reason_tone(line) returns a short code if the line is friendly, social, loud or long:
  - friendly words: greetings, "good luck", "have fun", "nice", "well played", thanks, apologies, praise, small talk,
  - punctuation: no "!", no emoji or symbols, no smileys, no shouting (capital words), at most two short sentences.
Cold does NOT mean abusive: insults, slurs and threats are blocked by the conduct filter (rules 6.10, 13.1.j).
English and Romanian (accents are removed before matching).
"""
import re
import unicodedata

from . import normalize as nz
from .config import TONE_MAX_CHARS

_FRIENDLY = [
    # English
    r"good\b", r"great\b", r"nice\w*", r"well\b", r"luck\w*", r"fun\b", r"funny\b", r"enjoy\w*", r"awesome", r"amazing",
    r"wonderful", r"lovely", r"excellent", r"fantastic", r"brilliant", r"impressive", r"congrat\w*", r"thank\w*", r"thx",
    r"please", r"sorry", r"apolog\w*", r"welcome", r"hello", r"hi\b", r"hey\b", r"hiya", r"greetings", r"cheers", r"friend\w*",
    r"buddy", r"pal\b", r"dear\b", r"glad", r"happy", r"pleasure", r"appreciat\w*", r"kind(?:ly)?\b", r"respect\w*", r"fair\b",
    r"sportsman\w*", r"wish\w*", r"lol\b", r"haha\w*", r"love\w*", r"bless\w*", r"gg\b", r"wp\b", r"best\b", r"pleased",
    r"cool\b", r"neat\b", r"sweet\b", r"charming", r"delight\w*", r"honou?r\w*", r"gracious", r"bravo", r"cute\b", r"enjoyable",
    # Romanian
    r"succes\w*", r"noroc\w*", r"distractie", r"frumos\w*", r"bravo", r"felicit\w*", r"multumesc", r"mersi", r"te rog",
    r"scuze\w*", r"scuz\b", r"iarta\w*", r"salut\b", r"buna\b", r"prieten\w*", r"draga\b", r"dragut\w*", r"bine jucat",
    r"minun\w*", r"super\b", r"grozav\w*", r"excelent\w*", r"bun\b", r"bine\b", r"placere", r"drag\b", r"fain\b",
]
_FRIENDLY_RE = [re.compile(r"\b" + p, re.I) for p in _FRIENDLY]
_SMILEY = re.compile(r"(?<![A-Za-z0-9])[:;=][-^']?[)(\]\[dDpPoO3]")
_SPACED = re.compile(r"(?<!\w)\w(?:[\s.\-_*]+\w(?!\w))+")


def reason_tone(line):
    """Why the line is not cold (a short code), or None."""
    if not isinstance(line, str):
        return None
    shown = nz.display(line)
    if "!" in shown:
        return "exclamation"
    for ch in shown:
        if ord(ch) >= 0x1F000 or unicodedata.category(ch) in ("So", "Sk"):
            return "emoji-or-symbol"
    if _SMILEY.search(shown):
        return "smiley"
    if len(shown) > TONE_MAX_CHARS:
        return "too-long"
    if len(re.findall(r"[.?]\s+\S", shown)) >= 2:  # three or more sentences: not terse
        return "too-many-sentences"
    if any(len(w) >= 4 and w.isupper() for w in re.findall(r"[^\W\d_]+", shown)):
        return "shouting"
    for form in (shown.lower(), nz.ascii_fold(shown, "i"), nz.ascii_fold(shown, "l")):
        for rx in _FRIENDLY_RE:
            m = rx.search(form)
            if m:
                return "friendly:" + m.group(0)
    for form in (nz.ascii_fold(shown, "i"), nz.ascii_fold(shown, "l")):  # spaced-out friendly words
        for run in _SPACED.findall(form):
            joined = re.sub(r"[^a-z]", "", run)
            if any(rx.fullmatch(joined) for rx in _FRIENDLY_RE):
                return "friendly-spaced:" + joined
    return reason_tone_hidden(line)


# friendly phrases that are also checked with every non-letter removed ("g o o d l u c k")
_SQUASH_FRIENDLY = ["goodluck", "havefun", "wellplayed", "goodgame", "nicemove", "goodmove", "thankyou", "thanks", "bestofluck",
                    "congrat", "multumesc", "felicitari", "bunaziua", "noroc", "multsucces", "greatgame", "nicetry"]


def reason_tone_hidden(line):
    """Friendly words hidden by spaces or punctuation; used by reason_tone through check_line."""
    sq = nz.squash(nz.ascii_fold(nz.display(line), "i")) if isinstance(line, str) else ""
    for term in _SQUASH_FRIENDLY:
        if term in sq:
            return "friendly-hidden:" + term
    return None
