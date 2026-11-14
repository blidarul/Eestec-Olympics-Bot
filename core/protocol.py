"""Protocol output: one JSON object per line on the REAL stdout, flushed. Logs go to stderr."""
import json
import os
import sys

_out = None


def setup_stdio():
    """Keep the real stdout for protocol lines; point fd 1 (and sys.stdout) at stderr so that
    no library print, and no child process, can corrupt the protocol (5.1)."""
    global _out
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    _out = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    os.dup2(2, 1)
    sys.stdout = sys.stderr


def send(obj) -> None:
    out = _out if _out is not None else sys.__stdout__
    out.write(json.dumps(obj) + "\n")
    out.flush()


def log(*parts) -> None:
    try:
        print(*parts, file=sys.stderr, flush=True)
    except Exception:
        pass


def clean_chat(text) -> str:
    text = " ".join(str(text or "").split())[:200].strip()
    return text
