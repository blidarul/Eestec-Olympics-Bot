"""Pick a strategy: scan strategies/*/ and strategies/*/*/ for STRATEGY; best matches() > 0.5 else generic."""
import importlib
import os
import sys
import traceback

THRESHOLD = 0.5


def _candidates(root):
    for fam in sorted(os.listdir(root)):
        p = os.path.join(root, fam)
        if not os.path.isdir(p) or fam.startswith(("_", ".")):
            continue
        if os.path.isfile(os.path.join(p, "__init__.py")):
            yield f"strategies.{fam}"
        for sub in sorted(os.listdir(p)):
            q = os.path.join(p, sub)
            if os.path.isdir(q) and not sub.startswith(("_", ".")) and os.path.isfile(os.path.join(q, "__init__.py")):
                yield f"strategies.{fam}.{sub}"


def load_all(root=None):
    root = root or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies")
    found = []
    try:
        mods = list(_candidates(root))
    except Exception:
        traceback.print_exc()
        return found
    for m in mods:
        try:
            s = getattr(importlib.import_module(m), "STRATEGY", None)
            if s is not None:
                found.append(s)
        except BaseException:
            print(f"registry: skipping {m}", file=sys.stderr)
            traceback.print_exc()
    return found


def pick(rules, artifacts, strategies=None):
    from core.generic import STRATEGY as generic
    best, best_score = generic, THRESHOLD
    for s in (load_all() if strategies is None else strategies):
        try:
            sc = float(s.matches(rules, artifacts))
        except Exception:
            traceback.print_exc()
            continue
        if sc > best_score:
            best, best_score = s, sc
    return best
