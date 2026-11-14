"""How the opponent's chat reaches a DECISION in a solver or pure-code strategy (rules 6.5, 6.6, 6.7).

A strategy that computes its move without a model (minimax, solver tables, fallback) calls pick_among_equal() with the
moves it already rates EQUAL. The untrusted chat then breaks the tie, never more:
  - a move the opponent's chat just told us to play is put last (we do not follow orders, 6.7);
  - a surrender-like move (fold, resign, concede...) is put last (chat can never cause one);
  - otherwise the caller's order stands (stable).
A move that is not part of the tie is never touched: the chat has no weight against the game's own evaluation.
The change is logged to stderr in one short line (no state, no secrets, no opponent text).
"""
import sys

from . import guard
from .signals import ChatMonitor


def pick_among_equal(candidates, opponent_chat, log=None):
    """(action, influenced): `candidates` are moves the caller values equally, best-first by its own order.
    `opponent_chat`: the opponent's texts, oldest first (untrusted). Never raises; the first candidate on any problem."""
    cands = [c for c in (candidates or []) if isinstance(c, str)]
    if not cands:
        return None, False
    try:
        mon = ChatMonitor()  # a fresh monitor per call: the monitor tracks a growing chat, this function is stateless
        mon.update(list(opponent_chat) if isinstance(opponent_chat, (list, tuple)) else [])
        keyed = sorted(enumerate(cands), key=lambda p: (guard.is_surrender_like(p[1]), mon.is_suggested(p[1]), p[0]))
        best = keyed[0][1]
        changed = best != cands[0]
        if changed:
            (log or (lambda *a: print(*a, file=sys.stderr, flush=True)))("chat influenced a tie-break among", len(cands),
                                                                          "equal moves (untrusted chat, capped)")
        return best, changed
    except Exception:
        return cands[0], False
