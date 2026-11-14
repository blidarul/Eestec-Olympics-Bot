"""Output-side filters: EVERY chat line we send goes through check_line() first (also the `ready` line).

Filters, in this order:
  (a) leak filter        no private state, no prompt/playbook/key/harness words, no canary tag,
  (b) conduct filter     no insults, hate, harassment, sexual content or threats (rules 6.10, 13.1.j),
  (c) collusion words    no deal, no "lose on purpose" (rule 13.1.f), see no_deal.py,
  (d) strategy-leak      nothing about our tactics, plans, reasons, numbers (strategy_leak.py),
  (e) tone               cold: no friendliness, no "!", no emoji (tone.py),
  (f) impersonation      never speak as the arena, a judge or the system (impersonation.py),
  (g) no-deal (only for CONCEDE_PRESSURE), (h) speech filter: no forbidden subject of the game (rule 6.8).
A line that fails any filter is replaced by a neutral cold line. The line is also cut to MAX_CHARS.
"""
import re

from . import impersonation, no_deal, strategy_leak, tone
from . import normalize as nz
from .config import CHAT_LIMIT, MAX_CHARS


# (a) words of our own machinery that must never appear in a line
_LEAK_WORDS = [
    r"system\s*prompt", r"\bmy\s+(?:prompt|instructions?|playbook|rules\s+say|guidelines|programming|training)\b",
    r"\bplaybook\b", r"\bharness\b", r"\bhaiku\b", r"\bclaude\b", r"\banthropic\b", r"\bgateway\b", r"\bllm\b",
    r"\blanguage\s+model\b", r"\bapi\b", r"\bapi\s*key\b", r"\bbearer\b", r"\bsk-[a-z0-9]", r"\blegal_actions\b",
    r"\bjson\b", r"\btemplate\b", r"\bintent\b", r"/memory", r"\bmemory\s+folder\b", r"\bsource\s+code\b",
    r"\bas\s+an\s+ai\b", r"\bi\s+am\s+an?\s+(?:ai|bot|model)\b", r"\bopenai\b", r"\buntrusted\b", r"\bprompt\s+injection\b",
]
_LEAK_RE = [re.compile(p, re.I) for p in _LEAK_WORDS]
# long random-looking strings (keys, hashes, tokens)
_SECRET_RE = re.compile(r"[A-Za-z0-9_\-]{24,}")

# (b) conduct: insults, hate, harassment, sexual content, threats. Matched on the normalized forms, so
# "1d10t" and "i d i o t" are caught as well. Whole words for short stems, substring for the long ones.
_CONDUCT_WORDS = {
    "idiot", "stupid", "moron", "dumb", "imbecile", "loser", "trash", "garbage", "worthless", "pathetic", "useless",
    "ugly", "fat", "scum", "disgusting", "braindead", "dummy", "clown", "noob", "retard", "retarded",
    "fuck", "fucking", "shit", "bitch", "asshole", "bastard", "cunt", "damn", "crap", "whore", "slut", "dickhead", "prick",
    "nigger", "nigga", "faggot", "fag", "kike", "chink", "spic", "tranny", "gypsy", "paki",
    "porn", "sex", "sexy", "nude", "naked", "rape", "nazi", "hitler",
    "kys", "die", "hate",
    "prost", "prostule", "idiotule", "dobitoc", "boule", "pula", "pizda", "muie", "cacat",
}
_CONDUCT_PHRASES = ["kill yourself", "killyourself", "go die", "hope you die", "shut up", "shutup", "i will find you",
                    "i will hurt you", "i will kill", "your mother", "your mom", "your family", "you suck", "suck it"]
_SHORT_WORDS = {w for w in _CONDUCT_WORDS if len(w) <= 4}
_LONG_WORDS = {w for w in _CONDUCT_WORDS if len(w) > 4}
# words that contain a short stem harmlessly ("die" in "diet", "sex" in "sextant") are only checked as whole words


def reason_leak(line, private_tokens=(), canary=""):
    """Why the line leaks something (a short code), or None. `canary` is the secret tag of our prompt."""
    shown = nz.display(line)
    if canary and canary.lower() in shown.lower().replace(" ", ""):
        return "canary"
    folded = nz.ascii_fold(shown, "i")
    for rx in _LEAK_RE:
        if rx.search(shown) or rx.search(folded):
            return "harness-word"
    if _SECRET_RE.search(shown):
        return "secret-like-string"
    low = " " + re.sub(r"[^a-z0-9]+", " ", shown.lower()) + " "
    for tok in private_tokens:
        t = re.sub(r"[^a-z0-9]+", " ", str(tok).lower()).strip()
        if t and f" {t} " in low:
            return "private-state"
    return None


