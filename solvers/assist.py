"""Layer 2, phase L5: one-call entry point for the core owner.

assist_turn(...) -> Assist. Order: precompute -> certain move (no model) -> select tools -> run_tool_loop with
the facts block appended to the user prompt -> suggestion from the model's final, or None.

Library only (no core/, prep/, chat/, strategies/ imports). Opponent chat is never an argument: the caller keeps
it inside base_user as its own untrusted block (rules 6.5, 6.7). The suggestion is checked against
legal_actions when they are known, but the caller still validates it (layer 2 suggests, the core decides).
Never raises, never writes to stdout.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from typing import Optional

from solvers import evidence
from solvers.precompute import Facts, precompute
from solvers.prompting import certain_chat, facts_block, tools_instructions
from solvers.select import select_tools
from solvers.toolloop import LoopResult, run_tool_loop

PRECOMPUTE_S = 0.3
SEARCH_S = 6.0          # budget of the simulator search (M6)
MODEL_RESERVE_S = 8.0   # always left for the model call after the search
CHAT_MAX = 200


@dataclass
class Assist:
    facts: Facts
    tools: list
    loop: Optional[LoopResult]
    suggestion: Optional[dict]   # {"action", "chat", "source": "tool"|"model", "why"}
    truth_check: Optional[str] = None   # "supported" | "unknown" | "skipped" | None (not a truth game)


def _log(msg):
    try:
        print("[assist] " + msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _legal_action(action, legal):
    """Original legal string for action, or None. legal None/empty = unknown, accept the text as is."""
    a = str(action).strip()
    if not a:
        return None
    if not legal:
        return a
    if a in legal:
        return a
    n = _norm(a)
    for x in legal:
        if _norm(x) == n:
            return x
    return None


def _is_truth(rules, artifacts):
    fam = artifacts.get("family") or artifacts.get("prep_family")
    return fam == "truth" or bool(evidence._TRUTHY.search(str(rules or "")[:20000]))


def _evidence(observation, rules, artifacts, legal, deadline):
    """Evidence block (<= 1500 chars) for truth games, else ''. Separate from the facts block."""
    try:
        if not _is_truth(rules, artifacts) or evidence.find_unknown_form(rules, legal) is None:
            return ""
        obs = str(observation or "")
        own_q = isinstance(artifacts.get("question"), str)
        q = artifacts["question"] if own_q else obs[-600:]
        body = obs if own_q else obs[:-len(q)]   # the question is not evidence for itself
        doc = artifacts.get("document") if isinstance(artifacts.get("document"), str) else \
            "%s\n\n%s" % (rules or "", body)
        return evidence.evidence_block(doc, q, 3, evidence.EVIDENCE_MAX, min(float(deadline), time.monotonic() + 0.2))
    except Exception as exc:  # noqa: BLE001
        _log("evidence failed: %s" % exc)
        return ""


def _truth(act, observation, rules, artifacts, legal, deadline):
    """-> (action, truth_check status). Replaces an unsupported answer by the rules' unknown form."""
    try:
        r = evidence.truth_check(act, rules, observation, legal, artifacts, min(float(deadline), time.monotonic() + 0.2))
        if r["status"] == "skipped" and r["why"] in ("not a truth game", "no unknown form in the rules"):
            return act, None
        _log("truth_check: %s (%s)" % (r["status"], r["why"]))
        return r["action"], r["status"]
    except Exception as exc:  # noqa: BLE001
        _log("truth_check failed: %s" % exc)
        return act, None


def assist_turn(observation, legal_actions, artifacts, rules, llm_call, base_system, base_user,
                deadline, native=True) -> Assist:
    facts, tools, loop, tcheck = Facts(), [], None, None
    try:
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        try:
            now = time.monotonic()
            facts = precompute(str(observation or ""), legal_actions, artifacts, str(rules or ""),
                               min(float(deadline), now + PRECOMPUTE_S),
                               search_deadline=min(now + SEARCH_S, float(deadline) - MODEL_RESERVE_S))
        except Exception as exc:  # noqa: BLE001
            _log("precompute failed: %s" % exc)
        c = facts.certain
        if c and c.get("move"):
            move = _legal_action(c["move"], legal_actions)
            if move is not None and (legal_actions or []):
                return Assist(facts, [], None, {"action": move, "chat": certain_chat(facts)[:CHAT_MAX],
                                                "source": "tool", "why": str(c.get("why", ""))})
        try:
            tools = select_tools(artifacts, str(observation or ""), str(rules or ""), facts)
        except Exception as exc:  # noqa: BLE001
            _log("select_tools failed: %s" % exc)
            tools = []
        fb = facts_block(facts)
        user = str(base_user) + ("\n\n" + fb if fb else "")
        ev = _evidence(observation, rules, artifacts, legal_actions, deadline)
        if ev:
            user += "\n\n" + ev
        system = str(base_system)
        if native or not tools:
            system += "\n" + tools_instructions("native" if (native and tools) else "none")
        loop = run_tool_loop(llm_call, system, user, tools, deadline, max_rounds=2, native=bool(native))
        fin = loop.final if loop else None
        if isinstance(fin, dict):
            act = _legal_action(fin.get("a"), legal_actions)
            if act is not None:
                chat = re.sub(r"\s+", " ", str(fin.get("c") or "")).strip()[:CHAT_MAX]
                act, tcheck = _truth(act, observation, rules, artifacts, legal_actions, deadline)
                if tcheck == "unknown":   # the move changed, so the chat must follow it (rule 6.4)
                    chat = "I can't find support for an answer in the text, so I say unknown."
                return Assist(facts, tools, loop, {"action": act, "chat": chat, "source": "model",
                                                   "why": "model (tools: %s)" % ",".join(
                                                       sorted({t.get("tool") for t in loop.trace
                                                               if t.get("tool")}))}, tcheck)
    except BaseException as exc:  # noqa: BLE001
        _log("failed: %s: %s" % (type(exc).__name__, exc))
    return Assist(facts, tools, loop, None)
