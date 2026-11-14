"""chat/: opponent chat defense and chat composition (owner: mbappe). See CHAT_DEFENSE.md.

The core (core/hooks.py) looks for two functions here and uses them for EVERY strategy, if they exist:
    wrap_untrusted(lines) -> str     the opponent chat for a model prompt: untrusted tags, sanitized, flags, counters
    filter_out(text, forbidden)      the output filters (leak, conduct, collusion, forbidden terms, length, repeats)
Both never raise; on any problem they return "" / a neutral line and the core uses its own simple version.
The full pipeline (compact model answer, action guard, templates) is in pipeline.py and is used by
strategies/guardrails/chat_defense.
"""
from collections import deque

from . import config, final_stage
from .signals import ChatMonitor
from .speech_rules import SpeechRules
from . import wrap as _wrap

_MONITOR = ChatMonitor()                       # one per process: the worker lives for the whole tournament
_RECENT = deque(maxlen=config.RECENT_LINES)    # the last lines that passed filter_out (no triple repeats)
_SPEECH_CACHE = {}


def wrap_untrusted(lines):
    """`lines`: the opponent's chat texts, oldest first (core/main.py passes strings only)."""
    try:
        chat = list(lines) if isinstance(lines, (list, tuple)) else []
        _MONITOR.update(chat)  # a shorter list than before = a new match: the monitor resets itself
        return _wrap.build_chat_block(chat, _MONITOR)
    except Exception:
        return ""


def filter_out(text, forbidden=None):
    """Final-stage filters on one chat line. `forbidden`: forbidden words of the game (from prep)."""
    try:
        key = tuple(sorted(str(t) for t in (forbidden or []) if str(t).strip()))
        if key not in _SPEECH_CACHE:
            if len(_SPEECH_CACHE) > 50:
                _SPEECH_CACHE.clear()
            _SPEECH_CACHE[key] = SpeechRules(list(key), bool(key))
        line, _problems = final_stage.finalize_chat(text, _SPEECH_CACHE[key], (), _RECENT, "", False, len(_RECENT))
        _RECENT.append(line)
        return line
    except Exception:
        return ""
