"""Detector for hostile opponent chat. Input: one chat line. Output: a ChatReport.

The opponent chat is NEVER thrown away (rules 6.5, 6.6). analyze() only:
  1. finds suspicious patterns (flags) and gives a severity 0..3,
  2. makes a `sanitized` copy where instruction-like spans are replaced by "[removed:FLAG]" and format
     markers (JSON, tags, code fences) are defused. The rest of the text is kept as it was.
The report goes to the model (inside untrusted tags, see wrap.py) and to the decision code (signals.py).

How detection works: patterns run on `ascii_fold(display(text))`, a same-length plain form, so tricks like
look-alike letters or leetspeak do not hide a phrase. A second check runs on the "squashed" text (letters
only), which catches spaced-out phrases ("i g n o r e  y o u r  r u l e s").
"""
import re
from dataclasses import dataclass, field

from . import normalize as nz

# flag -> weight (1 = low, 2 = medium). Severity = the biggest weight, +1 for combined attacks.
FLAG_WEIGHT = {
    "PRESSURE": 1, "SUGGEST_MOVE": 1, "REVEAL_PRIVATE": 1, "FLOOD": 1, "UNICODE_TRICKS": 1,
    "PROBE_STRATEGY": 1, "INSTRUCTION": 2, "FAKE_AUTHORITY": 2, "REVEAL_PROMPT": 2, "ROLEPLAY": 2, "FORMAT_SMUGGLE": 2,
    "FORBIDDEN_BAIT": 2,
}
SEVERITY_NAME = {0: "NONE", 1: "LOW", 2: "MEDIUM", 3: "HIGH"}
MAX_SHOWN = 300  # characters of one opponent line shown to the model (flooding protection)

W = r"(?:\w+\s+){0,3}"  # up to three filler words between the key words of a phrase

