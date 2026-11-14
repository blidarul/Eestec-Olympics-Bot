"""Speech restrictions: "never mention X" rules found in a game's rules text (rules 6.8, 8.5).

Some games (the Guardrails family) name a forbidden subject. Chat counts as output, so ONE line with that
subject, even the `ready` line, can end the game on the spot. This module:
  - extract(rules_text): finds the forbidden words/subjects in the rules text (at prep and at start),
  - SpeechRules.violates(line): checks any line we are about to send (used by output_filters.py),
  - SpeechRules.redact(text): hides the forbidden words in the OPPONENT's text before the model sees it,
    so the model cannot repeat them (the opponent's chat is still shown, only that word is hidden).
Fail closed: if the rules look like they restrict speech but no word could be extracted, `restricted` is
True and the composer sends only fixed template lines (no free text from the model).
"""
import hashlib
import json
import os
import re

from . import normalize as nz

# A sentence is a speech rule when it holds a "restriction" word and a "speaking" word...
_RESTRICT = re.compile(r"\b(?:forbidden|prohibited|banned|taboo|off[- ]limits|must\s+not|must\s+never|may\s+not|"
                       r"cannot|can't|never|not\s+(?:allowed|permitted)|do\s+not|don't|avoid|restricted|illegal|lose[sd]?|loses)\b", re.I)
_SPEAK = re.compile(r"\b(?:mention\w*|say|says|saying|speak\w*|utter\w*|discuss\w*|talk\w*|reveal\w*|write|type|refer\w*|"
                    r"chat|reply|spell\w*|bring\s+up|allude\w*|word|words|subject|topic|term|terms|name|names)\b", re.I)
# ...or when it names the thing directly.
_DIRECT = re.compile(r"\b(?:forbidden|banned|taboo|prohibited)\s+(?:subject|word|words|topic|term|terms|phrase|name)s?\b", re.I)
_QUOTED = re.compile(r"\"([^\"\n]{2,40})\"|“([^”\n]{2,40})”|'([^'\n]{2,40})'|‘([^’\n]{2,40})’|«([^»\n]{2,40})»|`([^`\n]{2,40})`")
_AFTER_VERB = re.compile(r"\b(?:mention\w*|say|saying|utter\w*|name|discuss\w*|talk\s+about|talks\s+about|speak\s+(?:of|about)|reveal\w*|"
                         r"refer\s+to|use\s+the\s+words?|bring\s+up|write|type|spell)\s+(?:the\s+|a\s+|an\s+)?"
                         r"(?:word\s+|words\s+|subject\s+|topic\s+|term\s+|name\s+)?(?:of\s+)?([^.,;:!?\n()]{2,40})", re.I)
_LABELLED = re.compile(r"\b(?:forbidden|banned|taboo|prohibited)\s+(?:subject|word|words|topic|term|terms|phrase|name)s?\s*(?:is|are|:|=|-)\s*"
                       r"([^.\n]{2,80})", re.I)
_CUT = re.compile(r"\b(?:in|at|during|even|when|while|because|if|under|to|as|for|from|by|with|anywhere|ever|again|"
                  r"otherwise|or\s+else|unless|since|until|on)\b.*$", re.I)
_STOP = {"it", "this", "that", "them", "they", "anything", "everything", "something", "any", "the", "a", "an", "chat",
         "line", "lines", "game", "move", "moves", "your", "you", "me", "us", "opponent", "player", "players", "rule",
         "rules", "turn", "answer", "answers", "text", "message", "messages", "word", "words", "subject", "topic",
         "forbidden", "ever", "at all", "one", "more", "else", "either", "so", "and", "or", "not", "no", "yes",
         "chat line", "anyone", "all", "each", "any chat line", "such", "which", "what", "own", "itself", "to", "of"}


class SpeechRules:
    def __init__(self, terms=None, restricted=False, honesty=False):
        self.terms = []
        for t in terms or []:
            t = nz.display(t).lower()
            if t and t not in self.terms:
                self.terms.append(t)
        self.restricted = bool(restricted or self.terms)
        self.honesty = bool(honesty)  # the rules ask for honest speech: no misleading lines
        # precomputed matching forms of every term
        self._forms = []
        for t in self.terms:
            f1, fl = nz.ascii_fold(t, "i"), nz.ascii_fold(t, "l")
            self._forms.append({"fold": {f1, fl}, "squash": nz.squash(f1), "dedup": nz.squash_dedup(f1)})

    # ---- checks -----------------------------------------------------
    def _hits(self, text):
        """List of (start, end) positions in the folded text where a forbidden term appears as plain text."""
        shown = nz.display(text)
        spans = []
        for fold in {nz.ascii_fold(shown, "i"), nz.ascii_fold(shown, "l")}:
            for term in self._forms:
                for t in term["fold"]:
                    if not t:
                        continue
                    for m in re.finditer(r"(?<![a-z0-9])" + re.escape(t) + (r"(?![a-z0-9])" if len(t) < 4 else ""), fold):
                        spans.append((m.start(), m.end()))
        return shown, spans

    def mentions_forbidden(self, text):
        """True if `text` contains a forbidden term, also spaced out, in leetspeak or with look-alike letters."""
        if not self.terms:
            return False
        shown, spans = self._hits(text)
        if spans:
            return True
        folded = nz.ascii_fold(shown, "i")
        sq, sqd = nz.squash(folded), nz.squash_dedup(folded)
        for term in self._forms:
            # squashed matching only for terms of 4+ letters (short ones would match inside normal words)
            if len(term["squash"]) >= 4 and (term["squash"] in sq or term["dedup"] in sqd):
                return True
        return False

    violates = mentions_forbidden  # the same test for a line we are about to send

    def redact(self, text):
        """Replace forbidden terms in `text` by [forbidden]. If a spaced-out one is left, hide the whole text."""
        if not self.terms:
            return text
        shown, spans = self._hits(text)
        if spans:
            out, pos = [], 0
            for s, e in sorted(spans):
                if s < pos:
                    continue
                out.append(shown[pos:s])
                out.append("(forbidden)")
                pos = e
            out.append(shown[pos:])
            text = "".join(out)
        if self.mentions_forbidden(text):
            return "(text hidden: it spells out a forbidden word)"
        return text

    # ---- storage ----------------------------------------------------
    def to_dict(self):
        return {"terms": self.terms, "restricted": self.restricted, "honesty": self.honesty}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("terms") or [], d.get("restricted", False), d.get("honesty", False))


