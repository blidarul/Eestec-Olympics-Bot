"""Hooks into prep/, optimization/ and chat/. WORKER PROCESS ONLY: the main process never imports this.

Every hook is in try/except; if prep/ or optimization/ is missing or raises we fall back to the
core minimal prep. Artifacts shape (what TurnState.artifacts holds, one dict per variant):
  {family, playbook, action_format{kind, regex, examples}, fallback_policy{prefer, avoid},
   chat_bank[], forbidden_terms[], grammar{...}, label}
"""
import contextlib
import os
import sys
import time
import traceback

from core import chatsafe, memory, registry
from core.llm import LLM

PREP_DEADLINE = 540.0
NEUTRAL_BANK = ["Your move.", "Go on.", "Playing.", "Next.", "Ready."]


def _log(*a):
    print(*a, file=sys.stderr, flush=True)


def _pause_gc():
    try:
        from optimization.budget import pause_gc
        return pause_gc()
    except Exception:
        return contextlib.nullcontext()


def _load_json(path, default=None):
    try:
        from optimization.serializer import load_json
        return load_json(path, default)
    except Exception:
        return memory.load_json(path, default)


def _default_artifacts(label="", rules=""):
    return {"label": label, "family": "generic", "playbook": "", "action_format": {"kind": "", "regex": None, "examples": []},
            "fallback_policy": {"prefer": [], "avoid": []}, "chat_bank": list(NEUTRAL_BANK), "forbidden_terms": []}


def map_engine_variant(vd: dict) -> dict:
    """Map one PrepEngine manifest variant (prep/engine.py) to the artifacts dict."""
    cls = vd.get("classification") or {}
    gr = vd.get("grammar") or {}
    heur = vd.get("heuristics") or {}
    opening = [str(x) for x in (heur.get("opening_moves") or [])]
    examples = [str(x) for x in (gr.get("discrete_actions") or [])][:6] or opening[:3]
    hints = heur.get("strategy_hints") or {}
    hint_txt = "; ".join(f"{k}: {v}" for k, v in hints.items() if isinstance(v, (str, int, float)))[:600]
    art = _default_artifacts(vd.get("label", ""))
    raw_family = cls.get("family") or heur.get("family") or "generic"
    art.update({
        "family": registry.FAMILY_ALIASES.get(raw_family, raw_family),  # strategy family name (core/registry.py)
        "prep_family": raw_family,
        "classification": {k: cls.get(k) for k in ("confidence", "is_deterministic", "has_hidden_information",
                                                   "is_simultaneous", "turn_structure")},
        "playbook": (f"Game family: {cls.get('family', 'generic')}. {hint_txt}").strip()[:900],
        "action_format": {"kind": gr.get("kind", ""), "regex": None, "examples": examples},
        "fallback_policy": {"prefer": opening, "avoid": []},
        "forbidden_terms": [str(x) for x in (gr.get("forbidden_keywords") or [])],
        "grammar": gr,
    })
    return art


def _core_prep_variant(llm: LLM, variant: dict) -> dict:
    """Minimal core prep: one model call (thinking enabled, 7.3). Game rules go only to the gateway."""
    art = _default_artifacts(variant.get("label", ""))
    sys_p = ("You prepare a bot for a two-player text game. Reply with compact JSON only: "
             '{"family": str, "playbook": "<=150 words of strategy", "action_format": {"regex": str, "examples": [str]}, '
             '"fallback_policy": {"prefer": [str], "avoid": [str]}, "chat_bank": [str <=100 chars, friendly], '
             '"forbidden_terms": [str]}')
    obj = llm.ask_json(sys_p, str(variant.get("rules", ""))[:12000], prep=True, timeout=60)
    if obj:
        try:
            fam = str(obj.get("family") or "generic").strip().lower()
            art["family"] = registry.FAMILY_ALIASES.get(fam, fam)
            art["playbook"] = str(obj.get("playbook") or "")[:900]
            af = obj.get("action_format") if isinstance(obj.get("action_format"), dict) else {}
            art["action_format"] = {"kind": "", "regex": af.get("regex") or None,
                                    "examples": [str(x) for x in (af.get("examples") or [])][:6]}
            fp = obj.get("fallback_policy") if isinstance(obj.get("fallback_policy"), dict) else {}
            art["fallback_policy"] = {"prefer": [str(x) for x in (fp.get("prefer") or [])][:10],
                                      "avoid": [str(x) for x in (fp.get("avoid") or [])][:10]}
            bank = [str(x)[:200] for x in (obj.get("chat_bank") or []) if str(x).strip()][:10]
            art["chat_bank"] = bank or art["chat_bank"]
            art["forbidden_terms"] = [str(x) for x in (obj.get("forbidden_terms") or [])][:20]
        except Exception:
            traceback.print_exc()
    return art


