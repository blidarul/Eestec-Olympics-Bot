"""Layer 3, phase M3: reading the opponent.

Tools (catalog): opponent_predictor, reciprocity_policy (model-callable), profile_store (harness-only).
Plain data in, plain data out, stdlib only, no eval, no stdout. Opponent chat is never an input (rules 6.5, 6.7):
only action histories, which the game engine reports.
"""
import json
import os
import random
import re
import time

from solvers import catalog
from solvers.catalog import ToolError, ToolSpec

MAX_HIST = 200
MAX_ACTIONS = 30
DECAY = 0.9
LOW_SCORE = 0.2          # best decayed score below this -> equilibrium mix
MIN_ROUNDS = 3


# ------------------------------------------------------------------ utility model

def _utility(actions, payoff, beats):
    """u(a, b) in [-1, 1]: our payoff for our action a against opponent action b, or None if no model."""
    if payoff:
        flat = [abs(float(v)) for row in payoff for v in row]
        top = max(flat) or 1.0
        idx = {a: i for i, a in enumerate(actions)}

        def u(a, b):
            try:
                return float(payoff[idx[a]][idx[b]]) / top
            except (KeyError, IndexError, ValueError, TypeError):
                return 0.0
        return u
    if beats:
        def u(a, b):
            if a == b:
                return 0.0
            if b in beats.get(a, ()):
                return 1.0
            if a in beats.get(b, ()):
                return -1.0
            return 0.0
        return u
    return None


def _matrix_for(actions, u):
    return [[u(a, b) for b in actions] for a in actions]


def _best_response(actions, u, opp):
    return max(actions, key=lambda a: (u(a, opp), -actions.index(a)))


def _opp_response(actions, u, ours):
    """Zero-sum assumption: the opponent answers `ours` with the action minimising our utility."""
    return min(actions, key=lambda b: (u(ours, b), actions.index(b)))


# ------------------------------------------------------------------ predictors

def _pred_freq(opp, mine):
    if not opp:
        return None
    counts = {}
    for a in opp:
        counts[a] = counts.get(a, 0) + 1
    return max(counts, key=lambda a: (counts[a], -opp.index(a)))


def _pred_hist(k):
    def f(opp, mine):
        if len(opp) <= k:
            return None
        tail = opp[-k:]
        for i in range(len(opp) - k - 1, -1, -1):
            if opp[i:i + k] == tail:
                return opp[i + k]
        return None
    return f


def _pred_markov(opp, mine):
    n = min(len(opp), len(mine))
    if n < 2:
        return None
    key = (mine[n - 1], opp[n - 1])
    nxt = {}
    for i in range(n - 1):
        if (mine[i], opp[i]) == key:
            nxt[opp[i + 1]] = nxt.get(opp[i + 1], 0) + 1
    if not nxt:
        return None
    return max(nxt, key=lambda a: (nxt[a], a))


PREDICTORS = (("frequency", _pred_freq), ("history1", _pred_hist(1)), ("history2", _pred_hist(2)),
              ("history3", _pred_hist(3)), ("history4", _pred_hist(4)), ("markov_pair", _pred_markov))


def _strategy_action(actions, u, pred, meta):
    if pred is None:
        return None
    a = _best_response(actions, u, pred)
    if meta == 2:
        a = _best_response(actions, u, _opp_response(actions, u, a))
    return a


def _clean_list(x, label, allowed=None):
    if not isinstance(x, list):
        raise ToolError("%s must be a list" % label)
    out = [str(v).strip() for v in x][-MAX_HIST:]
    if allowed is not None and any(v not in allowed for v in out):
        bad = next(v for v in out if v not in allowed)
        raise ToolError("%s contains %r, which is not in actions" % (label, bad))
    return out


