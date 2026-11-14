"""deals: negotiation, trust and betrayal (owner mbappe).

  - dilemma games (cooperate / defect): GENEROUS TIT FOR TAT. Cooperate first, copy the opponent's last move, but forgive a
    defection about 12 percent of the time so two retaliating players do not lock into mutual defection. If the opponent
    tracker (opponent/tracker.py) knows the opponent, the first move is cautious against a known defector and cooperative
    against a known cooperator (needs `state.opponent`, see issue #27; without it every opponent is unknown = cooperate);
  - bargaining over a pot (accept / reject / offer N): a firm first demand that concedes slowly towards a baseline we never go
    below; exploitative offers are rejected (bargaining.py). The numbers never reach the chat.
Chat: chat.reply_line in its negotiation mode (flat statements that our position does not move, answers to the opponent's
last message); the opponent's chat is data. Public signals only; no reservation value, no offer, no promise in any line.
Never raises, no network, well under 10 ms.
"""
import os
import random
import sys
import traceback

import chat
from chat import guard
from chat.signals import ChatMonitor
from opponent.tracker import OpponentTracker
from strategies.base import Decision, TurnState
from strategies.deals import bargaining
from strategies.read_opponent import history

FAMILIES = ("negotiation", "deals")
FORGIVENESS = 0.12            # a defection is forgiven this often (inside the 10-15 percent band)
COOPERATIVE, CAUTIOUS = 0.7, 0.3   # tracker cooperation rate limits for the first move
_MONITORS = {}


class DealsStrategy:
    name = "deals"

    def matches(self, rules, artifacts):
        family = (artifacts or {}).get("family") if isinstance(artifacts, dict) else None
        return 0.75 if family in FAMILIES else 0.0

    def decide(self, state: TurnState) -> Decision:
        legal = [a for a in (state.legal_actions or []) if isinstance(a, str)]
        try:
            return self._decide(state, legal)
        except Exception:  # never raise into the worker
            traceback.print_exc()
            return Decision(legal[0] if legal else "pass", chat.filter_out("", None), "fallback")

    def _decide(self, state, legal):
        gid = str(state.game_id)
        monitor = _MONITORS.setdefault(gid, ChatMonitor())
        monitor.update([{"from": "opponent", "text": t} for t in (state.opponent_chat or [])])
        rng = random.Random(f"{gid}|{state.turn}|deals")
        action, why = self._move(state, legal, rng)
        backup = next((a for a in legal if a != action), action)
        res = guard.guard_action(action, backup, legal or None, monitor, "EV" if why else "OTHER", None, (), action)
        line = chat.reply_line(state.opponent_chat or [], state.turn, state.rules,
                               (state.artifacts or {}).get("forbidden_terms"), "deals")
        monitor.consume()
        print(f"deals: {res.action!r} via={why} guard={res.why}", file=sys.stderr, flush=True)
        return Decision(res.action, line or chat.filter_out("", None), "strategy" if not res.changed else "fallback")

    # ---------------------------------------------------------------------------------
    def _move(self, state, legal, rng):
        """(action, how); how is "" when nothing could be read and the move is a plain random legal one."""
        if not legal:
            return "pass", ""
        if history.game_kind(legal, state.rules) == "dilemma":
            return self._tit_for_tat(state, legal, rng), "generous-tit-for-tat"
        total = bargaining.parse_total(state.rules, state.observation)
        r, rounds = bargaining.parse_round(state.observation, state.rules)
        offer = bargaining.parse_offer_to_us(state.observation)
        action, why = bargaining.pick_action(legal, state.rules, total, r, rounds, offer)
        if action:
            return action, why
        return rng.choice(legal), ""

    @staticmethod
    def _tit_for_tat(state, legal, rng):
        coop = next((a for a in legal if a.lower().startswith("coop")), legal[0])
        defect = next((a for a in legal if a != coop), coop)
        _ours, theirs = history.parse_history(state.observation, legal)
        if not theirs:  # first move: cooperative unless the tracker knows this opponent as a defector
            return defect if _known_cooperation(state) is not None and _known_cooperation(state) <= CAUTIOUS else coop
        if theirs[-1] == coop:
            return coop
        return coop if rng.random() < FORGIVENESS else defect


def _known_cooperation(state):
    """The opponent's cooperation rate from the tracker, or None when the opponent is unknown (or the name is missing)."""
    name = getattr(state, "opponent", "") or ""
    if not name:
        return None
    try:
        profile = OpponentTracker(os.environ.get("MEMORY_DIR", "/memory")).get_profile(name)
    except Exception:
        return None
    return profile["cooperation_rate"] if profile.get("known") else None


STRATEGY = DealsStrategy()