def reason_conduct(line):
    """Why the line is not respectful (a short code), or None."""
    shown = nz.display(line)
    for one in ("i", "l"):
        folded = nz.ascii_fold(shown, one)
        words = set(re.findall(r"[a-z]+", folded))
        if words & (_SHORT_WORDS | _LONG_WORDS):
            return "abusive-word"
        plain = " " + re.sub(r"[^a-z]+", " ", folded) + " "
        for ph in _CONDUCT_PHRASES:
            if " " + ph + " " in plain:
                return "abusive-phrase"
    # spaced-out words: runs of single characters ("i d i o t", "i.d.i.o.t") are joined and checked as words
    for one in ("i", "l"):
        for run in re.findall(r"(?<!\w)\w(?:[\s.\-_*]+\w(?!\w))+", nz.ascii_fold(shown, one)):
            joined = re.sub(r"[^a-z]", "", run)
            if joined in _SHORT_WORDS or joined in _LONG_WORDS:
                return "abusive-word-spaced"
    squashed = nz.squash(nz.ascii_fold(shown, "i"))
    for w in _LONG_WORDS:
        if len(w) >= 6 and w in squashed:
            return "abusive-word-hidden"
    for ph in _CONDUCT_PHRASES:
        p = ph.replace(" ", "")
        if len(p) >= 8 and p in squashed:
            return "abusive-phrase-hidden"
    return None


# Neutral lines used when a line is blocked. Cold and short, no content words that a game could forbid.
NEUTRAL_LINES = ["Your move.", "Noted.", "Continue.", "Next.", "Proceed.", "Understood.", "Go on.", "Hm."]


def cut_line(line, limit=MAX_CHARS):
    """One line, single spaces, at most `limit` characters (cut at a word end when possible)."""
    line = " ".join(str(line).split())
    if len(line) <= limit:
        return line
    cut = line[:limit]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "."


def neutral_lines():
    """The neutral lines of the active persona (the human persona forbids "noted", "next", "your move"...)."""
    from . import battle, config
    return list(battle.HUMAN_NEUTRAL) if config.PERSONA == "human" else NEUTRAL_LINES


def safe_neutral(speech=None, private_tokens=(), seed=0):
    """A neutral line that passes every filter (the last resort is a single full stop)."""
    lines = neutral_lines()
    n = len(lines)
    for k in range(n):
        line = lines[(seed + k) % n]
        if reason_leak(line, private_tokens) is None and not (speech and speech.violates(line)):
            return line
    return "."


def check_line(line, speech=None, private_tokens=(), seed=0, canary="", one_sided=False, private_chunks=()):
    """Run the filters: leak, conduct, collusion, strategy-leak, tone, impersonation, no-deal, speech.
    Returns (final_line, problems). `problems` is a list of codes (empty = line unchanged).
    one_sided=True is for the CONCEDE_PRESSURE intent: the line must pass the no-deal filter as well."""
    problems = []
    if not isinstance(line, str) or not line.strip():
        problems.append("empty")
        line = ""
    line = cut_line(line)
    why = reason_leak(line, private_tokens, canary)
    if why:
        problems.append("leak:" + why)
    why = reason_conduct(line)
    if why:
        problems.append("conduct:" + why)
    why = no_deal.hard_collusion(line)
    if why:
        problems.append("collusion:" + why)
    why = strategy_leak.reason_strategy(line, private_chunks)
    if why:
        problems.append("strategy:" + why)
    why = tone.reason_tone(line)
    if why:
        problems.append("tone:" + why)
    why = impersonation.reason_impersonation(line)
    if why:
        problems.append(why)
    if one_sided:
        ok, why = no_deal.is_one_sided_pressure(line)
        if not ok:
            problems.append("no-deal:" + why)
    if speech is not None and speech.violates(line):
        problems.append("speech:forbidden")
    if problems:
        if one_sided:  # a failed pressure line is REPLACED by a line of the safe bank, never rewritten
            from . import concede
            cand = concede.safe_line(seed)
            if not check_line(cand, speech, private_tokens, seed, canary, False, private_chunks)[1]                     and no_deal.is_one_sided_pressure(cand)[0]:
                return cand, problems
        return safe_neutral(speech, private_tokens, seed), problems
    return line, problems