def predict(opp, mine, actions, u, seed=0, deadline=None):
    """Core of opponent_predictor. Returns the result dict (without 'explain')."""
    n = len(opp)
    # strategies = predictor x meta; score = decayed utility of what each would have played, per round
    scores = {}
    for pname, pf in PREDICTORS:
        for meta in (1, 2):
            tot = wsum = 0.0
            for t in range(n):
                if deadline is not None and time.monotonic() > deadline:
                    break
                w = DECAY ** (n - 1 - t)
                wsum += w
                a = _strategy_action(actions, u, pf(opp[:t], mine[:t]), meta)
                if a is not None:
                    tot += w * u(a, opp[t])
            scores[(pname, meta)] = tot / wsum if wsum else 0.0
    nxt = {}
    for pname, pf in PREDICTORS:
        p = pf(opp, mine)
        for meta in (1, 2):
            nxt[(pname, meta)] = (p, _strategy_action(actions, u, p, meta))
    ranked = sorted(((s, k) for k, s in scores.items() if nxt[k][1] is not None),
                    key=lambda sk: (-sk[0], [p for p, _ in PREDICTORS].index(sk[1][0]), sk[1][1]))
    best_score, best = ranked[0] if ranked else (0.0, None)
    uniform = {a: 1.0 / len(actions) for a in actions}
    if best is None or n < MIN_ROUNDS or best_score < LOW_SCORE:
        mix = _nash_mix(actions, u) or uniform
        rng = random.Random(seed * 1000003 + n)
        r, acc, pick = rng.random(), 0.0, actions[-1]
        for a in actions:
            acc += mix.get(a, 0.0)
            if r < acc:
                pick = a
                break
        return {"action": pick, "probs": {a: round(p, 4) for a, p in mix.items()}, "predictor": "equilibrium_mix",
                "confidence": 0.0, "predicted_opponent": None, "best_score": round(best_score, 3),
                "rounds": n, "source": "matrix_nash" if mix is not uniform else "uniform"}
    pred, act = nxt[best]
    probs = {a: 0.0 for a in actions}
    probs[act] = 1.0
    return {"action": act, "probs": probs, "predictor": "%s/%s" % (best[0], "counter" if best[1] == 1 else "counter2"),
            "confidence": round(max(0.0, min(1.0, best_score)), 3), "predicted_opponent": pred,
            "best_score": round(best_score, 3), "rounds": n, "source": "ensemble"}


def _nash_mix(actions, u):
    try:
        r = catalog.call("matrix_nash", {"matrix": [[str(round(u(a, b), 6)) for b in actions] for a in actions],
                                         "row_labels": [a[:40] for a in actions]}, time.monotonic() + 1.5)
        if not (r.get("ok") and isinstance(r.get("result"), dict)):
            return None
        probs = r["result"].get("row_probs")
        if not isinstance(probs, list) or len(probs) != len(actions):
            return None
        tot = sum(probs)
        return {a: float(p) / tot for a, p in zip(actions, probs)} if tot > 0 else None
    except Exception:  # noqa: BLE001
        return None


def opponent_predictor(args, deadline):
    actions = [str(a).strip() for a in args["actions"]]
    if len(set(actions)) != len(actions) or not (2 <= len(actions) <= MAX_ACTIONS):
        raise ToolError("actions must be 2..%d distinct names" % MAX_ACTIONS)
    payoff, beats = args.get("payoff"), args.get("beats")
    if payoff is not None and not (isinstance(payoff, list) and len(payoff) == len(actions)
                                   and all(isinstance(r, list) and len(r) == len(actions) for r in payoff)):
        raise ToolError("payoff must be a square matrix, one row and column per action")
    if beats is not None:
        if not isinstance(beats, dict):
            raise ToolError("beats must map an action to the list of actions it beats")
        beats = {str(k): [str(x) for x in v] for k, v in beats.items() if isinstance(v, list)}
    try:
        u = _utility(actions, payoff, beats)
    except (ValueError, TypeError):
        raise ToolError("payoff entries must be numbers")
    if u is None:
        raise ToolError("give a payoff matrix or a beats relation")
    opp = _clean_list(args.get("opponent_history", []), "opponent_history", set(actions))
    mine = _clean_list(args.get("my_history", []), "my_history", set(actions))
    n = min(len(opp), len(mine)) if mine else len(opp)
    opp = opp[-n:] if n else []
    mine = mine[-n:] if n and mine else []
    res = predict(opp, mine, actions, u, int(args.get("seed", 0) or 0), deadline)
    res["explain"] = ("Play %s (%s, confidence %.2f%s)." % (
        res["action"], res["predictor"], res["confidence"],
        ", opponent likely plays %s" % res["predicted_opponent"] if res["predicted_opponent"] else ""))
    return res


