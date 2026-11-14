"""Strategy-leak firewall: our chat must never reveal, hint at or explain how we play.

reason_strategy(line, private_chunks) returns a short code if the FINAL line of chat would give away:
  - a strategy, algorithm or technique ("binary search", "minimax", "expected value", "I am bluffing"),
  - a plan or a move announcement ("I will play", "my plan", "I chose"),
  - a reason for a move ("because", "so I", "therefore"),
  - our model, harness, prompt, playbook, memory or tools,
  - a number (any digit): our private state or a number we computed,
  - any piece of our private observation fields (our hand, our secret number...).
It runs on the plain text, on a leetspeak/look-alike decoded copy, on spaced-out letters ("m i n i m a x") and on
the letters-only squash, so simple obfuscation does not pass. English and Romanian.
The templates are audited with this same function (tests/mbappe/test_tone_leak.py), so the code that writes our
chat can never fail it; the filter matters for text that comes from elsewhere (other strategies, the model).
"""
import re

from . import normalize as nz

# Strategy and tool words (regex stems, matched on the accent-free lower-case text, at a word start).
_TERMS = [
    # English
    r"algorithm\w*", r"binary", r"bisect\w*", r"mid-?points?", r"mini-?max", r"alpha-?beta", r"prun(?:e|ed|es|ing)\b", r"mcts",
    r"monte", r"carlo", r"simulat\w*", r"heuristic\w*", r"solver\w*", r"search\w*", r"trees?\b", r"depth\b", r"plys?\b",
    r"evaluat\w*", r"probabilit\w*", r"likelihood", r"pot\s+odds", r"expect(?:ed)?\s+(?:value|utility|payoff|return)", r"expectation\w*", r"ev\b", r"bayes\w*", r"entropy",
    r"deduc\w*", r"infer\w*", r"narrow\w*", r"candidates?\b", r"eliminat\w*", r"thresholds?\b", r"equilibri\w*", r"nash\b",
    r"strateg\w*", r"tactic\w*", r"plan(?:s|ned|ning)?\b", r"approach\w*", r"methods?\b", r"techniques?\b", r"calculat\w*",
    r"comput\w*", r"estimat\w*", r"optimi[sz]\w*", r"analy[sz]\w*", r"statistic\w*", r"confiden\w*", r"bluff\w*",
    r"all-?in\b", r"pairs?\b", r"flush\w*", r"straights?\b", r"full house", r"models?\b", r"llm\b", r"gpt\b", r"claude",
    r"haiku", r"anthropic", r"prompt\w*", r"playbook\w*", r"harness\w*", r"memory\b", r"tools?\b", r"bots?\b", r"script\w*",
    r"program\w*", r"train(?:ed|ing)\b", r"neural\w*", r"network\w*", r"code\b", r"data\b", r"engine\b", r"pattern\w*",
    r"weights?\b", r"policy\b", r"reasoning\b", r"logic\b", r"rule-?based", r"lookup", r"database",
    # Romanian (accents are removed before matching)
    r"algoritm\w*", r"binar\w*", r"euristic\w*", r"cautare\w*", r"arbore\w*", r"adancime\w*", r"evaluare\w*",
    r"probabilitat\w*", r"probabil\b", r"strategi\w*", r"tactic\w*", r"planul\w*", r"plan\b", r"abordare\w*", r"metoda\b",
    r"calcul\w*", r"estim\w*", r"optimiz\w*", r"analiz\w*", r"incredere\b", r"bluf\w*", r"blef\w*", r"simulare\w*",
    r"deduc\w*", r"elimin\w*", r"restrang\w*", r"model\w*", r"prompt\w*", r"memorie\b", r"unelt\w*", r"program\w*",
    r"pereche\b", r"culoare\b", r"mana mea\b", r"cartile mele\b", r"numarul meu\b", r"mutarea mea\b", r"ghicesc\b",
    r"ghicit\w*", r"miez\b", r"jumatate\b",
]
_TERM_RE = [re.compile(r"\b" + t, re.I) for t in _TERMS]

# Long terms also checked with every non-letter removed ("m i n i m a x", "bi-nary").
_SQUASH_TERMS = ["algorithm", "algoritm", "binarysearch", "minimax", "alphabeta", "heuristic", "euristic", "probability",
                 "probabilitate", "strategy", "strategie", "evaluation", "evaluare", "playbook", "harness", "bluffing",
                 "midpoint", "simulation", "expectedvalue", "montecarlo", "systemprompt", "calculat", "narrowed"]

