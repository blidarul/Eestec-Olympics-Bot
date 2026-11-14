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


_DEFENSE = None
_DEFENSE_KEY = None


def reply_line(opponent_chat, turn=0, rules="", forbidden=None, family="", decision=None, chat_full=None, game=None):
    """One chat line in the current persona (config.PERSONA) for ANY strategy that picks its move itself. Same filters
    and limits as the full pipeline. Never raises: "" on a problem (the caller then keeps its own line).
    `opponent_chat`: the opponent's texts, oldest first.
    `decision` (rule 6.4): the move actually chosen (Decision object, dict or action string): the line is built from
    its kind (aggressive, passive, defensive, probe, neutral) and answers the opponent's message as the first sentence.
    `chat_full` (rule 6.1): the whole match chat [{"from","text"}, ...] with OUR lines: the pressure caps, the spacing
    and the no-repeat memory are recomputed from it, so they hold across all containers of the team."""
    global _DEFENSE, _DEFENSE_KEY
    try:
        from .pipeline import ChatDefense
        key = (str(rules)[:200], tuple(sorted(str(t) for t in (forbidden or []))), str(family))
        if _DEFENSE is None:
            _DEFENSE = ChatDefense(log=lambda *a: None)
        if key != _DEFENSE_KEY:  # new game: read its speech rules
            _DEFENSE.configure(str(rules), forbidden, None, family)
            _DEFENSE_KEY = key
        if isinstance(game, int):
            _DEFENSE.game_index = game
        return _DEFENSE.chat_only(list(opponent_chat) if isinstance(opponent_chat, (list, tuple)) else [], turn,
                                  decision, chat_full if isinstance(chat_full, (list, tuple)) else None)
    except Exception:
        return ""


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