catalog.register(ToolSpec(
    name="opponent_predictor",
    summary="Simultaneous-move games: from the opponent's and our past actions and a payoff matrix (or a 'beats' relation), predict the opponent and recommend our action; falls back to the equilibrium mix when the opponent looks random.",
    params={"type": "object",
            "properties": {
                "actions": {"type": "array", "minItems": 2, "maxItems": MAX_ACTIONS, "items": {"type": "string", "maxLength": 40}},
                "opponent_history": {"type": "array", "maxItems": MAX_HIST, "items": {"type": "string", "maxLength": 40},
                                     "description": "opponent's past actions, oldest first"},
                "my_history": {"type": "array", "maxItems": MAX_HIST, "items": {"type": "string", "maxLength": 40},
                               "description": "our past actions in the same rounds, oldest first"},
                "payoff": {"type": "array", "maxItems": MAX_ACTIONS,
                           "items": {"type": "array", "maxItems": MAX_ACTIONS, "items": {"type": "number"}},
                           "description": "rows = our action, columns = opponent action, entries = our payoff, in the order of `actions`"},
                "beats": {"type": "object", "description": "action -> list of actions it beats (cyclic games); ties are all other pairs"},
                "seed": {"type": "integer"}},
            "required": ["actions", "opponent_history"]},
    fn=opponent_predictor, families=("read_opponent", "any"), model_callable=True, max_ms=2000))


# ------------------------------------------------------------------ reciprocity

def _coop(v, coop_label, defect_label):
    s = str(v).strip().lower()
    if s == str(defect_label).lower() or s.startswith(("d", "betray", "cheat", "steal", "refuse")):
        return False
    if s == str(coop_label).lower() or s.startswith(("c", "share", "trust", "honest", "split")):
        return True
    raise ToolError("cannot read %r as cooperate or defect" % s[:30])


def reciprocity_policy(args, deadline):
    cl = str(args.get("cooperate_label") or "cooperate")
    dl = str(args.get("defect_label") or "defect")
    opp = [_coop(v, cl, dl) for v in (args.get("opponent_history") or [])][-MAX_HIST:]
    mine = [_coop(v, cl, dl) for v in (args.get("my_history") or [])][-MAX_HIST:]
    n = len(opp)
    forgive = float(args.get("forgive_prob", 0.1))
    forgive = min(max(forgive, 0.0), 0.5)
    left = args.get("rounds_left")
    rng = random.Random(int(args.get("seed", 0) or 0) * 1000003 + n)
    rate = sum(opp) / n if n else 1.0
    recent = opp[-10:]
    rrate = sum(recent) / len(recent) if recent else 1.0
    p, why = 1.0, "start cooperative"
    if isinstance(left, int) and not isinstance(left, bool) and left == 1:
        p, why = 0.0, "last round of a known horizon: defect"
    elif n:
        streak = 0
        for c in reversed(opp):
            if c:
                break
            streak += 1
        if n >= 4 and (streak >= 4 or (n >= 6 and rrate <= 0.15)):
            p, why = 0.0, "persistent exploiter (%d defections in a row, rate %.2f): defect" % (streak, rrate)
        elif opp[-1]:
            p, why = 1.0, "opponent cooperated: reciprocate"
        else:
            p = min(0.4, forgive + 0.3 * rrate)
            why = "opponent defected: retaliate, forgive with p=%.2f" % p
    coop = rng.random() < p
    label = cl if coop else dl
    return {"action": label, "p_cooperate": round(p, 3), "opponent_cooperation_rate": round(rate, 3),
            "reason": why, "explain": "%s: %s (p_cooperate=%.2f)." % (label, why, p)}


catalog.register(ToolSpec(
    name="reciprocity_policy",
    summary="Repeated cooperate/defect games: next action from both histories (reciprocate, forgive sometimes, defect against persistent exploiters, defect on a known last round).",
    params={"type": "object",
            "properties": {
                "opponent_history": {"type": "array", "maxItems": MAX_HIST, "items": {"type": "string", "maxLength": 40}},
                "my_history": {"type": "array", "maxItems": MAX_HIST, "items": {"type": "string", "maxLength": 40}},
                "cooperate_label": {"type": "string", "maxLength": 40, "description": "default 'cooperate'; returned as the action name"},
                "defect_label": {"type": "string", "maxLength": 40, "description": "default 'defect'"},
                "rounds_left": {"type": "integer", "description": "rounds still to play including this one, only if the rules state the horizon"},
                "forgive_prob": {"type": "number"}, "seed": {"type": "integer"}},
            "required": ["opponent_history"]},
    fn=reciprocity_policy, families=("read_opponent", "any"), model_callable=True, max_ms=500))


