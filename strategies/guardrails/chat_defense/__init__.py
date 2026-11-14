"""Chat-aware default strategy (family guardrails, owner mbappe).

It is the strategy for the Guardrails family only (matches() = 0.6 there, 0.0 elsewhere, issue #18); the chat
hooks protect the chat of every other strategy too. It adds, around ONE model call per move:
  - the opponent chat inside untrusted tags + counters (chat/wrap.py), also with the model missing,
  - the compact answer {"a","b","i","r","s"} and the chat line built by code (chat/intents.py),
  - the action guard (never give up, never echo the chat, always legal: chat/guard.py),
  - the final output stage and the filters (chat/final_stage.py),
  - budget guard and model-free play (chat/budget.py): the chat signals still choose the move.
It runs in the worker process (core/worker.py), which has a hard deadline: the main process already holds a
legal fallback move and a neutral chat before the worker is asked.
"""
import hashlib
import sys
import time
import traceback

from chat import config
from chat.budget import BudgetGuard
from chat.pipeline import ChatDefense
from core import fallback
from strategies.base import Decision, TurnState

_DEFENSES = {}          # game_id -> (ChatDefense, config key): one per game, the worker lives for the tournament
_BUDGET = BudgetGuard()


def _defense(state):
    key = (hashlib.sha1(str(state.rules).encode("utf-8", "replace")).hexdigest()[:12],
           tuple(str(t) for t in (state.artifacts or {}).get("forbidden_terms") or []),
           str((state.artifacts or {}).get("family", "")))
    entry = _DEFENSES.get(state.game_id)
    if entry is None:
        entry = _DEFENSES[state.game_id] = [ChatDefense(), None]
    d, done = entry
    if done != key:  # new rules text or new forbidden terms: read the speech rules again
        d.configure(state.rules, (state.artifacts or {}).get("forbidden_terms"),
                    (state.artifacts or {}).get("rules_text_hash_dir"), (state.artifacts or {}).get("family", ""))
        entry[1] = key
    return d


def _turn(state):
    """TurnState -> the turn dict the chat package reads. The core passes the opponent's texts only."""
    return {"turn": state.turn, "observation": state.observation, "legal_actions": state.legal_actions,
            "warning": state.warning, "chat": [{"from": "opponent", "text": t} for t in (state.opponent_chat or [])]}


class ChatDefenseStrategy:
    name = "chat_defense"

    def matches(self, rules, artifacts):
        """Only the Guardrails family (a forbidden subject in the rules) is ours: above the router threshold (0.5)
        there, 0.0 everywhere else, so every other family keeps its own strategy or core/generic (issue #18).
        The chat hooks (chat.wrap_untrusted, chat.filter_out) still protect and cool the chat of ALL strategies."""
        family = (artifacts or {}).get("family") if isinstance(artifacts, dict) else None
        return 0.6 if family == "guardrails" else 0.0

    def decide(self, state: TurnState) -> Decision:
        t0 = time.monotonic()
        art = state.artifacts or {}
        legal = state.legal_actions
        rejected = (state.warning or {}).get("rejected") if isinstance(state.warning, dict) else None
        fb = fallback.fallback_action(legal, art, rejected)  # legal, needs no model
        d, turn = _defense(state), _turn(state)
        prefs = (art.get("fallback_policy") or {}).get("prefer") or []
        llm = state.llm
        try:
            use_model = (llm is not None and llm.available() and _BUDGET.allows(llm)
                         and time.monotonic() < state.deadline - 1.5 and not (legal and len(legal) == 1))
            text = None
            if use_model:
                playbook = str(art.get("playbook") or "")[:1200]
                # the full rules text costs about 400 tokens per call: send it only when it is really needed
                # (no playbook from prep, or no legal-move list so the action format must come from the rules)
                rules = state.rules if (not playbook or not legal) else "(in the playbook and the observation)"
                system, user = d.prompts(turn, rules, playbook, state.seat)
                timeout = max(1.0, min(8.0, state.deadline - time.monotonic() - 0.5))
                try:
                    text = llm.ask(system, user, timeout=timeout)  # ONE call: move and chat together (6.4)
                except Exception:
                    traceback.print_exc()
            if text and text.strip():
                action, chat, info = d.finish(text, turn, fb, None, prefs, rejected)
                # "model" only when the model's own move was played: if the guard changed or forced the move (any
                # guard code), or the answer was unusable, the move did not come from the model (the decision log shows the truth)
                source = "model" if (info["parsed"] not in ("empty", "no-action") and not info["guard"]) else "fallback"
            else:  # no model, no budget, timeout, empty answer: the signals still steer the move
                action, chat, info = d.model_free(turn, fb, prefs, rejected)
                source = "fallback"
            print(f"chat_defense: {action!r} src={source} intent={info['intent']} guard={info['guard']} "
                  f"problems={info['problems']} sev={info['signals']['severity']} {time.monotonic() - t0:.2f}s",
                  file=sys.stderr, flush=True)
            return Decision(action, chat, source)
        except Exception:  # never raise into the worker: a legal move and a neutral line
            traceback.print_exc()
            from chat import final_stage
            return Decision(fb, final_stage.finalize_chat("", None, (), (), "", False, 0)[0], "fallback")


STRATEGY = ChatDefenseStrategy()