def run_prep(msg: dict, memory_dir: str | None = None) -> dict:
    """Return {"by_label": {label: artifacts}, "first": label}. Never raises."""
    t_start = time.monotonic()
    base = memory_dir or memory.BASE
    variants = [v for v in (msg.get("variants") or []) if isinstance(v, dict)]
    by_label = {}
    engine_ok = False
    try:
        from prep.engine import PrepEngine
        with _pause_gc():
            PrepEngine(base).run_prep(msg)
        manifest = _load_json(os.path.join(_engine_dir(base, msg.get("game_id", "unknown_game")), "manifest.json"), {})
        for vd in (manifest.get("variants") or []):
            if isinstance(vd, dict):
                by_label[str(vd.get("label", ""))] = map_engine_variant(vd)
        engine_ok = bool(by_label)
    except BaseException:  # missing, raises, or exits: core prep takes over
        traceback.print_exc()
    if not engine_ok:
        llm = LLM(msg.get("llm"))
        for v in variants:
            try:
                by_label[str(v.get("label", ""))] = _core_prep_variant(llm, v)
            except Exception:
                traceback.print_exc()
    for v in variants:  # ensure every variant has an entry
        by_label.setdefault(str(v.get("label", "")), _default_artifacts(str(v.get("label", ""))))
    try:
        _verify_simulators(msg, by_label, base, t_start)
    except BaseException:
        traceback.print_exc()
    try:
        _prepare_strategies(msg, by_label, base, t_start)
    except BaseException:
        traceback.print_exc()
    for v in variants:
        by_label[str(v.get("label", ""))]["rules_text_hash_dir"] = memory.game_dir(msg.get("game_id", ""), v.get("rules", ""), base)
        memory.save_json(os.path.join(memory.game_dir(msg.get("game_id", ""), v.get("rules", ""), base), "artifacts.json"),
                         by_label[str(v.get("label", ""))])
    first = str(variants[0].get("label", "")) if variants else ""
    return {"by_label": by_label, "first": first}


def _simulator_for(base, game_id, manifest, idx, variant):
    """Path of the simulator built for THIS variant. prep/ writes one simulator.py from the FIRST variant only, so it is
    offered to variant 0 only; a per-variant file (manifest variant "simulator_path", or simulator_<idx>.py) is used when
    it exists. Returns (path | None, reason)."""
    d = _engine_dir(base, game_id)
    mv = (manifest.get("variants") or []) if isinstance(manifest, dict) else []
    p = mv[idx].get("simulator_path") if idx < len(mv) and isinstance(mv[idx], dict) else None
    for cand in (p, os.path.join(d, f"simulator_{idx}.py"), os.path.join(d, "simulator.py") if idx == 0 else None):
        if cand and os.path.isfile(cand):
            return cand, ""
    if os.path.isfile(os.path.join(d, "simulator.py")):
        return None, "simulator.py was built from the first variant only"
    return None, "no simulator.py"


