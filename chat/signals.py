"""ChatMonitor: reads the opponent chat once, keeps counters, and exposes them as SIGNALS for decisions.

This is where the opponent chat reaches the DECISION LOGIC (rules 6.5, 6.6), next to the model prompt:
  - the prompt builder (wrap.py) prints the counters and every analyzed line for the model,
  - the action guard (guard.py) reads `pressure_count`, `is_suggested()` and the severity,
  - other strategies can call `features()` to get the same numbers as a dict (e.g. "heavy fold spam" is a
    bluff/injection indicator for a bluffing strategy).
Nothing is dropped: every opponent line is analyzed and counted, only the display is shortened.
"""
import re
from collections import Counter

from . import config, injection, robust
from . import normalize as nz

KEEP_REPORTS = 60        # analyzed opponent lines kept in memory
HEAVY_PRESSURE = 3       # this many "fold / you lose" lines in a match = heavy spam
INJECTION_FLAGS = {"INSTRUCTION", "FAKE_AUTHORITY", "REVEAL_PROMPT", "ROLEPLAY", "FORMAT_SMUGGLE"}


class ChatMonitor:
    def __init__(self, speech=None):
        self.speech = speech
        self.reset()

    def reset(self, match_id=None):
        """Start of a new match: the chat starts empty again."""
        self.match_id = match_id
        self.resets = getattr(self, "resets", 0) + 1   # counts new matches (the pipeline watches it)
        self.seen = 0                 # chat lines already processed
        self.lines = []               # (index, line dict, ChatReport) of opponent lines, newest last
        self.by_index = {}            # chat index -> ChatReport
        self.flag_counts = Counter()
        self.opp_lines = 0
        self.pressure_count = 0
        self.injection_count = 0
        self.bait_count = 0
        self.flood_count = 0
        self.suggest_count = 0
        self.concede_request_count = 0  # lines that ask us to give up (also counted in pressure_count)
        self.probe_count = 0          # questions about our strategy or our hand
        self.repeat_count = 0         # the opponent said the same thing as in its previous line
        self.last_text = None
        self.repeated_now = False
        self.max_severity = 0
        self.new_reports = []         # reports first seen in the last update()
        self.skipped = 0              # lines of a huge chat that were only counted, not analyzed

    # ---- reading the chat -----------------------------------------------------------
    def update(self, chat):
        """Process the lines we have not seen yet. `chat` is the whole conversation (oldest first)."""
        if not isinstance(chat, (list, tuple)):
            chat = []
        if len(chat) < self.seen:
            self.reset(self.match_id)  # a shorter chat can only be a new match
        elif len(chat) == self.seen:
            return self  # nothing new: keep the "new this turn" signals until consume() is called
        self.new_reports = []
        self.repeated_now = False     # one of the new lines repeated the previous opponent line
        start = max(self.seen, len(chat) - config.CHAT_WINDOW)  # a huge chat: only the last lines are analyzed
        if start > self.seen:
            self.skipped += start - self.seen
            self.flag_counts["FLOOD"] += 1
            self.flood_count += 1
        for idx in range(start, len(chat)):
            line = robust.clean_line(chat[idx])  # tolerant: strings, missing fields, odd types
            if line["from"] != "opponent":
                continue
            rep = injection.analyze(line["text"], self.speech)
            self._count(idx, line, rep)
            self.new_reports.append(rep)
        self.seen = len(chat)
        if len(self.new_reports) >= 5:  # five or more lines in one turn = flooding the chat
            self.flood_count += 1
            self.flag_counts["FLOOD"] += 1
        return self

    def _count(self, idx, line, rep):
        self.opp_lines += 1
        self.lines.append((idx, line, rep))
        self.by_index[idx] = rep
        if len(self.lines) > KEEP_REPORTS:
            old_idx = self.lines.pop(0)[0]
            self.by_index.pop(old_idx, None)
        self.flag_counts.update(rep.flags)
        self.max_severity = max(self.max_severity, rep.severity)
        if rep.pressure:
            self.pressure_count += 1
        if "CONCEDE_REQUEST" in rep.flags:
            self.concede_request_count += 1
        if set(rep.flags) & INJECTION_FLAGS:
            self.injection_count += 1
        if "FORBIDDEN_BAIT" in rep.flags:
            self.bait_count += 1
        if "FLOOD" in rep.flags:
            self.flood_count += 1
        if rep.suggests_move:
            self.suggest_count += 1
        if {"PROBE_STRATEGY", "REVEAL_PROMPT", "REVEAL_PRIVATE"} & set(rep.flags):
            self.probe_count += 1
        text = " ".join(str(line.get("text", "")).lower().split())
        if text and text == self.last_text:
            self.repeat_count += 1
            self.repeated_now = True
        self.last_text = text

    def consume(self):
        """The turn is answered: the "new this turn" signals (pressure, probes, repeats) are used up."""
        self.new_reports = []
        self.repeated_now = False

    # ---- the signals ----------------------------------------------------------------
    @property
    def new_pressure(self):
        """A "fold / you lose" line arrived since the last turn."""
        return any(r.pressure for r in self.new_reports)

    @property
    def new_probe(self):
        """A question about our strategy / hand / prompt arrived since the last turn."""
        return any({"PROBE_STRATEGY", "REVEAL_PROMPT", "REVEAL_PRIVATE"} & set(r.flags) for r in self.new_reports)

    @property
    def new_hostile(self):
        """Pressure, injection or a fake notice arrived since the last turn."""
        return self.new_pressure or any(set(r.flags) & INJECTION_FLAGS for r in self.new_reports)

    @property
    def opponent_repeats(self):
        """The opponent keeps repeating itself (a public signal we may comment on)."""
        return self.repeat_count >= config.REPEAT_UNSETTLE

    @property
    def new_severity(self):
        return max([r.severity for r in self.new_reports] or [0])

    @property
    def heavy_pressure(self):
        return self.pressure_count >= HEAVY_PRESSURE

    @property
    def bluff_indicator(self):
        """Pressure spam, or pressure together with fake instructions: the opponent is probably bluffing or injecting."""
        return self.heavy_pressure or (self.pressure_count >= 1 and self.injection_count >= 1)

    def recent_pressure(self, n=3):
        """Is one of the last n opponent lines a pressure line?"""
        return any(r.pressure for _i, _l, r in self.lines[-n:])

    def is_suggested(self, action, n=6):
        """Did one of the last n opponent lines tell us to play `action`? (a mention with an imperative cue)"""
        want = _words(action)
        if not want:
            return False
        for _i, line, rep in self.lines[-n:]:
            if not (rep.suggests_move or rep.severity >= 2):
                continue  # a plain mention ("I will play B2") is a claim, not a suggestion
            low = " " + _words(line.get("text", "")) + " "
            if " " + want + " " in low:
                return True
        return False

    def features(self):
        """The signals as a plain dict (for strategies and for the logs)."""
        return {
            "opp_lines": self.opp_lines, "new_lines": len(self.new_reports),
            "pressure_count": self.pressure_count, "new_pressure": self.new_pressure,
            "concede_request_count": self.concede_request_count, "probe_count": self.probe_count, "repeat_count": self.repeat_count,
            "injection_count": self.injection_count, "bait_count": self.bait_count,
            "flood_count": self.flood_count, "suggest_count": self.suggest_count,
            "max_severity": self.max_severity, "severity": injection.SEVERITY_NAME[self.max_severity],
            "heavy_pressure": self.heavy_pressure, "bluff_indicator": self.bluff_indicator,
            "flags": sorted(self.flag_counts),
        }


def _words(text):
    """Lower case words of a text joined by single spaces (letters and digits only)."""
    return " ".join(re.findall(r"[a-z0-9]+", nz.display(text).lower()))
