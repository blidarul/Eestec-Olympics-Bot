"""Safe /memory access (5.14): atomic JSON writes, tolerant reads, append-only log.jsonl."""
import hashlib
import json
import os
import tempfile

BASE = os.environ.get("MEMORY_DIR", "/memory")


def game_dir(game_id, rules="", base=None):
    h = hashlib.sha1((rules or "").encode("utf-8", "replace")).hexdigest()[:12]
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(game_id))[:80] or "game"
    return os.path.join(base or BASE, safe, h)


def save_json(path, obj) -> bool:
    try:
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def append_log(directory, record) -> bool:
    """Append one JSON line to <directory>/log.jsonl (single small write; safe with several writers)."""
    try:
        os.makedirs(directory, exist_ok=True)
        line = json.dumps(record, default=str) + chr(10)
        with open(os.path.join(directory, "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(line)
        return True
    except Exception:
        return False


def update_opponent_chat_profile(opponent: str, chat_list: list, base: str = None) -> bool:
    """Track opponent chat behavior across match games in /memory/opponents/<name>.json (Rules 5.14, 6.5)."""
    if not opponent or not isinstance(chat_list, list):
        return False
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(opponent))[:60]
    if not safe_name:
        return False
    opp_dir = os.path.join(base or BASE, "opponents")
    path = os.path.join(opp_dir, f"{safe_name}.json")
    cur = load_json(path, {}) or {}

    opp_lines = [c.get("text", "") for c in chat_list if isinstance(c, dict) and c.get("from") == "opponent" and c.get("text")]
    total_lines = cur.get("total_lines", 0) + len(opp_lines)
    total_chars = cur.get("total_chars", 0) + sum(len(t) for t in opp_lines)
    matches_seen = cur.get("matches_seen", 0) + 1

    injections = cur.get("injection_indicators", 0)
    for t in opp_lines:
        t_l = t.lower()
        if any(kw in t_l for kw in ("ignore", "override", "system:", "instruction", "judge", "rule")):
            injections += 1

    cur.update({
        "opponent": opponent,
        "matches_seen": matches_seen,
        "total_lines": total_lines,
        "total_chars": total_chars,
        "avg_chars": int(total_chars / max(1, total_lines)),
        "injection_indicators": injections,
    })
    return save_json(path, cur)