# Move announcements, self-reports and reasons.
_PATTERNS = [
    # "I will play / I'll guess / I am going to raise" ...
    r"\bi(?:'ll|ll|\s+will|\s+shall|\s+am\s+going\s+to|'m\s+going\s+to|\s+gonna|\s+would|\s+might|\s+may|\s+can|\s+could)\s+"
    r"(?:now\s+|just\s+|probably\s+|simply\s+|then\s+|not\s+|never\s+|only\s+)?(?:accept|pay|offer|give|sell|buy|concede|agree|bid|"
    r"demand|insist|refuse|keep|stick|counter|settle|play|guess|pick|choose|take|go|bet|raise|call|fold|roll|hold|move|try|ask|"
    r"say|bluff|attack|defend|check|pass|reveal|show|use|do|make|aim|target|start|open|win|lose|stay|stand|wait|press|push)\b",
    r"\bmy\s+(?:move|plan|strategy|guess|bid|bet|hand|cards?|number|choice|next|approach|play|turn|position|score|total|range|"
    r"estimate|reading|read|call|offer|price|value|reservation|secret|dice|roll|fleet|word|budget|valuation|limit|minimum|maximum|ceiling|floor|bottom\s+line)\b",
    r"\bi\s+(?:chose|choose|picked|pick|played|guessed|decided|selected|hold|have|had|am\s+holding|know|think|believe|calculated|"
    r"computed|estimated|figured|deduced|assume|suspect|expect|see|saw|noticed|narrowed|eliminated|reasoned|analy[sz]ed|bluff\w*)\b",
    r"\bi'?m\s+(?:holding|bluffing|guessing|playing|going|using|doing|running|thinking|counting|tracking|reading)\b",
    r"\bi\s+am\s+(?:holding|bluffing|guessing|playing|going|using|doing|running|thinking|counting|tracking|reading)\b",
    r"\b(?:my|the)\s+(?:next\s+)?(?:move|guess)\s+(?:is|will\s+be)\b",
    # reasons
    r"\bbecause\b", r"\bso\s+i\b", r"\btherefore\b", r"\bthus\b", r"\bsince\b", r"\bhence\b", r"\bin\s+order\s+to\b",
    r"\bthat\s+is\s+why\b", r"\bthat'?s\s+why\b", r"\bwhich\s+means\b", r"\bmeans\s+i\b", r"\bas\s+a\s+result\b", r"\bdue\s+to\b",
    r"\bthe\s+reason\b", r"\bso\s+that\b", r"\bgiven\s+that\b", r"\bit\s+follows\b",
    # Romanian
    r"\bpentru\s+ca\b", r"\bdeci\b", r"\bde\s+aceea\b", r"\bdeoarece\b", r"\bplanul\s+meu\b", r"\beu\s+(?:voi|o\s+sa|aleg|joc|ghicesc|am)\b",
    r"\bam\s+(?:ales|decis|calculat|ghicit|dedus|estimat|eliminat|restrans|vazut|observat)\b", r"\bvoi\s+(?:juca|alege|ghici|merge|paria)\b",
    r"\bo\s+sa\s+(?:joc|aleg|ghicesc|merg|pariez)\b", r"\bmutarea\s+mea\b", r"\bpentru\s+a\b", r"\bdin\s+cauza\b",
    r"\bpretul\s+meu\b", r"\blimita\s+mea\b", r"\bnu\s+(?:merg|cobor|accept|ofer)\b", r"\bpot\s+(?:plati|accepta|oferi)\b",
]
_PATTERN_RE = [re.compile(p, re.I) for p in _PATTERNS]

_SPACED = re.compile(r"(?<!\w)\w(?:[\s.\-_*]+\w(?!\w))+")


def _forms(line):
    shown = nz.display(line)
    low = shown.lower()
    fi, fl = nz.ascii_fold(shown, "i"), nz.ascii_fold(shown, "l")
    return shown, low, fi, fl


def reason_strategy(line, private_chunks=()):
    """Why the line would reveal our approach (a short code), or None if it is clean."""
    if not isinstance(line, str):
        return None
    shown, low, fi, fl = _forms(line)
    if re.search(r"\d", shown):
        return "digit"  # a number may be our private state or a number we computed: never in our chat
    for form in (low, fi, fl):
        for rx in _TERM_RE:
            m = rx.search(form)
            if m:
                return "term:" + m.group(0)
        for rx in _PATTERN_RE:
            m = rx.search(form)
            if m:
                return "pattern:" + m.group(0)
    # spaced-out words: join runs of single characters ("m i n i m a x") and check them as words
    for form in (fi, fl):
        for run in _SPACED.findall(form):
            joined = re.sub(r"[^a-z]", "", run)
            for rx in _TERM_RE:
                if rx.fullmatch(joined):
                    return "term-spaced:" + joined
    squashed = nz.squash(fi)
    dedup = nz.squash_dedup(fi)
    for term in _SQUASH_TERMS:
        if term in squashed or re.sub(r"(.)\1+", r"\1", term) in dedup:
            return "term-hidden:" + term
    # a piece of our private observation fields (our hand, our secret...)
    words = " " + re.sub(r"[^a-z0-9]+", " ", fi) + " "
    for chunk in private_chunks:
        c = re.sub(r"[^a-z0-9]+", " ", str(chunk).lower()).strip()
        if len(c) >= 3 and f" {c} " in words:
            return "private-substring"
    return None
