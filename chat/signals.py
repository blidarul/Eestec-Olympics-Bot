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

from . import injection
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
        self.max_severity = 0
        self.new_reports = []         # reports first seen in the last update()

    # ---- reading the chat -----------------------------------------------------------
    def update(self, chat):
        """Process the lines we have not seen yet. `chat` is the whole conversation (oldest first)."""
        if not isinstance(chat, list):
            chat = []
        if len(chat) < self.seen:
            self.reset(self.match_id)  # a shorter chat can only be a new match
        self.new_reports = []
        for idx in range(self.seen, len(chat)):
            line = chat[idx]
            if not isinstance(line, dict) or line.get("from") != "opponent":
                continue
            rep = injection.analyze(line.get("text"), self.speech)
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
        if set(rep.flags) & INJECTION_FLAGS:
            self.injection_count += 1
        if "FORBIDDEN_BAIT" in rep.flags:
            self.bait_count += 1
        if "FLOOD" in rep.flags:
            self.flood_count += 1
        if rep.suggests_move:
            self.suggest_count += 1

    # ---- the signals ----------------------------------------------------------------
    @property
    def new_pressure(self):
        """A "fold / you lose" line arrived since the last turn."""
        return any(r.pressure for r in self.new_reports)

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
            low = " " + _words(line.get("text")) + " "
            if " " + want + " " in low:
                return True
        return False

    def features(self):
        """The signals as a plain dict (for strategies and for the logs)."""
        return {
            "opp_lines": self.opp_lines, "new_lines": len(self.new_reports),
            "pressure_count": self.pressure_count, "new_pressure": self.new_pressure,
            "injection_count": self.injection_count, "bait_count": self.bait_count,
            "flood_count": self.flood_count, "suggest_count": self.suggest_count,
            "max_severity": self.max_severity, "severity": injection.SEVERITY_NAME[self.max_severity],
            "heavy_pressure": self.heavy_pressure, "bluff_indicator": self.bluff_indicator,
            "flags": sorted(self.flag_counts),
        }


def _words(text):
    """Lower case words of a text joined by single spaces (letters and digits only)."""
    return " ".join(re.findall(r"[a-z0-9]+", nz.display(text).lower()))
