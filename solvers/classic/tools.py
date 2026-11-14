"""Catalog entries for the classic solvers (harness-only: inputs are whole observations, not model-fillable)."""
import time

from solvers import catalog
from solvers.catalog import ToolError, ToolSpec
from solvers import classic

_FAMILY = {"kinrow": ("think_ahead",), "subtraction": ("think_ahead",), "dice_race": ("any",),
           "range_guess": ("guessing",), "battleship": ("think_ahead", "guessing"), "kuhn": ("bluff",),
           "pegs": ("guessing",)}
_SUMMARY = {
    "kinrow": "k-in-a-row on any board size, optional gravity: exact search when few cells are empty, else win/block/double-threat rules.",
    "subtraction": "Heaps with an allowed-removal set, normal or misere: Grundy values and the winning move.",
    "dice_race": "Roll/hold race to a target: exact table for the common target, rule of thumb otherwise.",
    "range_guess": "Plain numeric guessing with higher/lower feedback: binary search.",
    "battleship": "Hidden-ship grid shooting: probability density over remaining ship placements, hunt then target.",
    "kuhn": "3-card one-bet poker: equilibrium action table (mixed actions sampled with a seed, dominant ones proven).",
    "pegs": "Code-breaking with exact/partial feedback: entropy guess over the consistent candidates.",
}
_PARAMS = {"type": "object",
           "properties": {"rules": {"type": "string", "maxLength": 20000},
                          "observation": {"type": "string", "maxLength": 12000},
                          "legal_actions": {"type": ["array", "null"], "maxItems": 200, "items": {"type": "string"}}},
           "required": ["rules", "observation"]}


def _make(name):
    def fn(args, deadline):
        s = classic.REGISTRY[name]
        params = s.detect(args["rules"], {})
        if not params:
            raise ToolError("rules do not look like %s" % name)
        legal = args.get("legal_actions")
        if not s.verify(params, {"observation": args["observation"], "legal_actions": legal}):
            raise ToolError("observation does not match the %s model" % name)
        r = s.solve(args["observation"], legal, params, deadline)
        return {"params": {k: v for k, v in params.items() if not k.startswith("_")}, "move": r.get("move"),
                "value": r.get("value"), "why": r.get("why"), "proven": bool(r.get("proven")),
                "explain": str(r.get("why"))}
    return fn


for _n in ("kinrow", "subtraction", "dice_race", "range_guess", "battleship", "kuhn", "pegs"):
    catalog.register(ToolSpec(name=_n + "_solve", summary=_SUMMARY[_n], params=_PARAMS, fn=_make(_n),
                              families=_FAMILY[_n], model_callable=False, max_ms=2000))
