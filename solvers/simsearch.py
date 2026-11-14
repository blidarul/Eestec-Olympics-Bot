"""Search on a verified simulator (layer 3, M6): alpha-beta when the game is small and deterministic, MCTS otherwise.

search_move(spec, observation, legal, seat, deadline, rng) -> dict | None, where `spec` is artifacts["simulator"]
({path, verified, has_chance, calibration}, set by core/hooks after solvers/verify). Library only, never raises,
no stdout. `proven` is True only for an exact alpha-beta win (deterministic game, perfect information, value >= 1).
Harness-only tools: `sim_search` (same thing, by simulator path) and `mdp_solve` (value iteration on an explicit table).
"""
import random
import sys
import time

from solvers import catalog, mcts, search
from solvers.catalog import ToolError, ToolSpec

AB_SHARE = 0.5          # share of the budget given to alpha-beta before MCTS takes over


def _log(msg):
    try:
        print("[simsearch] " + msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


class _Restricted:
    """Root move filter: at the root state only the arena-legal moves are considered."""

    def __init__(self, game, moves, root):
        self._g, self._moves, self._root = game, moves, root
        for n in ("to_move", "apply", "is_terminal", "score", "determinize", "has_chance"):
            if hasattr(game, n):
                setattr(self, n, getattr(game, n))

    def legal(self, s):
        return list(self._moves) if s is self._root else self._g.legal(s)


def search_move(spec, observation, legal, seat, deadline, rng=None):
    try:
        if not (isinstance(spec, dict) and spec.get("verified") and spec.get("path")):
            return None
        from solvers.adapter import load_simulator
        game = load_simulator(spec["path"])
        if not game.can_parse:
            return None
        s = game.parse(observation, seat if isinstance(seat, int) else 0)
        if game.is_terminal(s):
            return None
        if callable(getattr(game, "to_move", None)):
            seat = game.to_move(s)           # assist runs on our turn: the parsed state says who we are
        elif not isinstance(seat, int):
            seat = 0
        moves = game.legal(s)
        if isinstance(legal, list):
            allowed = {str(a) for a in legal}
            moves = [m for m in moves if m in allowed]
        if not moves:
            return None
        if len(moves) == 1:
            return {"move": moves[0], "proven": False, "share": 1.0, "why": "only legal move", "tool": "none"}
        t0 = time.monotonic()
        total = deadline - t0
        if total < 0.05:
            return None
        hidden = callable(getattr(game, "determinize", None))
        chance = bool(spec.get("has_chance"))
        if not chance and not hidden:
            r = search.search(game, s, seat, t0 + total * AB_SHARE)
            if r.action in moves and r.exact:
                win = r.value >= 1.0
                return {"move": r.action, "proven": bool(win), "share": 1.0, "value": r.value, "tool": "alpha-beta",
                        "why": "alpha-beta to terminal (value %g, depth %d, %d nodes)" % (r.value, r.depth, r.nodes)}
        left = deadline - time.monotonic()
        if left < 0.03:
            return None
        cap = mcts.sims_from_calibration(spec.get("calibration"), left)
        res = mcts.search(_Restricted(game, moves, s), s, seat, deadline, max_sims=cap, rng=rng or random.Random(0))
        if res.action not in moves:
            return None
        tot = sum(res.visits.values()) or 1
        share = res.visits.get(res.action, 0) / tot
        return {"move": res.action, "proven": False, "share": round(share, 3), "tool": "mcts",
                "why": "mcts %d simulations, branching %d" % (res.sims, len(moves))}
    except Exception as exc:  # noqa: BLE001
        _log("failed: %s: %s" % (type(exc).__name__, exc))
        return None


# ---------------------------------------------------------------- tools

def _sim_search(args, deadline):
    spec = {"path": args["path"], "verified": True, "has_chance": bool(args.get("has_chance")),
            "calibration": args.get("calibration")}
    r = search_move(spec, args["observation"], args.get("legal_actions"), args.get("seat", 0), deadline,
                    random.Random(0))
    if r is None:
        raise ToolError("no search result (simulator cannot parse this observation)")
    return dict(r, explain=r["why"])


def _mdp_solve(args, deadline):
    from solvers import mdp
    table = args["table"]
    if not isinstance(table, dict) or not table:
        raise ToolError("table must map state -> {action: [[p, next_state, reward], ...]}")

    def acts(s):
        return list(table.get(s, {}).keys())

    def trans(s, a):
        return [(p, s2, r) for p, s2, r in table[s][a]]

    res = mdp.solve(args["start"], acts, trans, float(args.get("discount", 1.0)), deadline, max_states=5000)
    if res is None:
        raise ToolError("too many states or out of time")
    s0 = args["start"]
    return {"value": res.values.get(s0, 0.0), "action": res.policy.get(s0), "iterations": res.iterations,
            "converged": res.converged, "states": res.states,
            "explain": "value iteration, %d states, %d sweeps" % (res.states, res.iterations)}


catalog.register(ToolSpec(
    name="sim_search", summary="Alpha-beta or MCTS on a verified simulator file (harness-only).",
    params={"type": "object", "properties": {
        "path": {"type": "string"}, "observation": {"type": "string"},
        "legal_actions": {"type": "array", "items": {"type": "string"}},
        "seat": {"type": "integer"}, "has_chance": {"type": "boolean"}, "calibration": {"type": "object"}},
        "required": ["path", "observation"]},
    fn=_sim_search, families=("think_ahead",), model_callable=False, max_ms=6000))

catalog.register(ToolSpec(
    name="mdp_solve", summary="Value iteration on an explicit MDP table (harness-only).",
    params={"type": "object", "properties": {
        "table": {"type": "object"}, "start": {"type": "string"}, "discount": {"type": "number"}},
        "required": ["table", "start"]},
    fn=_mdp_solve, families=("any",), model_callable=False, max_ms=2000))
