"""Team-level chat state, recomputed from the whole match conversation (rule 6.1).

Every `start`, `turn` and `end` carries the whole match chat, oldest first, and "you" means the TEAM: lines said by
our other containers are in it too. So the counters that cap our pressure lines, the no-repeat memory and the spacing
are read from that history on every call instead of being kept per process.

Input lines: {"from": "you"|"opponent", "text": str}, optionally "game" (int) and "kind" ("chat"|"move").
Our lines are matched to the concession banks by normalized text.
"""
import re

from . import concede


def norm(text):
    return re.sub(r"[^\w]+", " ", str(text or "").lower()).strip()


_CONCEDE = None


def _concede_set():
    global _CONCEDE
    if _CONCEDE is None:
        _CONCEDE = {norm(line) for _s, line in concede.all_lines()}
    return _CONCEDE


def our_lines(chat_full):
    """[(text, game or None)] of OUR chat lines (kind "chat" or no kind), oldest first. Never raises."""
    out = []
    try:
        for c in chat_full or []:
            if not isinstance(c, dict) or c.get("from") != "you" or c.get("kind") == "move":
                continue
            t = c.get("text")
            if isinstance(t, str) and t.strip():
                g = c.get("game")
                out.append((t.strip(), g if isinstance(g, int) else None))
    except Exception:
        pass
    return out


def summarize(chat_full, game=None):
    """What the history says about us: lines, concede counts (match, game), the lines used, spacing since the last one.
    `game`: the current game number (only used when the lines carry a "game" field; otherwise the game count is
    the match count, the strictest reading)."""
    ours = our_lines(chat_full)
    cset = _concede_set()
    # a concession line may be followed by an action sentence ("Concede. Pressing on."): match the bank line as a prefix
    def bank_line(text):
        n = norm(text)
        return next((b for b in cset if n == b or n.startswith(b + " ")), None)
    hits = {i: bank_line(t) for i, (t, _g) in enumerate(ours)}
    idx = [i for i, b in hits.items() if b]
    in_game = [i for i in idx if game is None or ours[i][1] is None or ours[i][1] == game]
    pool = in_game if game is not None and any(ours[j][1] is not None for j in idx) else idx
    # `used` holds bank lines in their original spelling (concede.pick compares with the bank text)
    originals = {norm(l): l for _s, l in concede.all_lines()}
    used = {originals[hits[i]] for i in pool}
    return {"lines": [t for t, _g in ours], "count_match": len(idx), "count_game": len(in_game), "used": used,
            "our_turns": len(ours), "last_use": (idx[-1] + 1) if idx else None}


def apply_to(defense, chat_full, game=None):
    """Overwrite the per-process counters of a ChatDefense with the team-level numbers of the history."""
    s = summarize(chat_full, game)
    if not s["lines"] and not chat_full:
        return s
    lim = defense.limiter
    lim.match, lim.game, lim.used = s["count_match"], s["count_game"], set(s["used"])
    lim.our_turn, lim.last_use = s["our_turns"], s["last_use"]
    defense.recent.clear()
    defense.recent.extend(s["lines"][-defense.recent.maxlen:])
    defense.said.clear()
    defense.said.extend(s["lines"][-defense.said.maxlen:])
    return s
