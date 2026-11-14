"""No-deal filter for the CONCEDE_PRESSURE intent (rule 13.1.f: no collusion, no coded signals).

The pressure we may apply is ONE-SIDED: a cold statement that the opponent's position is lost and that
conceding is the rational move from the game state. It must never read as an offer, a request, an
arrangement or a signal. is_one_sided_pressure(line) returns (ok, reason):
  1. DENY list: any word or phrase of a deal (offer, trade, split, share, promise, agree, "let's", "we", points,
     standings, bracket, "throw", "on purpose", threats tied to a deal...) in English or Romanian -> rejected;
  2. no question marks (a question is a request), no "we/us/our";
  3. CUE list: the line must talk about the position, odds or conceding (lost, odds, resign, hopeless...).
A rejected line is replaced by a neutral line by the caller. The check runs on the FINAL expanded text,
on the plain, the leetspeak-decoded and the spaced-out forms, so "d e a l" and "d3al" do not pass.
"""
import re

from . import normalize as nz

# (1) things that make a line an offer, a request, an arrangement, a signal or a threat tied to a deal.
_DENY = [
    # English
    r"\bdeals?\b", r"\bbargain\w*", r"\btrad(?:e|es|ed|ing)\b", r"\boffer\w*", r"\bsplit\w*", r"\bshar(?:e|es|ed|ing)\b",
    r"\bmutual\w*", r"\bexchange\w*", r"\bpromis\w*", r"\bswear\b", r"\bguarantee\w*", r"\bagree\w*", r"\bagreement\b",
    r"\baccept\w*", r"\bin return\b", r"\bin exchange\b", r"\bfavou?rs?\b", r"\bcompromis\w*", r"\barrang\w*",
    r"\bpact\b", r"\balliance\b", r"\bcooperat\w*", r"\bcollaborat\w*", r"\btogether\b", r"\bboth\b", r"\beveryone\b",
    r"\bwe\b", r"\bus\b", r"\bour\b", r"\bours\b", r"\blet'?s\b", r"\blet me\b", r"\blet you\b", r"\bi'?ll let\b",
    r"\bi will let\b", r"\bhelp\w*", r"\bthrow\w*", r"\bdump\w*", r"\bon purpose\b", r"\bintentional\w*", r"\bdeliberate\w*",
    r"\bfake\b", r"\bpretend\b", r"\bsignal\w*", r"\bcode\b", r"\bas discussed\b", r"\bas agreed\b", r"\bremember our\b",
    r"\bpoints?\b", r"\bstanding\w*", r"\bbracket\w*", r"\bleaderboard\w*", r"\brank\w*", r"\btournament\w*",
    r"\bsemi\W?final\w*", r"\bquarter\W?final\w*", r"\bfinals?\b", r"\bround of\b", r"\bqualif\w*", r"\bscoreboard\b",
    r"\bor else\b", r"\botherwise\b", r"\bunless\b", r"\bif you\b", r"\bif i\b", r"\blast chance\b", r"\bbefore i\b",
    r"\bregret\w*", r"\bthreat\w*", r"\bi will make you\b", r"\bi'?ll make you\b", r"\bi will hurt\b", r"\bor i\b",
    r"\bbribe\w*", r"\bpay\w*", r"\breward\w*", r"\bgift\b", r"\bdonat\w*",
    r"\byou have \d+\b", r"\bseconds? to\b", r"\bminutes? to\b", r"\bturns? to\b",
    # Romanian (the text is accent-folded before matching)
    r"\binteleger\w*", r"\bafacere\w*", r"\btarg\b", r"\bofert\w*", r"\bofer\b", r"\bschimb\w*", r"\bimpart\w*",
    r"\bimpreuna\b", r"\bamandoi\b", r"\bpromit\w*", r"\bpromisiun\w*", r"\bjur\b", r"\bgaranta\w*", r"\bacceptam\b",
    r"\baccept\w*", r"\bde acord\b", r"\bhai sa\b", r"\bsa \w+m\b", r"\bnoi\b", r"\bne\b", r"\bnostru\w*", r"\bnoastra\b",
    r"\bte las\b", r"\bma lasi\b", r"\blasa-?ma\b", r"\bpuncte\w*", r"\bpunct\b", r"\bclasament\w*", r"\bturneu\w*",
    r"\bsemifinal\w*", r"\bfinala\b", r"\bajut\w*", r"\bintentionat\b", r"\bdin proprie\b", r"\bpe sfert\b",
    r"\baltfel\b", r"\bdaca (?:tu|nu|te|ma)\b", r"\bultima sansa\b", r"\bsemnal\w*", r"\bcod\b", r"\bpacient\w*",
    r"\bcooper\w*", r"\bamenint\w*", r"\bregreti\w*", r"\bmita\b", r"\brasplat\w*",
]
_DENY_RE = [re.compile(p, re.I) for p in _DENY]

