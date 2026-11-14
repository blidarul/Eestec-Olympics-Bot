"""No-impersonation filter: our chat never speaks as the arena, the organizers, the judges, the referee or the system.

Pretending to be the arena is what a hostile opponent does (see injection.FAKE_AUTHORITY). Doing it ourselves could
read as cheating or as an attack on the infrastructure, and the rulebook does not say it is allowed, so it is
forbidden by default (AMBIGUOUS: rule 15.4, listed in RULES_CHECKLIST.md). reason_impersonation(line) returns a
short code or None. English and Romanian, plain and obfuscated.
"""
import re

from . import normalize as nz

_ROLE = r"(?:arena|organi[sz]ers?|judges?|referee|umpire|system|admin\w*|moderator|mentors?|game\s*master|operator|gateway|official\w*|organizatori\w*|arbitru\w*|juriu\w*|sistem\w*)"
_PATTERNS = [
    r"(?:^|[\s\[\(<#*>|])" + _ROLE + r"\s*(?::|>|-->|=>)",
    r"\[\s*" + _ROLE + r"\s*\]",
    r"\b(?:i\s+am|i'?m|this\s+is|we\s+are|speaking\s+as|on\s+behalf\s+of|as\s+the)\s+(?:the\s+)?" + _ROLE + r"\b",
    r"\b" + _ROLE + r"\s+(?:notice|message|ruling|announcement|decision|alert|warning|update|says|said|has\s+decided|declares?|confirms?|orders?)\b",
    r"\bofficial\s+(?:notice|ruling|message|announcement|decision|update)\b",
    r"\bby\s+order\s+of\b",
    r"\byou\s+(?:are|have\s+been|were)\s+(?:disqualified|penali[sz]ed|banned|warned|flagged|reported|timed\s+out)\b",
    r"\bthe\s+rules\s+(?:say|state|require|prohibit|forbid|allow|change|have\s+changed|were\s+changed)\b",
    r"\b(?:rule|rules)\s+(?:change|update|violation)\b",
    r"\bdisqualif\w*",
    r"\bin\s+numele\s+" + _ROLE,
    r"\b(?:mesaj|anunt|decizie|hotarare)\s+(?:de\s+la|al)\s+" + _ROLE,
]
_RE = [re.compile(p, re.I) for p in _PATTERNS]
_SQUASH = ["arenanotice", "systemmessage", "messagefromthearena", "officialnotice", "organizernotice", "judgeruling", "refereeruling"]


def reason_impersonation(line):
    if not isinstance(line, str):
        return None
    shown = nz.display(line)
    for form in (shown.lower(), nz.ascii_fold(shown, "i"), nz.ascii_fold(shown, "l")):
        for rx in _RE:
            m = rx.search(form)
            if m:
                return "impersonation:" + m.group(0).strip()
    sq = nz.squash(nz.ascii_fold(shown, "i"))
    for term in _SQUASH:
        if term in sq:
            return "impersonation-hidden:" + term
    return None
