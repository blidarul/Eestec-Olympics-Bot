"""Robust parsing of the model's compact answer. Never raises, whatever the model returns.

Expected answer (one JSON object, nothing else):
    {"a": "<action>", "b": "<backup action>", "i": "<INTENT>", "r": "<REASON>"}  ("s" is read but IGNORED: the model
    never writes text for the opponent)
      a = the move we want to play (exactly as the rules write it)
      b = the second-best legal move (used if the guard rejects `a`: no second model call is needed)
      i = intent code (see intents.py)        s = optional slot text for the chat template
      r = why the move is good, from a fixed list (see REASONS): the guard uses it, see guard.py

Garbage handling: empty text, text around the JSON, code fences, several objects, a cut-off JSON,
or the old "ACTION: x" format are all accepted; anything else gives `ok=False` and the caller uses its fallback.
"""
import json
import re
from dataclasses import dataclass

from . import intents
from . import normalize as nz

REASONS = ("FORCED", "WIN", "BLOCK", "EV", "OTHER")
MAX_ACTION_CHARS = 120


@dataclass
class Decision:
    ok: bool = False          # an action was found in the model text
    action: str = ""
    backup: str = ""
    intent: str = "NEUTRAL"
    reason: str = "OTHER"
    slot: str = ""
    chat: str = ""            # the model's own chat line (human persona)
    how: str = "empty"        # which parsing path worked (for the logs and the tests)


def _as_text(v):
    if isinstance(v, (str, int, float)) and not isinstance(v, bool):
        return " ".join(str(v).split())[:MAX_ACTION_CHARS]
    return ""


def _objects(text):
    """Every JSON object found in the text, in order."""
    found, dec, i = [], json.JSONDecoder(), 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return found
        try:
            obj, end = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                found.append(obj)
            i = end
        except ValueError:
            i += 1


def parse_model_output(text):
    d = Decision()
    if not isinstance(text, str) or not text.strip():
        return d
    text = text.replace("```json", " ").replace("```", " ")
    obj = None
    for candidate in reversed(_objects(text)):  # the last object that has an action
        if any(k in candidate for k in ("a", "action")):
            obj = candidate
            break
    if obj is not None:
        d.action = _as_text(obj.get("a", obj.get("action")))
        d.backup = _as_text(obj.get("b", obj.get("backup")))
        d.intent = intents.normalize_intent(obj.get("i", obj.get("intent")))
        r = str(obj.get("r", obj.get("reason", ""))).strip().upper()
        d.reason = r if r in REASONS else "OTHER"
        slot = obj.get("s", obj.get("slot", ""))
        d.slot = slot if isinstance(slot, str) else ""
        chat = obj.get("chat")
        d.chat = " ".join(chat.split())[:400] if isinstance(chat, str) else ""
        d.how = "json"
    else:
        # cut-off JSON: take the first "a" value we can still read
        m = re.search(r'"a"\s*:\s*"([^"\n]{1,%d})"' % MAX_ACTION_CHARS, text)
        if m:
            d.action, d.how = " ".join(m.group(1).split()), "partial-json"
            for key, attr in (("b", "backup"), ("s", "slot")):
                m2 = re.search(r'"%s"\s*:\s*"([^"\n]{0,60})"' % key, text)
                if m2:
                    setattr(d, attr, m2.group(1))
            m3 = re.search(r'"i"\s*:\s*"([A-Za-z]{3,10})"', text)
            if m3:
                d.intent = intents.normalize_intent(m3.group(1))
        else:
            found = re.findall(r"ACTION:\s*(.+)", text)  # the starter's old format
            if found:
                d.action = re.split(r"\s+CHAT:", found[-1])[0].strip()[:MAX_ACTION_CHARS]
                d.how = "legacy"
    d.ok = bool(d.action)
    if not d.ok:
        d.how = "no-action"
    return d


def _norm(s):
    return re.sub(r"\s+", " ", nz.display(s).lower()).strip(" .\"'")


def match_legal(action, legal):
    """The legal action that `action` names (same text, case and spacing ignored), or None."""
    if not legal or not isinstance(action, str) or not action.strip():
        return None
    want = _norm(action)
    for a in legal:
        if isinstance(a, str) and _norm(a) == want:
            return a
    return None


def format_ok(action):
    """Light check for games with `legal_actions: null`: one short printable line, nothing else we can know here."""
    return (isinstance(action, str) and 0 < len(action.strip()) <= MAX_ACTION_CHARS
            and "\n" not in action and "{" not in action and "ACTION:" not in action.upper())
