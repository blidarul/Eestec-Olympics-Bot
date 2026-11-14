"""Safe /memory access (5.14). Minimal P2 version: P3 extends (log.jsonl etc.)."""
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
