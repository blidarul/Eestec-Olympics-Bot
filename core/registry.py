"""Router: which strategy plays this game. Explicit policy, first rule that holds wins.

 #  condition (artifacts from prep)                                      strategy                      tool
 1  family guessing + verified feedback model                            guessing/deduce               deduction
 2  perfect information + verified simulator, deterministic              think_ahead/search            alpha-beta (MCTS if too big)
 3  perfect information + verified simulator, chance                     think_ahead/search            MCTS
 4  family guardrails                                                    guardrails/* (mbappe)         model + chat defense
 5  family bluff | deals | read_opponent | truth | matrix_simultaneous    strategies/<family>/* (mbappe); matrix_simultaneous -> read_opponent
 6  anything else, or any tool above unverified / declining              core/generic                  model + playbook

A strategy found by a rule must also report matches() > THRESHOLD, else the next rule is tried. Any exception
inside a strategy falls back to core/generic in the worker (core/worker.py). Family names from prep/classifier.py are
mapped to the strategy families by FAMILY_ALIASES. BOT_FORCE_STRATEGY=<name> (tests, debugging) forces one strategy by
name ("generic" included) whatever the policy says.
Every turn logs family, strategy, tool and reason (core/worker.py -> main.py -> stderr and log.jsonl).
"""
import importlib
import os
import sys
import traceback
from dataclasses import dataclass

THRESHOLD = 0.5
FORCE_ENV = "BOT_FORCE_STRATEGY"
FAMILY_ALIASES = {"deduction": "guessing", "qa_guardrails": "guardrails", "cards_hidden": "bluff",
                  "negotiation": "deals"}
# prep family (after FAMILY_ALIASES) -> strategies/<folder>/ that plays it (rule 5 of the policy)
FAMILY_DIRS = {"bluff": "bluff", "deals": "deals", "read_opponent": "read_opponent", "truth": "truth",
               "matrix_simultaneous": "read_opponent"}


@dataclass
class Route:
    strategy: object
    reason: str
    family: str


def family_of(artifacts) -> str:
    raw = str((artifacts or {}).get("family") or "generic")
    return FAMILY_ALIASES.get(raw, raw)


def _candidates(root):
    for fam in sorted(os.listdir(root)):
        p = os.path.join(root, fam)
        if not os.path.isdir(p) or fam.startswith(("_", ".")):
            continue
        if os.path.isfile(os.path.join(p, "__init__.py")):
            yield fam, f"strategies.{fam}"
        for sub in sorted(os.listdir(p)):
            q = os.path.join(p, sub)
            if os.path.isdir(q) and not sub.startswith(("_", ".")) and os.path.isfile(os.path.join(q, "__init__.py")):
                yield fam, f"strategies.{fam}.{sub}"


def load_entries(root=None):
    """[(family_dir, strategy)] for every STRATEGY under strategies/. Import errors are logged and skipped."""
    root = root or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies")
    found = []
    try:
        mods = list(_candidates(root))
    except Exception:
        traceback.print_exc()
        return found
    for fam, m in mods:
        try:
            s = getattr(importlib.import_module(m), "STRATEGY", None)
            if s is not None:
                found.append((fam, s))
        except BaseException:
            print(f"registry: skipping {m}", file=sys.stderr)
            traceback.print_exc()
    return found


def load_all(root=None):
    return [s for _, s in load_entries(root)]


def _score(s, rules, artifacts) -> float:
    try:
        return float(s.matches(rules, artifacts))
    except Exception:
        traceback.print_exc()
        return 0.0


def _find(entries, rules, artifacts, name=None, fam_dir=None):
    """Best-scoring strategy with the given name or in the given strategies/<fam_dir>/, above THRESHOLD."""
    best, best_sc = None, THRESHOLD
    for fd, s in entries:
        if (name is not None and getattr(s, "name", None) != name) or (fam_dir is not None and fd != fam_dir):
            continue
        sc = _score(s, rules, artifacts)
        if sc > best_sc:
            best, best_sc = s, sc
    return best


def route(rules, artifacts, entries=None) -> Route:
    """Apply the policy table. `entries`: [(family_dir, strategy)] (default: scan strategies/)."""
    from core.generic import STRATEGY as generic
    art = artifacts if isinstance(artifacts, dict) else {}
    fam = family_of(art)
    entries = load_entries() if entries is None else entries
    forced = os.environ.get(FORCE_ENV)
    if forced:
        if forced == "generic":
            return Route(generic, f"forced by {FORCE_ENV}", fam)
        for _, s in entries:
            if getattr(s, "name", None) == forced:
                return Route(s, f"forced by {FORCE_ENV}", fam)
    cls = art.get("classification") if isinstance(art.get("classification"), dict) else {}
    sim = art.get("simulator") if isinstance(art.get("simulator"), dict) else {}
    prepared = art.get("prepared") if isinstance(art.get("prepared"), dict) else {}
    fm = prepared.get("deduce") if isinstance(prepared.get("deduce"), dict) else {}  # strategies/guessing/deduce.prepare()
    notes = []

    if fam == "guessing":
        if fm.get("verified"):
            s = _find(entries, rules, art, name="deduce")
            if s:
                return Route(s, "guessing family, feedback model verified", fam)
            notes.append("deduce declined")
        else:
            notes.append("feedback model unverified" + (f" ({fm['reason']})" if fm.get("reason") else ""))
    if sim.get("verified"):
        if cls.get("has_hidden_information") or cls.get("is_simultaneous"):
            notes.append("simulator verified but game has hidden information or simultaneous moves")
        else:
            s = _find(entries, rules, art, name="search")
            if s:
                kind = "chance" if sim.get("has_chance") else "deterministic"
                return Route(s, f"perfect information, simulator verified, {kind}", fam)
            notes.append("search declined")
    elif sim:
        notes.append("simulator unverified" + (f" ({sim['reason']})" if sim.get("reason") else ""))
    if fam == "guardrails":
        s = _find(entries, rules, art, fam_dir="guardrails")
        if s:
            return Route(s, "guardrails family", fam)
    if fam in FAMILY_DIRS:
        s = _find(entries, rules, art, fam_dir=FAMILY_DIRS[fam])
        if s:
            return Route(s, f"{fam} family -> strategies/{FAMILY_DIRS[fam]}", fam)
    return Route(generic, "generic: " + ("; ".join(notes) if notes else f"no specialised strategy for family {fam}"), fam)


def pick(rules, artifacts, strategies=None):
    """Compatibility: with an explicit list, the highest matches() above THRESHOLD wins (no policy); else route()."""
    if strategies is None:
        return route(rules, artifacts).strategy
    from core.generic import STRATEGY as generic
    best, best_score = generic, THRESHOLD
    for s in strategies:
        sc = _score(s, rules, artifacts)
        if sc > best_score:
            best, best_score = s, sc
    return best
