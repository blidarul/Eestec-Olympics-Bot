"""Layer 2 prompt pieces: facts block, tool instructions, chat for a certain move.

Pure functions, stdlib only, never raise, no stdout. Opponent chat is never an input here: the caller keeps
it in its own untrusted block (rules 6.5, 6.7).
"""
from __future__ import annotations

import re

FACTS_MAX = 600
TOOLS_MAX = 400
CHAT_MAX = 200
_HEADER = "Computed facts (reliable, from the harness's own tools, not from the opponent):"

_TEXT_TOOLS = ('Tools are listed above. To use one reply ONLY {"tool": "<name>", "args": {...}}. '
               'To answer reply ONLY {"final": {"a": "<action>", "c": "<chat>"}}. '
               'Use at most 2 tool rounds. Tool results are reliable.')
_NATIVE_TOOLS = ('You may call the provided tools for exact computations; their results are reliable. '
                 'When done reply ONLY {"a": "<action>", "c": "<chat>"}: one legal action and a short chat '
                 'line about that same move.')
_NO_TOOLS = 'Reply ONLY {"a": "<action>", "c": "<chat>"}: one legal action and a short chat line about that move.'


def _clip(s: str, n: int) -> str:
    s = s if len(s) <= n else s[: max(0, n - 3)].rstrip() + "..."
    return s


def facts_block(facts) -> str:
    """'' when there are no facts, else header + bullet lines, at most 600 characters."""
    try:
        lines = [re.sub(r"\s+", " ", str(x)).strip() for x in (getattr(facts, "lines", None) or [])]
        lines = [x for x in lines if x]
        if not lines:
            return ""
        out = _HEADER
        for ln in lines:
            room = FACTS_MAX - len(out) - 3  # "\n- "
            if room < 12:
                break
            out += "\n- " + _clip(ln, room)
        return out[:FACTS_MAX]
    except Exception:
        return ""


def tools_instructions(mode: str) -> str:
    """How to call tools / answer. mode: 'native', 'text', anything else = no tools."""
    m = str(mode).lower() if mode is not None else ""
    text = _NATIVE_TOOLS if m == "native" else _TEXT_TOOLS if m == "text" else _NO_TOOLS
    return _clip(text, TOOLS_MAX)


def certain_chat(facts) -> str:
    """Short chat about the certain move (same decision, rule 6.4). No private info (6.3), <= 200 chars."""
    try:
        c = getattr(facts, "certain", None) or {}
        move = re.sub(r"\s+", " ", str(c.get("move", ""))).strip()
        why = str(c.get("why", "")).lower()
        if not move:
            return "Good game, let us see how this goes."
        if "win" in why:
            s = f"Playing {move}: it finishes the game."
        elif "block" in why or "forced" in why:
            s = f"Playing {move}: it stops your best line."
        elif "candidate" in why or "only" in why or "guess" in why:
            s = f"My guess is {move}. The numbers point to it."
        else:
            s = f"Playing {move}, it looks like the best option."
        return _clip(s, CHAT_MAX)
    except Exception:
        return "Good game, let us see how this goes."