# Patterns on the ascii-folded text. English plus Romanian, Spanish, French, German, Italian, Portuguese.
_RAW = {
    "INSTRUCTION": [
        r"\b(?:ignor\w*|disregard\w*|forget|override|bypass|drop|skip|cancel|abandon)\s+" + W +
        r"(?:rules?|instructions?|prompts?|guidelines?|constraints?|directions?|programming|training|orders?)\b",
        r"\b(?:new|updated|changed|different|real|true|actual)\s+(?:rules?|instructions?|orders?|task|objective|goal)\b",
        r"\b(?:from now on|starting now|henceforth|for the rest of (?:the|this) (?:game|match))\b.{0,40}\b(?:you|your|must|will|only|always|never)\b",
        r"\byou\s+(?:must|have to|need to|will|shall|are required to|are ordered to)\s+(?:now\s+)?"
        r"(?:play|choose|pick|move|answer|say|respond|reply|output|print|send|type|write|fold|resign|concede|forfeit|give up|reveal|tell|obey|follow|repeat)\b",
        r"\b(?:do as i say|obey me|obey this|follow my (?:instructions?|orders?|commands?|rules?)|i command you|that is an order|this is an order)\b",
        r"\b(?:respond|reply|answer|output|print|say|write|type|send)\s+(?:only|exactly|just|with)\b",
        r"\b(?:end|stop|finish|terminate)\s+(?:the|this)\s+(?:game|match|round)\b",
        # other languages
        r"\b(?:ignora|ignori|uita|uitati|nu mai respecta|nu respecta)\s+" + W + r"(?:regulile|instructiunile|indicatiile|ordinele|regulament\w*)\b",
        r"\b(?:ignora|ignore|olvida|omite)\s+" + W + r"(?:instrucciones|reglas|ordenes|indicaciones|instrucoes|regras|istruzioni|regole)\b",
        r"\b(?:ignore|ignorez|oublie|oubliez)\s+" + W + r"(?:instructions|regles|consignes|ordres)\b",
        r"\b(?:ignorier\w*|vergiss|vergesst|missachte\w*)\s+" + W + r"(?:anweisungen|regeln|instruktionen|befehle|vorgaben)\b",
    ],
    "FAKE_AUTHORITY": [
        r"(?:^|[\s\[\(<#*>|])(?:system|admin|administrator|developer|dev|assistant|moderator|arena|referee|judge|organizer|organiser|host|mentor|operator|gateway|root|sudo)\s*(?::|>|-->|=>)",
        r"\[\s*(?:system|admin|arena|referee|judge|organi[sz]ers?|official|moderator|developer|notice|alert|mentor)\s*\]",
        r"\b(?:message|notice|announcement|update|alert|warning|note|ruling|decision|memo|order|directive)\s+(?:from|by)\s+(?:the\s+)?(?:arena|organi[sz]ers?|judges?|referees?|admins?|system|dvloper|gateway|platform|mentors?|moderators?|developers?)\b",
        r"\b(?:the\s+)?(?:arena|organi[sz]ers?|judges?|referees?|admins?|system|moderators?|mentors?)\s+(?:has\s+|have\s+)?(?:just\s+)?(?:announced|decided|ruled|changed|updated|declared|says|said|requires?|requested|ordered|instructs?|informs?|confirmed)\b",
        r"\b(?:rules?|game|match|scoring|clock|timer)\s+(?:has|have|had)?\s*(?:been\s+|was\s+|were\s+)?(?:changed|updated|modified|suspended|void|voided|cancel+ed|reset|paused|extended)\b",
        r"\bofficial\s+(?:notice|ruling|announcement|update|message|decision)\b",
        r"\b(?:you|your\s+(?:bot|team|harness))\s+(?:has|have|had)\s+(?:been\s+)?(?:disqualified|penali[sz]ed|banned|timed out|forfeited|flagged|reported)\b",
        r"\b(?:game|match)\s+(?:is\s+)?(?:void|cancel+ed|a draw|forfeited)\b",
        r"\b(?:this|the)\s+(?:is|was)\s+(?:an?\s+)?(?:automated|official|system)\s+(?:message|test|check)\b",
    ],
    "REVEAL_PROMPT": [
        r"\b(?:reveal|show|print|repeat|output|display|share|leak|dump|recite|paste|echo|give|send|tell|expose|disclose)\s+(?:me\s+)?" + W +
        r"(?:system\s+prompt|prompt|instructions?|playbook|configuration|config|api\s*key|keys?|tokens?|passwords?|memory\s*(?:file|dump)|harness|source\s*code|guidelines|training)\b",
        r"\bwhat\s+(?:are|were|is)\s+(?:your|the|ur)\s+(?:\w+\s+)?(?:instructions?|rules|prompt|guidelines|playbook|system\s+prompt|configuration|model|engine|strategy)\b",
        r"\b(?:system|initial|original|hidden|secret)\s+prompt\b",
        r"\brepeat\s+(?:everything|all|the (?:text|words|message)|your (?:text|words))\s+(?:above|before|so far)\b",
        r"\b(?:api|secret|access)\s*[-_ ]?(?:keys?|tokens?)\b|\bsk-[a-z0-9]{8,}|\bbearer\s+[a-z0-9]{8,}",
        r"\bwhich\s+(?:ai|model|llm|engine)\s+(?:are\s+you|do\s+you\s+use|powers?)\b",
    ],
    "REVEAL_PRIVATE": [
        r"\b(?:what(?:'s|s| is| are)|tell me|show me|reveal|share|give me|let me see)\s+(?:me\s+)?(?:your|ur)\s+(?:\w+\s+)?(?:hand|cards?|secret|number|dice|roll|private|hidden|fleet|word|value|code|bid|offer|reservation|limit|minimum|maximum|price|budget|valuation|ceiling|floor|bottom\s+line)\b",
        r"\b(?:show|reveal)\s+(?:me\s+)?(?:your\s+)?(?:hand|cards?)\b",
        r"\bwhat(?:'s|s| is)\s+yours\b", r"\bcare\s+e\s+(?:limita|pretul|numarul)\s+tau\b",
    ],
    "ROLEPLAY": [
        r"\byou\s+(?:are|re)\s+(?:now|no longer)\b",
        r"\b(?:act|behave|respond|answer|play)\s+(?:as|like)\s+(?:an?\s+|the\s+|if\s+you\s+(?:were|are)\s+)",
        r"\bpretend\s+(?:to\s+be|you\s+(?:are|re)|that|as)\b",
        r"\brole\s*[- ]?play\w*\b|\bimagine\s+(?:you\s+(?:are|re)|that\s+you)\b|\bassume\s+the\s+role\b",
        r"\byour\s+(?:new|real|true|actual)\s+(?:role|persona|name|identity|purpose|job|task)\b",
        r"\byou(?:'re|re| are)\s+(?:actually\s+)?(?:an?\s+)?(?:helpful\s+)?(?:ai|assistant|chatbot|language model|llm|gpt|dan|bot)\b",
        r"\b(?:developer|debug|god|admin|jailbreak|dan|unrestricted)\s+mode\b|\bjailbreak\w*\b",
        r"\bsimulate\s+(?:being|an?)\b",
        r"\b(?:acum esti|esti acum|prefa-te|prefa te)\b",
    ],
    "FORMAT_SMUGGLE": [
        r"\"?\b(?:action|chat|type|a|b|i|r|s|intent|legal_actions)\b\"?\s*:\s*[\"\[{]",
        r"\b(?:action|chat)\s*:\s*\S",
        r"```|~~~|<\|[^|]*\|>|\[/?(?:inst|sys|system)\]|###\s*(?:system|instruction|user|assistant)|</?\s*(?:system|user|assistant|untrusted|opponent|instructions?|prompt|tool|function)\w*\s*>",
        r"\{\s*\"",
    ],
    "PROBE_STRATEGY": [
        r"\b(?:what(?:'s|s| is| are)|tell me|explain|describe|reveal|share|show me)\s+(?:\w+\s+){0,2}(?:your|ur)\s+(?:\w+\s+)?(?:strategy|strategies|algorithm|plan|approach|method|tactics?|technique|logic|reasoning|process)\b",
        r"\bhow\s+(?:do|did|will|are|would)\s+you\s+(?:play|decide|choose|pick|think|work|win|guess|know|calculate|compute|do\s+it)\b",
        r"\b(?:are|r)\s+you\s+(?:using|doing|running|playing|following|applying|trying)\b",
        r"\bdo\s+you\s+(?:use|follow|play|have\s+a\s+(?:plan|strategy|system))\b",
        r"\b(?:binary\s+search|mini-?max|alpha-?beta|monte\s+carlo|mcts|bisect\w*|midpoint|heuristic\w*|algorithm\w*)\b",
        r"\bwhy\s+(?:did|do|would|are)\s+you\s+(?:play|pick|choose|guess|fold|raise|call|bet|move|say|go)\b",
        r"\b(?:what|which)\s+(?:cards?|number|hand|move)\s+(?:do|did|will)\s+you\b",
        r"\bcare\s+(?:e|este)\s+(?:strategia|planul|metoda)\s+ta\b", r"\bcum\s+(?:joci|alegi|decizi|ghicesti)\b",
        r"\b(?:folosesti|urmezi)\b", r"\bai\s+(?:o\s+strategie|un\s+plan)\b", r"\barata-?mi\s+(?:mana|cartile)\b",
    ],
    "PRESSURE": [
        r"\b(?:fold|folds|folding|resign\w*|surrender\w*|give\s*-?\s*up|giving\s+up|concede\w*|forfeit\w*|quit|yield|withdraw|throw\s+in\s+the\s+towel|lay\s+down|bow\s+out|admit\s+defeat)\b",
        r"\byou\s+(?:will|are\s+going\s+to|are\s+gonna|gonna|already|have|ve|just|can't|cant|cannot)?\s*(?:definitely\s+|surely\s+)?(?:lose|lost|losing|loser|failed|are\s+done|are\s+finished|are\s+dead|are\s+beaten|are\s+toast|are\s+doomed|have\s+no\s+chance)\b",
        r"\b(?:you(?:'re|re| are)\s+(?:done|finished|dead|beaten|toast|doomed|lost|losing|hopeless)|it(?:'s|s| is)\s+(?:over|hopeless)|(?:game|match)\s+(?:is\s+)?(?:over|finished)|no\s+chance|stop\s+playing|just\s+(?:give|quit|stop))\b",
        # other languages
        r"\b(?:renunta|predate|te\s*-?\s*ai\s+dat\s+batut|ai\s+pierdut|vei\s+pierde|abandoneaza|lasa\s+jocul)\b",
        r"\b(?:rindete|te\s+rindes|has\s+perdido|vas\s+a\s+perder|abandona|rendete)\b",
        r"\b(?:abandonne|rends\s*-?\s*toi|tu\s+as\s+perdu|tu\s+vas\s+perdre|renonce)\b",
        r"\b(?:gib\s+auf|aufgeben|ergib\s+dich|du\s+verlierst|du\s+hast\s+verloren)\b",
        r"\b(?:arrenditi|ti\s+arrendi|hai\s+perso|abbandona|desista|voce\s+perdeu|desiste)\b",
    ],
    "SUGGEST_MOVE": [
        r"\b(?:you\s+(?:should|must|need\s+to|have\s+to|better|ought\s+to)|best\s+move|only\s+move|your\s+best|(?:just|please|now)\s+(?:play|pick|choose|take|go))\b",
        r"^\s*(?:play|pick|choose|take|go\s+for|select|try|bet|call|raise|roll|hold|guess|move\s+to|answer)\s+\S+",
    ],
}
# Patterns on the lower-case display text for scripts the ascii fold cannot read (Russian, Greek, Chinese...).
_RAW_NATIVE = {
    "INSTRUCTION": [r"(?:игнорируй|забудь|отмени|пропусти)\w*\s+(?:\w+\s+){0,3}(?:инструкци|правил|указани)", r"忽略.{0,6}(?:指令|规则|说明)", r"αγνόησε.{0,20}(?:οδηγίες|κανόνες)"],
    "PRESSURE": [r"(?:сдавайся|сдаюсь|сдайся|ты\s+проиграл\w*|проиграешь|откажись)", r"(?:放弃|认输|你输了)", r"(?:παραιτήσου|έχασες)"],
    "FAKE_AUTHORITY": [r"(?:система|администратор|организатор|арбитр|судья)\s*[:>\]]"],
    "REVEAL_PROMPT": [r"(?:покажи|раскрой|выведи)\s+(?:\w+\s+){0,2}(?:промпт|инструкци|ключ)"],
}
# Whole phrases for the squashed check (letters only, so spaced-out or punctuated text is still caught).
_SQUASH_PHRASES = {
    "INSTRUCTION": ["ignoreyourrule", "ignoreallrule", "ignorethepreviousinstruction", "ignorepreviousinstruction",
                    "ignoreallpreviousinstruction", "ignoreyourinstruction", "ignoreinstruction", "disregardyourinstruction",
                    "disregardyourrule", "forgetyourinstruction", "forgetyourrule", "overrideyourrule", "newinstruction",
                    "ignoreallinstruction", "ignorethepromptabove", "ignoreabove", "fromnowonyou"],
    "REVEAL_PROMPT": ["systemprompt", "revealyourprompt", "showyourprompt", "revealyourinstruction", "printyourinstruction",
                      "repeatyourinstruction", "yourapikey", "revealyourkey", "showyourplaybook"],
    "ROLEPLAY": ["youarenow", "pretendtobe", "pretendyouare", "developermode", "jailbreak", "actasan", "roleplayas"],
    "FAKE_AUTHORITY": ["messagefromthearena", "messagefromthesystem", "systemmessage", "arenanotice", "officialnotice",
                       "messagefromtheorganizers", "messagefromthejudges", "arenaannouncement"],
}