# (3) the line must talk about the position, the odds or conceding.
_CUE = re.compile(
    r"\b(?:position|positions|odds|chances?|game state|lost|losing|hopeless|decided|resign\w*|concede\w*|conceding|"
    r"concession|rational|optimal|evaluation|winning path|cannot be saved|no way out|defeat\w*|"
    r"pozitia|pozitie|sanse|sansele|pierdut\w*|pierzi|renunt\w*|cedar\w*|rational\w*|optim\w*|evaluare\w*|disperat\w*|"
    r"decis\w*|inchis\w*)\b", re.I)

_SPACED = re.compile(r"(?<!\w)\w(?:[\s.\-_*]+\w(?!\w))+")


def _forms(text):
    shown = nz.display(text)
    folded_i, folded_l = nz.ascii_fold(shown, "i"), nz.ascii_fold(shown, "l")
    joined = []
    for f in (folded_i, folded_l):
        for run in _SPACED.findall(f):  # "d e a l" -> "deal"
            joined.append(re.sub(r"[^a-z0-9]", "", run))
    return shown, folded_i, folded_l, joined


def is_one_sided_pressure(line):
    """(ok, reason). ok is True only for a one-sided statement about the position or the odds."""
    if not isinstance(line, str) or not line.strip():
        return False, "empty"
    shown, folded_i, folded_l, joined = _forms(line)
    if "?" in shown:
        return False, "question"
    for form in (shown.lower(), folded_i, folded_l):
        for rx in _DENY_RE:
            m = rx.search(form)
            if m:
                return False, "deal-word:" + m.group(0)
    for word in joined:  # spaced-out words, checked as whole words
        for rx in _DENY_RE:
            if rx.fullmatch(word):
                return False, "deal-word-spaced:" + word
    if not (_CUE.search(shown.lower()) or _CUE.search(folded_i)):
        return False, "no-position-statement"
    return True, ""


# A short list that applies to EVERY line we send, whatever the intent: words of an arrangement with the opponent.
_HARD = [r"\bdeal\b", r"\bsplit\b", r"\bthrow (?:the|this|a) (?:game|match)\b", r"\bon purpose\b", r"\blet you win\b",
         r"\blet me win\b", r"\blose (?:on purpose|deliberately|intentionally)\b", r"\bas agreed\b",
         r"\bour (?:deal|arrangement|agreement)\b", r"\bshare (?:the )?points\b", r"\binteleger\w*", r"\bpierde intentionat\b",
         r"\bte las sa castigi\b"]
_HARD_RE = [re.compile(p, re.I) for p in _HARD]


def hard_collusion(line):
    """Why a line looks like an arrangement with the opponent (rule 13.1.f), or None. Applies to all lines."""
    shown = nz.display(line) if isinstance(line, str) else ""
    forms = (shown.lower(), nz.ascii_fold(shown, "i"), nz.ascii_fold(shown, "l"))
    for form in forms:
        for rx in _HARD_RE:
            m = rx.search(form)
            if m:
                return m.group(0)
    return None
