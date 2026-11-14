"""Tolerant reading of the `chat` array of a message (rule 6.1 describes the fields).

A chat line is {"from": "you"|"opponent", "game", "game_name", "phase", "turn", "kind": "chat"|"move", "text"}.
Real messages follow that, but this code must never crash on anything else: a missing or unknown field, a
number instead of a string, a plain string instead of a dict, None, nested lists, a huge array.
Rules used here:
  - an unknown or missing `from` counts as the OPPONENT (the safe choice: we never ignore a line);
  - `text` becomes a string (numbers are converted, other types become ""), cut to MAX_TEXT characters;
  - the array is cut to its last `window` entries (the rest is only counted).
"""
MAX_TEXT = 5000


def _text(value):
    if isinstance(value, str):
        return value[:MAX_TEXT]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)[:MAX_TEXT]
    return ""


def clean_line(line):
    """One chat entry -> {"from", "text", "game", "turn", "kind"}. Never raises."""
    try:
        if isinstance(line, str):
            return {"from": "opponent", "text": line[:MAX_TEXT], "game": "?", "turn": "?", "kind": "chat"}
        if not isinstance(line, dict):
            return {"from": "opponent", "text": "", "game": "?", "turn": "?", "kind": "chat"}
        who = "you" if line.get("from") == "you" else "opponent"
        kind = "move" if line.get("kind") == "move" else "chat"
        game, turn = line.get("game", "?"), line.get("turn", "?")
        return {"from": who, "text": _text(line.get("text")), "kind": kind,
                "game": game if isinstance(game, (int, str)) else "?",
                "turn": turn if isinstance(turn, (int, str)) else "?"}
    except Exception:
        return {"from": "opponent", "text": "", "game": "?", "turn": "?", "kind": "chat"}


def clean_chat(chat, window=None):
    """The chat array as a list of clean lines; returns (lines, skipped). `skipped` = entries before the window."""
    if not isinstance(chat, (list, tuple)):
        return [], 0
    skipped = 0
    if window and len(chat) > window:
        skipped = len(chat) - window
        chat = chat[-window:]
    return [clean_line(x) for x in chat], skipped
