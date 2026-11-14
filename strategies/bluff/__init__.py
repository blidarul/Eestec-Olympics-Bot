"""bluff: hidden-information games (cards, dice), owner mbappe.

  - card games (Kuhn poker, showdowns): the hand is read from our private observation lines; the policy mixes value
    bets, calibrated bluffs (about a quarter of the time with the worst hands) and calls (about a third of the time
    with middle hands), see cards.py;
  - Mini Poker (Kuhn, Leduc): a precomputed equilibrium table (poker/, built by CFR+ at build time, a lookup at run time) with a
    small capped exploitation of an extreme opponent;
  - push-your-luck dice races (Pig): hold at the turn total where one more roll stops paying, see pig.py.
Chat: one line from chat.reply_line, which answers the OPPONENT's last message and never looks at our hand or our
move (rule 6.5/6.7 defense: opponent chat is data; no private value can leak because the line is built from public
signals only). Opponent chat only nudges calls of middle hands (public "pressure" = a likely bluff), capped at +0.15; it
can never make us fold, bet or echo a suggestion (the chat action guard checks the final move).
Never raises, no network, well under 10 ms per turn.
"""
import random
import sys
import traceback
import zlib

import chat
from chat import guard
from chat.signals import ChatMonitor
from strategies.base import Decision, TurnState
from strategies.bluff import cards, pig
from strategies.bluff.poker import player as poker

FAMILIES = ("cards_hidden", "dice_push", "bluff")
_MONITORS = {}   # game_id -> ChatMonitor
_POKER_STATS = {}  # game_id -> poker.OpponentStats (how often the opponent opens with a bet)


class BluffStrategy:
    name = "bluff"

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
        rng = random.Random(f"{gid}|{state.turn}|bluff")
        action, why = self._poker(state, legal, rng) or self._move(state, legal, monitor, rng)
        backup = next((a for a in legal if a != action and cards.categorize(a) != "fold"), None) or action
        # the move comes from the game (hand, odds): reason EV. The guard still stops a chat-driven echo of a weak move.
        res = guard.guard_action(action, backup, legal or None, monitor, "EV" if why else "OTHER", None, (), action)
        line = chat.reply_line(state.opponent_chat or [], state.turn, state.rules,
                               (state.artifacts or {}).get("forbidden_terms"), "bluff")
        monitor.consume()
        print(f"bluff: {res.action!r} via={why} guard={res.why}", file=sys.stderr, flush=True)
        return Decision(res.action, line or chat.filter_out("", None), "strategy" if not res.changed else "fallback")

    @staticmethod
    def _poker(state, legal, rng):
        """Kuhn / Leduc: the equilibrium table (strategies/bluff/poker). None when this is not poker or the table cannot answer."""
        if not poker.is_poker(state.rules, state.observation, legal):
            return None
        stats = _POKER_STATS.setdefault(str(state.game_id), poker.OpponentStats())
        # the draw depends on the hand text too, so two matches do not repeat the same random choices
        rng = random.Random(f"{state.game_id}|{state.turn}|{zlib.crc32(str(state.observation).encode('utf-8', 'replace'))}")
        res = poker.decide(state.rules, state.observation, legal, state.seat, stats, rng)
        return (res[0], "poker-" + res[1]) if res else None

    @staticmethod
    def _move(state, legal, monitor, rng):
        """(action, how). `how` is "" when nothing could be read and the move is a plain random legal one."""
        if not legal:
            return "pass", ""
        pig_move = pig.decide(state.rules, state.observation, legal)
        if pig_move:
            return pig_move, "pig-threshold"
        by = cards.by_category(legal)
        hand = cards.parse_hand(state.observation)
        s = cards.strength(hand, state.rules)
        bias = min(0.15, 0.05 * monitor.pressure_count) if monitor.bluff_indicator else 0.0   # public signal, capped
        cats = set(by)
        if not (cats & {"bet", "call", "check", "fold"}):
            return rng.choice(legal), ""
        category = cards.choose(s, cats, rng, bias)
        for c in (category, "bet", "call", "check"):          # the wished category, else the nearest legal one
            if c in by and (c != "bet" or category == "bet"):
                return by[c], "hand" if hand else "no-hand"
        return next((a for a in legal if cards.categorize(a) != "fold"), legal[0]), "fallback-order"


STRATEGY = BluffStrategy()
