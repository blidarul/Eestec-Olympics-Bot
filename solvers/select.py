"""Layer 2, phase L2: choose which model-callable tools to offer for one turn.

select_tools(artifacts, observation, rules, facts, limit=6) -> list of tool names

Library only (no core/prep/chat/strategies imports). Deterministic, never raises. The opponent's chat is not an
input, so it cannot change the choice (rules 6.5, 6.7). The reason for each name goes to stderr.

Order: (1) tools whose detector fired in precompute and whose result is NOT already fully given as a fact,
(2) keyword hints from the rules/observation, (3) tools of the artifacts family, (4) general ("any") tools in a
fixed priority order. Detector tools whose answer is already in the facts are dropped, except in PARTIAL, where
the model may still ask a different question (board_lines on a hypothetical position).
"""
import re
import sys

import solvers  # noqa: F401  (registers the tools)
from solvers import catalog

PARTIAL = {"board_lines"}

# keyword in rules/observation -> tools worth offering
HINTS = (
    (r"\b(dice|die|roll|d\d+)\b", ("dice_sum_distribution", "binomial_tail", "expected_value")),
    (r"\b(card|hand|deck|poker)\b", ("count_hands", "hypergeometric", "extract_cards")),
    (r"\b(probabilit|chance|odds|bayes)", ("bayes_update", "binomial_tail", "expected_value")),
    (r"\b(graph|node|edge|path|route|maze)\b", ("graph_shortest_path", "grid_bfs")),
    (r"\b(grid|board|cell|row|column)\b", ("extract_grid", "grid_bfs")),
    (r"\b(payoff|simultaneous|matrix)\b", ("matrix_nash", "best_response")),
    (r"\b(simultaneous(ly)?|at the same time|rock|paper|scissors)\b", ("opponent_predictor",)),
    (r"\b(cooperat\w*|defect\w*|betray\w*|prisoner)", ("reciprocity_policy",)),
    (r"\b(heap|pile|nim)\b", ("nim_analysis",)),
    (r"\b(guess|higher|lower|secret)\b", ("binary_search_next", "deduce_next", "extract_history")),
    (r"\b(pegs?|bulls?|cows?|mastermind|wordle|green|yellow|digits?|letters?)\b", ("deduce_next", "extract_history")),
)

GENERAL_ORDER = ("expected_value", "best_option", "combinatorics", "bayes_update", "extract_numbers",
                 "binomial_tail", "hypergeometric", "dice_sum_distribution", "matrix_nash", "best_response",
                 "graph_shortest_path", "extract_grid", "extract_history", "extract_cards", "nim_analysis",
                 "opponent_predictor", "reciprocity_policy", "sample_action", "count_hands", "abstain_threshold", "graph_reachable", "graph_topo_sort",
                 "graph_components", "graph_dfs_order", "deduce_next")


def _log(msg):
    try:
        print("[select] " + msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def select_tools(artifacts, observation, rules, facts, limit=6):
    try:
        limit = max(0, min(int(limit), 6))
    except Exception:  # noqa: BLE001
        limit = 6
    try:
        art = artifacts if isinstance(artifacts, dict) else {}
        fam = art.get("family") or art.get("prep_family")
        fam = fam if isinstance(fam, str) else None
        callable_ = [s.name for s in catalog.list_tools(model_callable=True)]
        ok = set(callable_)
        text = ("%s\n%s" % (rules if isinstance(rules, str) else "",
                            observation if isinstance(observation, str) else ""))[:20000].lower()
        used = list(getattr(facts, "used", None) or [])

        chosen, why = [], {}

        def add(name, reason):
            if name in ok and name not in chosen and len(chosen) < limit:
                chosen.append(name)
                why[name] = reason

        for n in used:
            if n in PARTIAL:
                add(n, "detector fired, partial answer in facts")
        for rx, names in HINTS:
            if re.search(rx, text):
                for n in names:
                    if n not in used:
                        add(n, "keyword hint")
        if fam and fam != "generic":
            for s in catalog.list_tools(family=fam, model_callable=True):
                if fam in s.families and n_ok(s, used):
                    add(s.name, "family " + fam)
        for n in GENERAL_ORDER:
            if n not in used:
                add(n, "general")
        for n in callable_:  # tools missing from GENERAL_ORDER
            if n not in used and "any" in _fams(n):
                add(n, "general")
        for n in chosen:
            _log("%s: %s" % (n, why[n]))
        return chosen
    except Exception as e:  # noqa: BLE001
        _log("error: %r" % (e,))
        return []


def _fams(name):
    for s in catalog.list_tools():
        if s.name == name:
            return s.families
    return ()


def n_ok(spec, used):
    return spec.name not in used or spec.name in PARTIAL
