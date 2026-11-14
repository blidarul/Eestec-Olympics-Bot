"""Atomic, thread-safe, and process-safe serialization for shared /memory.
Owned by agent `bld`. Rule 5.14 compliant.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import tempfile
import time
from typing import Any


def sanitize_game_id(game_id: str) -> str:
    """Sanitize game identifier to a safe directory name."""
    return re.sub(r"[^a-z0-9_-]", "_", str(game_id).lower().strip())


def game_memory_dir(base_dir: str, game_id: str) -> str:
    """Get the game-specific directory in memory (Rule 5.14)."""
    return os.path.join(base_dir, sanitize_game_id(game_id))


def atomic_write_bytes(filepath: str, data: bytes) -> bool:
    """Atomically write binary data to a file by writing to a temporary file
    in the same directory and using os.replace to guarantee atomic replacement.
    Tolerates concurrent writers, creates parent directories if needed.
    """
    directory = os.path.dirname(os.path.abspath(filepath))
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        print(f"[optimization/serializer] failed to create dir {directory}: {exc}", file=sys.stderr)
        return False

    temp_path = None
    try:
        # Create temp file in the same directory to ensure atomic rename across filesystems
        fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_atom_", suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())

        os.replace(temp_path, filepath)
        return True
    except OSError as exc:
        print(f"[optimization/serializer] atomic write to {filepath} failed: {exc}", file=sys.stderr)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False


def atomic_save_json(filepath: str, obj: Any, indent: int | None = None) -> bool:
    """Atomically save JSON serializable object."""
    try:
        payload = json.dumps(obj, indent=indent, separators=(",", ":") if indent is None else None).encode("utf-8")
        return atomic_write_bytes(filepath, payload)
    except (TypeError, ValueError) as exc:
        print(f"[optimization/serializer] json serialization failed for {filepath}: {exc}", file=sys.stderr)
        return False


def load_json(filepath: str, default: Any = None) -> Any:
    """Safely load JSON file, returning default on missing, partial, or corrupt file."""
    if not os.path.isfile(filepath):
        return default
    try:
        with open(filepath, "rb") as fh:
            data = fh.read()
        if not data:
            return default
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        print(f"[optimization/serializer] failed reading json {filepath}: {exc}", file=sys.stderr)
        return default


def atomic_save_pickle(filepath: str, obj: Any) -> bool:
    """Atomically save arbitrary Python object using highest pickle protocol."""
    try:
        payload = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        return atomic_write_bytes(filepath, payload)
    except (pickle.PickleError, TypeError) as exc:
        print(f"[optimization/serializer] pickle serialization failed for {filepath}: {exc}", file=sys.stderr)
        return False


def load_pickle(filepath: str, default: Any = None) -> Any:
    """Safely load pickled file, returning default on missing, partial, or corrupt file."""
    if not os.path.isfile(filepath):
        return default
    try:
        with open(filepath, "rb") as fh:
            data = fh.read()
        if not data:
            return default
        return pickle.loads(data)
    except (OSError, pickle.PickleError, EOFError) as exc:
        print(f"[optimization/serializer] failed reading pickle {filepath}: {exc}", file=sys.stderr)
        return default