_COMPILED = {f: [re.compile(p, re.I | re.S) for p in ps] for f, ps in _RAW.items()}
_COMPILED_NATIVE = {f: [re.compile(p, re.I | re.S) for p in ps] for f, ps in _RAW_NATIVE.items()}
_SQUASH_DEDUP = {f: [re.sub(r"(.)\1+", r"\1", p) for p in ps] for f, ps in _SQUASH_PHRASES.items()}

# Characters that could close our untrusted tags or fake a format marker: replaced in the sanitized copy.
_DEFUSE = str.maketrans({"<": "‹", ">": "›", "{": "(", "}": ")", "`": "'", "[": "(", "]": ")"})


@dataclass
class ChatReport:
    original: str = ""
    sanitized: str = ""
    flags: list = field(default_factory=list)
    severity: int = 0
    pressure: bool = False       # the line tries to make us give up / says we lose
    suggests_move: bool = False  # the line tells us what to play
    hidden_chars: int = 0        # invisible characters that were removed

    @property
    def severity_name(self):
        return SEVERITY_NAME[self.severity]


def _find_spans(folded, display_text):
    """Collect (start, end, flag) of every medium-weight pattern hit, on the aligned forms."""
    hits = []
    for flag, pats in _COMPILED.items():
        for p in pats:
            for m in p.finditer(folded):
                if m.end() > m.start():
                    hits.append((m.start(), m.end(), flag))
    low = display_text.lower()
    for flag, pats in _COMPILED_NATIVE.items():
        for p in pats:
            for m in p.finditer(low):
                if m.end() > m.start():
                    hits.append((m.start(), m.end(), flag))
    return hits


