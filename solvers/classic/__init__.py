"""Classic solvers: exact or near-exact play for well-known game structures, found by detect() + verify().

Contract (layer 3, M2): detect(rules, variant) -> params | None (conservative), verify(params, sample_turn) -> bool
(legal moves of a real observation match the model), solve(observation, legal, params, deadline) ->
{"move", "value", "why", "proven"}. Library only: no core/prep/chat imports, no stdout, never raises out of run().
"""
import hashlib
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class ClassicSolver:
    name: str
    detect: Callable
    verify: Callable
    solve: Callable


REGISTRY = {}
_VERIFIED = {}          # (rules hash, solver name) -> bool, so a rules text is verified once


def register(s):
    REGISTRY[s.name] = s
    return s


def _log(msg):
    try:
        print("[classic] " + msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def run(observation, legal, rules, variant, deadline, skip=()):
    """Run every detected+verified solver on one turn. Returns a list of
    {"solver", "move", "value", "why", "proven"} (never raises, never prints to stdout)."""
    out = []
    variant = variant if isinstance(variant, dict) else {}
    for name, s in REGISTRY.items():
        if name in skip or time.monotonic() >= deadline:
            continue
        try:
            params = s.detect(rules, variant)
            if not params:
                continue
            key = (hashlib.sha1((rules or "").encode("utf-8", "replace")).hexdigest(), name)
            sample = {"observation": observation, "legal_actions": legal}
            ok = _VERIFIED.get(key)
            if ok is None or (ok is False and legal):
                ok = bool(s.verify(params, sample))
                _VERIFIED[key] = ok
            if not ok:
                continue
            r = s.solve(observation, legal, params, deadline)
            if isinstance(r, dict) and r.get("move") is not None or isinstance(r, dict) and r.get("why"):
                r = dict(r)
                r["solver"] = name
                out.append(r)
        except Exception as exc:  # noqa: BLE001
            _log("%s failed: %s: %s" % (name, type(exc).__name__, exc))
    return out


from solvers.classic import kinrow, subtraction, dice_race, range_guess, battleship, kuhn, pegs  # noqa: E402,F401
