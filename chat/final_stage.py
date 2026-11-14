"""The FINAL output stage for chat: the one place that guarantees a valid chat line, whatever happened before.

Every chat we send (normal path, model failure, timeout fallback, budget fallback, retry after a warning)
goes through finalize_chat(). It guarantees that the line:
  - is a string, not empty, at most MAX_CHARS characters (the limit is 200: rule 6.2),
  - passed ALL filters on the FINAL expanded text: leak (also our secret canary tag), conduct, collusion words,
    the game's speech rules, and for CONCEDE_PRESSURE the no-deal filter,
  - has no leftover template marker ("{s}", "{", "}"),
  - is not the same line again for the third time in a row.
Nothing here trusts the model: a bad line is replaced by a neutral one, it is never "fixed" by guessing.
"""
import re

from . import output_filters as of
from .config import MAX_SAME_IN_ROW

# More neutral lines than output_filters.NEUTRAL_LINES, so the last resort can rotate without repeating.
ROTATION = of.NEUTRAL_LINES + ["Go on.", "Your turn.", "Very well.", "Carry on.", "I see.", "Fine.", "Proceed.", "Understood."]


def _has_marker(line):
    return bool(re.search(r"[{}]|\[removed|\bnone\b|\bnull\b|<[^>]*>", line, re.I))


def _repeated(line, recent):
    last = list(recent)[-MAX_SAME_IN_ROW:]
    return len(last) >= MAX_SAME_IN_ROW and all(x == line for x in last)


def finalize_chat(line, speech=None, private_tokens=(), recent=(), canary="", one_sided=False, seed=0):
    """Return (final_line, problems). Never raises, never returns an empty string."""
    problems = []
    try:
        if not isinstance(line, str):
            problems.append("not-a-string")
            line = ""
        line, bad = of.check_line(line, speech, private_tokens, seed, canary, one_sided)
        problems += bad
        if _has_marker(line):
            problems.append("marker")
            line = ""
        if not line.strip() or _repeated(line, recent):
            if line.strip():
                problems.append("repeat")
            line = _rotate(speech, private_tokens, recent, canary, seed)
        return line, problems
    except Exception:  # the last line of defense must not fail
        return ".", problems + ["final-stage-error"]


def _rotate(speech, private_tokens, recent, canary, seed):
    """A neutral line that passes the filters and differs from the last lines."""
    last = list(recent)[-MAX_SAME_IN_ROW:]
    n = len(ROTATION)
    for k in range(n):
        cand = ROTATION[(seed + k) % n]
        if cand in last:
            continue
        if of.check_line(cand, speech, private_tokens, 0, canary)[1] == []:
            return cand
    return "."