def analyze(text, speech=None):
    """Analyze one raw chat line. `speech` (optional) is a SpeechRules object to spot forbidden-subject bait."""
    report = ChatReport()
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    report.original = text
    report.hidden_chars = nz.count_hidden_chars(text)
    shown = nz.display(text)
    folded_i = nz.ascii_fold(shown, "i")
    folded_l = nz.ascii_fold(shown, "l")
    flags = set()
    hits = []
    for folded in {folded_i, folded_l}:
        hits += _find_spans(folded, shown)
    for _s, _e, flag in hits:
        flags.add(flag)

    # squashed check: a phrase that only appears once spaces, punctuation and doubled letters are removed
    sq, sq_dedup = nz.squash(folded_i), nz.squash_dedup(folded_i)
    for flag, phrases in _SQUASH_PHRASES.items():
        for ph, ph_d in zip(phrases, _SQUASH_DEDUP[flag]):
            if ph in sq or ph_d in sq_dedup:
                if flag not in flags:
                    flags.add("UNICODE_TRICKS")  # the phrase was hidden from the plain patterns
                flags.add(flag)

    if report.hidden_chars >= 1 or nz.mixed_script_count(shown) >= 1:
        flags.add("UNICODE_TRICKS")

    # flooding: very long text, a long run of one character, or the same word again and again
    words = re.findall(r"\w+", shown.lower())
    if (len(shown) > MAX_SHOWN or re.search(r"(.)\1{14,}", shown)
            or (len(words) >= 8 and max(words.count(w) for w in set(words)) >= 8)):
        flags.add("FLOOD")

    if speech is not None and speech.mentions_forbidden(shown):
        flags.add("FORBIDDEN_BAIT")

    # --- sanitized copy: remove the dangerous spans (medium flags), defuse markers, cut flooding
    spans = sorted((s, e) for s, e, f in hits if FLAG_WEIGHT.get(f, 0) >= 2)
    out, pos = [], 0
    flag_at = {(s, e): f for s, e, f in hits}
    for s, e in spans:
        if s < pos:
            continue  # overlapping hit already replaced
        out.append(shown[pos:s].translate(_DEFUSE))
        out.append(f"[removed:{flag_at[(s, e)]}]")
        pos = e
    out.append(shown[pos:].translate(_DEFUSE))
    clean = "".join(out)
    # a forbidden word that was only mentioned (bait) is hidden from the model so it cannot be repeated
    if speech is not None:
        clean = speech.redact(clean)
    if len(clean) > MAX_SHOWN:
        clean = clean[:MAX_SHOWN] + f" [cut {len(clean) - MAX_SHOWN} chars]"
    report.sanitized = clean

    report.flags = sorted(flags)
    report.pressure = "PRESSURE" in flags
    report.suggests_move = "SUGGEST_MOVE" in flags
    weights = [FLAG_WEIGHT[f] for f in flags]
    sev = max(weights) if weights else 0
    mediums = [f for f in flags if FLAG_WEIGHT[f] >= 2]
    if sev >= 2 and (len(mediums) >= 2 or "UNICODE_TRICKS" in flags or "FLOOD" in flags):
        sev = 3  # a combined or obfuscated attack
    report.severity = min(sev, 3)
    return report