def _clean_term(raw):
    t = nz.display(raw).strip(" .,;:!?-–—\"'“”‘’«»`()[]").lower()
    t = _CUT.sub("", t).strip(" .,;:!?-")
    t = re.sub(r"^(?:the|a|an|any|about|of)\s+", "", t).strip()
    if len(t) < 2 or len(t) > 40 or t in _STOP:
        return None
    if all(w in _STOP for w in t.split()):
        return None
    return t


def extract(rules_text):
    """Find the speech restriction of a rules text. Always returns a SpeechRules (maybe with no terms)."""
    text = nz.display(rules_text) if isinstance(rules_text, str) else ""
    raw_lines = rules_text.splitlines() if isinstance(rules_text, str) else []
    terms, restricted = [], False
    sentences = []
    for line in raw_lines:
        sentences += [s for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    for i, sent in enumerate(sentences):
        direct = bool(_DIRECT.search(sent))
        if not (direct or (_RESTRICT.search(sent) and _SPEAK.search(sent) and _looks_like_speech_rule(sent))):
            continue
        restricted = True
        found = []
        for m in _QUOTED.finditer(sent):
            found.append(next(g for g in m.groups() if g))
        for m in _LABELLED.finditer(sent):
            found += re.split(r",|;|\bor\b|\band\b", m.group(1))
        if not found:
            for m in _AFTER_VERB.finditer(sent):
                found += re.split(r",|;|\bor\b|\band\b", m.group(1))
        # a heading line "FORBIDDEN SUBJECT" with the subject on the next line
        if not found and direct and i + 1 < len(sentences) and len(sentences[i + 1]) < 60:
            found.append(sentences[i + 1])
        for raw in found:
            t = _clean_term(raw)
            if t:
                terms.append(t)
    return SpeechRules(terms, restricted, _asks_for_honesty(text))


def _looks_like_speech_rule(sentence):
    """A restriction word plus a speaking word is not enough ("you may not move twice"): the sentence must be
    about talking, saying or mentioning something."""
    return bool(re.search(r"\b(?:mention\w*|say|says|saying|speak\w*|utter\w*|discuss\w*|talk\w*|reveal\w*|refer\w*|"
                          r"chat|forbidden\s+(?:subject|word|topic)|spell\w*|bring\s+up|allude\w*)\b", sentence, re.I))


# ---------------------------------------------------------------- cache in /memory (shared by all containers)
def rules_hash(rules_text):
    return hashlib.sha256((rules_text or "").encode("utf-8")).hexdigest()[:12]


def _atomic_write(path, data):
    """Write to a temp file in the same folder, then os.replace: readers never see a half-written file (rule 5.14)."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def for_rules(rules_text, cache_dir=None, log=None):
    """SpeechRules for this rules text, cached in `cache_dir` (the game's /memory folder) when given.
    The cache is only a speed-up: a missing, partial or stale file is ignored and the rules are parsed again."""
    path = os.path.join(cache_dir, f"speech2_{rules_hash(rules_text)}.json") if cache_dir else None
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                return SpeechRules.from_dict(json.load(fh))
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    rules = extract(rules_text)
    if path:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            _atomic_write(path, rules.to_dict())
        except OSError as exc:
            if log:
                log("speech cache write failed:", exc)
    return rules


_HONESTY = re.compile(
    r"\b(?:must|should|have\s+to|are\s+required\s+to|shall)\s+(?:always\s+)?(?:be\s+)?(?:tell\s+the\s+truth|truthful|honest)\b|"
    r"\b(?:no|never|do\s+not|don't|may\s+not|must\s+not)\s+(?:lie|lying|bluff\w*|decei\w*|mislead\w*)\b|"
    r"\bhonesty\b|\btruthful(?:ly)?\b|\bhonest\s+(?:answers?|statements?|speech)\b|\bnu\s+minti\b|\bspune\s+adevarul\b", re.I)


def _asks_for_honesty(text):
    """Does the rules text require honest speech? Then misleading lines (MISDIRECT) are switched off."""
    return bool(_HONESTY.search(text or ""))