# ------------------------------------------------------------------ profile store (harness-only)

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
_COUNTERS = ("games", "wins", "rounds", "coop_rounds", "showdowns", "bluff_shows", "actions", "aggressive_actions")


def _root(root=None):
    return root or os.path.join(os.environ.get("MEMORY_DIR", "/memory"), "opponents")


def _path(team, root=None):
    name = _SAFE.sub("_", str(team))[:64].strip(".") or "unknown"
    return os.path.join(_root(root), name + ".json")


def load_profile(team, root=None):
    """Profile dict (empty one when missing, partial or corrupt)."""
    try:
        with open(_path(team, root), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _merge(base, delta, family):
    out = dict(base) if isinstance(base, dict) else {}
    fam = out.get("families") if isinstance(out.get("families"), dict) else {}
    out["families"] = fam
    for k in _COUNTERS:
        v = delta.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100000:
            out[k] = int(out.get(k, 0) or 0) + int(v)
            if family:
                f = fam.get(family) if isinstance(fam.get(family), dict) else {}
                f[k] = int(f.get(k, 0) or 0) + int(v)
                fam[str(family)[:40]] = f
    return out


def update_profile(team, delta, family=None, root=None):
    """Merge `delta` counters into the team's file: re-read, add, write a temp file, os.replace (rule 5.14).
    Several containers may write at once, so the merge always starts from what is on disk. Returns the profile or None."""
    try:
        d = _root(root)
        os.makedirs(d, exist_ok=True)
        path = _path(team, root)
        lock = path + ".lock"
        got = False
        for _ in range(20):
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                got = True
                break
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(lock) > 5:
                        os.remove(lock)       # stale lock of a crashed writer
                        continue
                except OSError:
                    pass
                time.sleep(0.02)
            except OSError:
                break
        try:
            merged = _merge(load_profile(team, root), delta if isinstance(delta, dict) else {}, family)
            merged["team"] = str(team)[:64]
            tmp = "%s.%d.tmp" % (path, os.getpid())
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(merged, f)
            os.replace(tmp, path)
            return merged
        finally:
            if got:
                try:
                    os.remove(lock)
                except OSError:
                    pass
    except Exception:  # noqa: BLE001
        return None


def profile_summary(profile):
    """One short fact line from a profile, or None when there is not enough data."""
    if not isinstance(profile, dict):
        return None
    parts = []
    r, c = profile.get("rounds", 0), profile.get("coop_rounds", 0)
    if isinstance(r, int) and r >= 5:
        parts.append("cooperates %d%% of rounds" % round(100.0 * c / r))
    s, b = profile.get("showdowns", 0), profile.get("bluff_shows", 0)
    if isinstance(s, int) and s >= 3:
        parts.append("bluffs in %d%% of showdowns" % round(100.0 * b / s))
    a, g = profile.get("actions", 0), profile.get("aggressive_actions", 0)
    if isinstance(a, int) and a >= 10:
        parts.append("aggressive %d%% of actions" % round(100.0 * g / a))
    if not parts:
        return None
    return "Opponent profile (%s games): %s." % (profile.get("games", 0), ", ".join(parts))


def profile_store(args, deadline):
    op = args.get("op")
    team = args.get("team")
    if not isinstance(team, str) or not team:
        raise ToolError("team id required")
    root = args.get("root")
    if op == "load":
        p = load_profile(team, root)
        return {"profile": p, "summary": profile_summary(p), "explain": profile_summary(p) or "no profile data"}
    if op == "update":
        p = update_profile(team, args.get("delta") or {}, args.get("family"), root)
        if p is None:
            raise ToolError("could not write the profile")
        return {"profile": p, "explain": "profile updated"}
    raise ToolError("op must be load or update")


catalog.register(ToolSpec(
    name="profile_store",
    summary="Harness-only: load or merge-update /memory/opponents/<team>.json (cooperation rate, bluff shows, aggression per family).",
    params={"type": "object",
            "properties": {"op": {"type": "string", "enum": ["load", "update"]}, "team": {"type": "string", "maxLength": 64},
                           "delta": {"type": "object"}, "family": {"type": "string", "maxLength": 40},
                           "root": {"type": "string", "maxLength": 300}},
            "required": ["op", "team"]},
    fn=profile_store, families=("read_opponent", "any"), model_callable=False, max_ms=1000))
