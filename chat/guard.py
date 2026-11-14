"""Action guard: sits between the model's proposed move and what we send.

The chat must never decide the move on its own. The guard does three things:
  1. LEGALITY: the action must be one of `legal_actions` (or, when the list is null, a clean one-line action).
     Otherwise we use the model's backup move, then the caller's fallback (rule 8.1: a second bad answer loses).
  2. SURRENDER: a surrender-like move (fold, resign, give up...) is accepted only with an independent reason.
  3. ECHO: a move that the opponent's chat just told us to play is accepted only with an independent reason.
"Independent reason" means a reason that does not come from the chat:
  - it is the only legal move, or
  - a game strategy says so (the optional `hook(action) -> bool`, e.g. a solver says it is the best move), or
  - the model gave a reason code (r) that points at the game itself (FORCED/WIN/BLOCK/EV), and for a
    surrender also: no pressure line in the last opponent lines (so "fold!" spam cannot work).
If the reason is missing, the guard replaces the move by the best ALTERNATIVE: the model's backup move (b), then
the strategy's ranking `prefs`, then the first legal move that is neither a surrender nor an echo.
"""
import re
from dataclasses import dataclass

from . import normalize as nz
from . import parse

SURRENDER_WORDS = {"fold", "folds", "resign", "resigns", "surrender", "concede", "forfeit", "quit", "abandon",
                   "yield", "withdraw", "giveup", "renunta", "predate", "rindete", "abandonne", "aufgeben"}
_SURRENDER_PHRASES = ("give up", "gives up", "throw in the towel", "lay down", "i quit", "i resign", "i fold")
OWN_REASONS = {"FORCED", "WIN", "BLOCK", "EV"}  # reason codes that point at the game, not at the chat


def is_surrender_like(action):
    """True for fold / resign / give up / ... in any listed spelling."""
    text = nz.display(action).lower() if isinstance(action, str) else ""
    words = set(re.findall(r"[a-z]+", nz.ascii_fold(text, "i")))
    if words & SURRENDER_WORDS:
        return True
    plain = " " + " ".join(re.findall(r"[a-z]+", nz.ascii_fold(text, "i"))) + " "
    return any(" " + p + " " in plain for p in _SURRENDER_PHRASES)


@dataclass
class GuardResult:
    action: str
    changed: bool = False
    why: str = ""          # "", "illegal", "surrender", "echo", "forced"
    pressured: bool = False  # the guard acted because of chat pressure (the caller may answer coldly)


def _acceptable(action, legal):
    if legal:
        return parse.match_legal(action, legal) is not None
    return parse.format_ok(action)


def guard_action(action, backup, legal, monitor, reason="OTHER", hook=None, prefs=(), fallback=""):
    """Return a GuardResult. `legal` is the list of legal actions or None; `monitor` is the ChatMonitor."""
    legal = [a for a in legal if isinstance(a, str)] if isinstance(legal, list) else None

    # 1. legality ---------------------------------------------------------------------------------
    ok = bool(action) and _acceptable(action, legal)
    if ok and legal:
        action = parse.match_legal(action, legal)  # the exact spelling from the list
    if not ok:
        for cand in (backup, fallback):
            if cand and _acceptable(cand, legal):
                action = parse.match_legal(cand, legal) if legal else cand
                return _after_legality(GuardResult(action, True, "illegal"), backup, legal, monitor, reason, hook, prefs, fallback)
        action = legal[0] if legal else (fallback or action or "")
        return GuardResult(action, True, "illegal")
    if legal and len(legal) == 1:
        return GuardResult(legal[0], False, "forced")  # nothing else is possible, so nothing to defend
    return _after_legality(GuardResult(action), backup, legal, monitor, reason, hook, prefs, fallback)


def _after_legality(res, backup, legal, monitor, reason, hook, prefs, fallback):
    """Steps 2 and 3 for a legal action."""
    action = res.action
    surrender = is_surrender_like(action)
    echoed = monitor.is_suggested(action) if monitor else False
    if not surrender and not echoed:
        return res
    if hook is not None:
        try:
            if hook(action):
                return res  # the game logic itself backs this move
        except Exception:
            pass  # a broken hook must never break the turn
    if surrender:
        justified = reason in {"FORCED", "EV"} and not (monitor and monitor.recent_pressure(3))
    else:
        justified = reason in OWN_REASONS and not (monitor and monitor.new_severity >= 3)
    if justified:
        return res
    alt = _alternative(action, backup, legal, monitor, prefs, fallback)
    if alt is None or alt == action:
        return res  # nothing better exists (for example every legal move is a surrender)
    pressured = bool(monitor and (monitor.new_pressure or monitor.pressure_count))
    return GuardResult(alt, True, "surrender" if surrender else "echo", pressured)


def _banned(action, monitor):
    return is_surrender_like(action) or (monitor is not None and monitor.is_suggested(action))


def _alternative(action, backup, legal, monitor, prefs, fallback):
    """The best other move: model backup, then strategy preferences, then the first clean legal move."""
    candidates = [backup] + list(prefs or [])
    if legal:
        candidates += legal
    else:
        candidates.append(fallback)
    for cand in candidates:
        if not cand or not _acceptable(cand, legal):
            continue
        cand = parse.match_legal(cand, legal) if legal else cand
        if cand != action and not _banned(cand, monitor):
            return cand
    return None