def _verify_simulators(msg, by_label, base, t_start):
    """artifacts["simulator"] = {path, verified, has_chance, reason, calibration} per variant (solvers/verify.py)."""
    game_id = msg.get("game_id", "unknown_game")
    manifest = _load_json(os.path.join(_engine_dir(base, game_id), "manifest.json"), {})
    calib = manifest.get("simulator_calibration") if isinstance(manifest, dict) else None
    for idx, v in enumerate(msg.get("variants") or []):
        if not isinstance(v, dict):
            continue
        art = by_label.get(str(v.get("label", "")))
        if art is None:
            continue
        path, why = _simulator_for(base, game_id, manifest, idx, v)
        res = {"path": path, "verified": False, "has_chance": False, "reason": why, "calibration": calib}
        try:
            if path:
                left = PREP_DEADLINE - 60 - (time.monotonic() - t_start)
                if left < 5:
                    res["reason"] = "no prep time left"
                else:
                    from solvers.verify import verify_isolated
                    out = verify_isolated(path, v, timeout=min(25.0, left))
                    res.update({k: out.get(k) for k in ("verified", "reason", "has_chance")})
        except BaseException as e:
            traceback.print_exc()
            res["reason"] = f"verify error {type(e).__name__}"
        art["simulator"] = res
        _log(f"[prep] simulator {v.get('label')!r}: verified={res['verified']} ({res['reason']})")


def _prepare_strategies(msg, by_label, base, t_start):
    """Optional Strategy.prepare(rules, variant, llm, deadline) of the strategies in the family's folder
    (strategies/<family>/*). Results go to artifacts["prepared"][<strategy name>]."""
    entries = registry.load_entries()
    llm = None
    try:
        llm = LLM(msg.get("llm"))
    except Exception:
        traceback.print_exc()
    deadline = t_start + PREP_DEADLINE - 90  # monotonic-based: this process started the prep clock
    for v in (msg.get("variants") or []):
        if not isinstance(v, dict):
            continue
        art = by_label.get(str(v.get("label", "")))
        if art is None:
            continue
        for fam_dir, strat in entries:
            fn = getattr(strat, "prepare", None)
            if not callable(fn) or fam_dir != art.get("family"):
                continue
            if time.monotonic() > deadline - 10:
                _log(f"[prep] no time left for {strat.name}.prepare")
                break
            try:
                variant = dict(v)
                variant["memory_dir"] = memory.game_dir(msg.get("game_id", ""), v.get("rules", ""), base)
                res = fn(str(v.get("rules", "")), variant, llm, deadline)
                if isinstance(res, dict):
                    art.setdefault("prepared", {})[getattr(strat, "name", fam_dir)] = res
                    _log(f"[prep] {strat.name}.prepare: verified={res.get('verified')} ({res.get('reason')})")
            except BaseException:
                traceback.print_exc()


def ready_line(rules, forbidden, seed) -> str:
    """The `ready` chat (6.8): chat.pipeline.ready_line (pure code, filtered, never empty) or the core's neutral line."""
    try:
        from chat.pipeline import ready_line as rl
        out = rl(rules, list(forbidden or []), str(seed))
        if isinstance(out, str) and out.strip():
            return out.strip()[:200]
    except BaseException:
        traceback.print_exc()
    return filter_out("Good luck, have fun!", forbidden)


def _engine_dir(base, game_id):
    try:
        from optimization.serializer import game_memory_dir
        return game_memory_dir(base, game_id)
    except Exception:
        return os.path.join(base, str(game_id))


def load_artifacts(game_id: str, rules: str, base: str | None = None) -> dict:
    d = _load_json(os.path.join(memory.game_dir(game_id, rules, base), "artifacts.json"), None)
    return d if isinstance(d, dict) else {}


# --- chat hooks (chat/ if it exposes them, else core/chatsafe.py) ---
def wrap_untrusted(lines) -> str:
    try:
        import chat
        f = getattr(chat, "wrap_untrusted", None)
        if callable(f):
            out = f(lines)
            if isinstance(out, str) and out:
                return out
    except Exception:
        traceback.print_exc()
    return chatsafe.wrap_untrusted(lines)


def filter_out(text, forbidden=None) -> str:
    try:
        import chat
        f = getattr(chat, "filter_out", None)
        if callable(f):
            out = f(text, forbidden)
            if isinstance(out, str) and out.strip():
                return out[:200]
    except Exception:
        traceback.print_exc()
    return chatsafe.filter_out(text, forbidden)
