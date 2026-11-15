"""AI Harness Arena bot: protocol loop. Never exits except on `shutdown` or EOF on stdin.

The main process imports nothing from strategies/, prep/, chat/: strategy work happens in a
worker process (core/worker.py) with a hard deadline, backed by core/fallback.py.
"""
import json
import sys
import time
import traceback

from core import actionfmt, fallback, forbidden, memory, protocol, validate, worker

PREP_DEADLINE = 540.0  # arena gives 600 s
START_DEADLINE = 2.0  # arena gives 30 s (120 cold)
COLD_PREP_CAP = 60.0  # code-only prep at a cold start (rule 4.3)
TURN_DEADLINE = 12.0  # arena gives 20 s
START_CHAT = "Ready."

STATE = {"llm": None, "game": {}, "artifacts": {}, "prep": None, "my_actions": [], "prev_obs": ""}


def use_llm(msg):
    info = msg.get("llm")
    if isinstance(info, dict) and info.get("api_key"):
        STATE["llm"] = info  # always the latest (7.2)


def chat_texts(chat):
    out = []
    for c in chat or []:
        if isinstance(c, dict) and c.get("text") and c.get("from") != "you":
            out.append(str(c["text"]))
    return out


def chat_full(chat):
    """[{"from", "text", "game", "kind"}] of the chat of the turn, untrusted, latest last (strings only, bounded)."""
    out = []
    for c in chat or []:
        if isinstance(c, dict) and c.get("text"):
            item = {"from": str(c.get("from", "?"))[:20], "text": str(c["text"])[:300]}
            if "game" in c and isinstance(c["game"], int):
                item["game"] = c["game"]
            if "kind" in c:
                item["kind"] = str(c.get("kind", "chat"))[:20]
            elif "type" in c:
                item["kind"] = str(c.get("type", "chat"))[:20]
            out.append(item)
    return out[-20:]


def new_lines(obs, prev):
    """Observation lines that were not in the previous observation (what happened since our last action)."""
    seen = {l.strip() for l in prev.splitlines() if l.strip()}
    return [l.strip()[:200] for l in obs.splitlines() if l.strip() and l.strip() not in seen][:12]


def on_prep(msg, wk):
    use_llm(msg)
    try:  # specialise inside the worker (prep/, optimization/ never imported here); 540 s hard deadline
        ans = wk.ask({"kind": "prep", "msg": msg}, PREP_DEADLINE)
        res = ans.get("prep") if isinstance(ans, dict) else None
        if isinstance(res, dict) and isinstance(res.get("by_label"), dict):
            STATE["prep"] = {
                "game_id": str(msg.get("game_id", "")),
                "by_label": res.get("by_label"),
                "first": res.get("first", ""),
            }
    except Exception:
        traceback.print_exc()
    protocol.send({"type": "ready"})


def pick_artifacts(msg, wk):
    game_id = str(msg.get("game_id", ""))
    rules = str(msg.get("rules", ""))
    raw_var = msg.get("variant")
    if isinstance(raw_var, dict):
        label = str(raw_var.get("label", ""))
    elif isinstance(raw_var, str):
        label = raw_var
    else:
        label = ""

    prep = STATE.get("prep") or {}
    same_game = bool(prep.get("game_id") and prep.get("game_id") == game_id)
    by = prep.get("by_label") or {} if same_game else {}

    # 1. Exact variant match from prep
    art = by.get(label) if (label and by) else None

    # 1b. Case-insensitive / normalized variant match from prep
    if not art and by and label:
        norm_l = label.strip().lower()
        for k, v in by.items():
            if k.strip().lower() == norm_l or norm_l in k.strip().lower():
                art = v
                break

    # 2. If not found in in-memory prep, try /memory by game_id and rules
    if not art:
        ans = wk.ask({"kind": "load", "game_id": game_id, "rules": rules}, 1.0)
        art = ans.get("artifacts") if isinstance(ans, dict) else None

    # 3. If still not found, only default to prep's first variant IF it was the same game
    if not art and same_game and by:
        art = by.get(prep.get("first", ""))

    return art if isinstance(art, dict) else {}


def light_artifacts(msg):
    """Last resort for a cold container when the code-only prep returned nothing: parse family and action grammar from the rules."""
    rules = str(msg.get("rules", ""))
    raw_var = msg.get("variant")
    label = str(raw_var.get("label", "")) if isinstance(raw_var, dict) else (raw_var if isinstance(raw_var, str) else "")
    art = None
    if rules:
        try:
            from prep.action_parser import parse_action_grammar
            from prep.classifier import classify_rules
            from core.hooks import map_engine_variant
            cls = classify_rules(rules)
            gr = parse_action_grammar(rules)
            art = map_engine_variant({
                "label": label or "default",
                "classification": cls.to_dict(),
                "grammar": gr.to_dict(),
                "heuristics": {"family": cls.family},
            })
        except Exception:
            traceback.print_exc()
    return art if isinstance(art, dict) else {}


def cold_prep(msg, wk):
    """No artifacts at `start` (cold container, rule 4.3): run the code-only part of prep on start.rules inside the worker, at most
    COLD_PREP_CAP s and never more than half of the study clock the arena announces, then route like a warm container."""
    try:
        study = float(msg.get("study_seconds") or 30.0)
    except (TypeError, ValueError):
        study = 30.0
    cap = min(COLD_PREP_CAP, 0.5 * study)
    if cap < 5.0 or not str(msg.get("rules", "")).strip():
        return {}
    ans = wk.ask({"kind": "cold", "msg": msg, "budget": cap}, cap)
    art = ans.get("artifacts") if isinstance(ans, dict) else None
    return art if isinstance(art, dict) and art else {}


def on_start(msg, wk):
    t0 = time.monotonic()
    use_llm(msg)
    STATE["game"] = msg
    try:
        STATE["artifacts"] = pick_artifacts(msg, wk)
        if not STATE["artifacts"]:
            STATE["artifacts"] = cold_prep(msg, wk) or light_artifacts(msg)
            t0 = time.monotonic()  # the ready line gets its own fresh budget
    except Exception:
        traceback.print_exc()
        STATE["artifacts"] = {}
    STATE["my_actions"], STATE["prev_obs"] = [], ""
    ensure_action_template(STATE["artifacts"], msg)
    ensure_forbidden_terms(STATE["artifacts"], msg)
    terms0 = STATE["artifacts"].get("forbidden_terms") or []
    chat = None
    try:  # chat.pipeline.ready_line in the worker (pure code, filtered, never empty); main keeps the 2 s start clock
        ans = wk.ask({"kind": "ready_line", "rules": msg.get("rules", ""), "forbidden": terms0,
                      "seed": str(msg.get("match_id", ""))}, max(0.2, START_DEADLINE - 0.3 - (time.monotonic() - t0)))
        line = ans.get("line") if isinstance(ans, dict) else None
        chat = line if isinstance(line, str) and line.strip() else None
    except Exception:
        traceback.print_exc()
    if chat is None:
        chat = fallback.fallback_chat(STATE["artifacts"]) if STATE["artifacts"].get("chat_bank") else START_CHAT
        chat = wk_filter(chat, terms0)
    chat = clean_line(protocol.clean_chat(chat) or fallback.NEUTRAL_CHAT, forbidden_terms_of(STATE["artifacts"]), STATE["artifacts"])
    protocol.send({"type": "ready", "chat": chat})


def ensure_action_template(art, msg):
    """Prep normally stores the template; if it is missing (prep failed, artifacts lost) parse it from the rules now."""
    try:
        af = art.get("action_format") if isinstance(art.get("action_format"), dict) else {}
        if not actionfmt.has_template(af):
            parsed = actionfmt.parse_template(str(msg.get("rules", "")))
            if parsed:
                af = dict(af)
                af.update({"template": parsed["template"], "regex": parsed["regex"],
                           "placeholders": parsed["placeholders"], "templates": parsed["templates"]})
                art["action_format"] = af
    except Exception:
        traceback.print_exc()


def forbidden_terms_of(art):
    return (art or {}).get("forbidden_terms") or []


def ensure_forbidden_terms(art, msg):
    """Terms the rules name (code-side extraction) are always in the artifacts, whatever prep produced (6.8, 6.9)."""
    try:
        rules = str(msg.get("rules", ""))
        have = art.get("forbidden_terms") or []
        base = forbidden.extract_terms(rules)
        if base and any(forbidden.contains(t, have) is None for t in base):
            art["forbidden_base"] = base
            art["forbidden_terms"] = forbidden.merge(rules, have)
    except Exception:
        traceback.print_exc()


def clean_line(chat, terms, art=None):
    """Chat that still hits a forbidden term (leetspeak, plural, spaced letters) is replaced by a clean bank line, never emptied."""
    try:
        if not terms or not forbidden.contains(chat, terms):
            return chat
        bank = [str(b) for b in ((art or {}).get("chat_bank") or [])] + [fallback.NEUTRAL_CHAT, START_CHAT, "Proceed.", "Standing by."]
        return next((b for b in bank if b.strip() and not forbidden.contains(b, terms)), fallback.NEUTRAL_CHAT)
    except Exception:
        return fallback.NEUTRAL_CHAT


def wk_filter(text, forbidden):
    """Main-process speech and forbidden-term cut (delegates to chat.filter_out, fallback chatsafe)."""
    try:
        from core import hooks
        res = hooks.filter_out(text, forbidden)
        if res and isinstance(res, str) and res.strip():
            return res
    except Exception:
        pass
    try:
        from core import chatsafe
        return chatsafe.filter_out(text, forbidden, default=fallback.NEUTRAL_CHAT)
    except Exception:
        return text


def on_turn(msg, wk):
    t0 = time.monotonic()
    source, model_error, meta = "fallback", None, {}
    art = STATE["artifacts"]
    if art.get("cold_prep") and not art.get("cold_verified"):  # cold container: verify the simulator on the first real turn
        try:
            ans = wk.ask({"kind": "cold_verify", "artifacts": art, "game": STATE["game"],
                          "turn": {"observation": msg.get("observation"), "legal_actions": msg.get("legal_actions")}}, 6.0)
            new = ans.get("artifacts") if isinstance(ans, dict) else None
            art = STATE["artifacts"] = new if isinstance(new, dict) and new else dict(art, cold_verified=True)
        except Exception:
            traceback.print_exc()
            art["cold_verified"] = True
    legal = msg.get("legal_actions")
    warning = msg.get("warning") if isinstance(msg.get("warning"), dict) else None
    mine = STATE["my_actions"]
    if warning and mine:
        mine.pop()  # the turn is re-sent after a rejected answer: that answer does not count as played
    obs = str(msg.get("observation", ""))
    rules_text = str(STATE["game"].get("rules", ""))
    is_blotto_game = "blotto" in rules_text.lower() or "battlefield" in rules_text.lower() or "soldiers this round:" in obs.lower()
    guessing = not is_blotto_game and (
        art.get("family") in ("guessing", "deduction", "word", "wordle")
        or art.get("prep_family") in ("guessing", "deduction", "word", "wordle")
        or (art.get("grammar") or {}).get("kind") in ("word", "numeric_range")
    )
    previous = list(mine) if guessing else []  # guessing / word games: never send the same action twice (safety net)
    # fallback FIRST, from the message alone
    use_fmt = not (isinstance(legal, list) and legal)  # legal_actions null/empty: the rules' template is the only guard
    fmt = actionfmt.from_artifacts(art, warning) if use_fmt else None
    opp_chat_now = chat_texts(msg.get("chat"))
    fb_action, fb_chat = fallback.fallback_decision(msg, art, previous, rules=rules_text, opponent_chat=opp_chat_now)
    action, chat = fb_action, fb_chat
    try:
        limit = min(TURN_DEADLINE, 0.6 * float(msg.get("seconds") or 20))
        game = STATE["game"]
        req = {"state": {
            "game_id": str(game.get("game_id", "")), "rules": str(game.get("rules", "")),
            "variant": game.get("variant") or {}, "seat": int(game.get("seat", 0) or 0),
            "observation": obs,
            "legal_actions": [str(a) for a in legal] if isinstance(legal, list) else None,
            "turn": int(msg.get("turn", 0) or 0), "warning": msg.get("warning"),
            "opponent_chat": chat_texts(msg.get("chat")), "artifacts": art,
            "chat_full": chat_full(msg.get("chat")), "my_actions": list(mine),
            "new_feedback": new_lines(obs, STATE["prev_obs"]),
            "match_id": str(game.get("match_id", "") or ""), "game_index": int(msg.get("game_index", 0) or 0),
            "opponent": str(game.get("opponent", "") or "")},
            "llm": STATE["llm"], "match_id": game.get("match_id"), "budget": max(0.5, limit - 2.0)}
        ans = wk.ask(req, limit - (time.monotonic() - t0) - 0.5)
        if not ans:
            model_error = "worker_timeout_or_error"
        if ans:
            a, c = ans.get("action"), ans.get("chat")
            a = a if isinstance(a, str) else ""
            rejected = warning.get("rejected") if warning else None
            v = validate.validate(a, legal, art, rejected, previous, observation=obs, rules=rules_text)
            if fmt and v is not None and not actionfmt.matches(fmt, v):
                v = actionfmt.repair(fmt, v)  # near miss (quotes, trailing period) or None -> fallback
            if fmt and v is None and a and actionfmt.matches(fmt, a) and not (rejected and fallback.norm(a) == fallback.norm(rejected)):
                v = a if a not in previous and fallback.norm(a) not in {fallback.norm(p) for p in previous} else None
            model_error = ans.get("model_error")
            meta = {k: ans.get(k) for k in ("family", "strategy", "tool", "reason", "candidates_left",
                                             "facts_used", "tools_called", "assist_source", "assist_ms")}
            if v is not None:
                action = v
                source = ans.get("source") if ans.get("source") in ("model", "strategy", "fallback") else "fallback"
                chat = protocol.clean_chat(c) or fb_chat
            else:
                meta["tool"] = "fallback"
                meta["reason"] = "answer rejected by validator (illegal, repeated or malformed): " + str(meta.get("reason") or "")
    except Exception:
        traceback.print_exc()
    # Hard circuit breaker: NEVER re-send a move rejected by warning (Rules 8.1, 8.2)
    if warning:
        rej = str(warning.get("rejected", ""))
        if rej and (action == rej or fallback.norm(action) == fallback.norm(rej)):
            protocol.log(f"CRITICAL: action '{action}' matches rejected '{rej}', forcing fresh non-repeating fallback!")
            action = fallback.fallback_action(legal, art, rejected=rej, conservative=True, avoid_also=list(mine) + [rej], rules=rules_text,
                                                observation=obs, warning=warning)
            source = "fallback"
            meta["tool"] = "fallback"
            meta["reason"] = f"override rejected action '{rej}' with emergency fallback"
    if fmt and not actionfmt.matches(fmt, action):  # last gate: every outgoing action (model, tool, fallback) fits the template
        rej = warning.get("rejected") if warning else None
        fixed = actionfmt.repair(fmt, action) or fallback.fallback_action(
            legal, art, rejected=rej, conservative=bool(warning), avoid_also=list(mine) + ([rej] if rej else []),
            observation=obs, warning=warning, rules=rules_text)
        protocol.log(f"template gate: {action!r} -> {fixed!r}")
        action, source = fixed, "fallback"
        meta["tool"] = "fallback"
        meta["reason"] = "outgoing action did not fit the action template"
    terms = forbidden_terms_of(art)
    if terms and forbidden.contains(action, terms):  # the action itself says a forbidden term (talking is the move)
        rej = warning.get("rejected") if warning else None
        safe = forbidden.safe_action(action, terms, legal=legal, fmt=fmt, art=art, avoid=list(mine) + ([rej] if rej else []),
                                     observation=obs, warning=warning)
        protocol.log(f"forbidden-term gate: {action!r} -> {safe!r}")
        action, source = safe, "fallback"
        meta["tool"] = "fallback"
        meta["reason"] = "action contained a forbidden term"
    from core import chatsafe
    obs_priv = chatsafe.extract_private_tokens(obs) + chatsafe.extract_private_chunks(obs)
    all_terms = list(dict.fromkeys(list(terms) + obs_priv))
    chat = wk_filter(protocol.clean_chat(chat), all_terms)
    chat = clean_line(chat, all_terms, art)
    protocol.send({"type": "action", "action": action, "chat": protocol.clean_chat(chat) or fallback.NEUTRAL_CHAT})
    mine.append(action)
    STATE["prev_obs"] = obs
    meta.setdefault("family", art.get("family"))
    meta["action"] = action
    log_decision(msg, source, time.monotonic() - t0, model_error, meta)


def log_decision(msg, source, secs, model_error, meta=None):
    """One line per decision on stderr and in log.jsonl: game, turn, family, strategy, tool, reason, candidates_left,
    source (tool|model|fallback), answer_ms, model_error. Stdout stays protocol-only."""
    g = STATE["game"]
    meta = meta or {}
    src = {"strategy": "tool"}.get(source, source)  # a strategy's own computation is a "tool" decision
    rec = {"kind": "decision", "game": g.get("game_id"), "game_index": msg.get("game_index"), "turn": msg.get("turn"),
           "family": meta.get("family"), "strategy": meta.get("strategy"), "tool": meta.get("tool"),
           "action": meta.get("action"), "reason": meta.get("reason"), "candidates_left": meta.get("candidates_left"),
           "source": src, "answer_ms": int(secs * 1000), "model_error": model_error}
    for k in ("facts_used", "tools_called", "assist_source", "assist_ms"):
        if k in meta and meta[k] is not None:
            rec[k] = meta[k]
    protocol.log("decision " + json.dumps(rec, default=str))
    try:
        memory.append_log(memory.game_dir(g.get("game_id", ""), g.get("rules", "")), rec)
    except Exception:
        traceback.print_exc()


def on_end(msg):
    protocol.log(f"game {msg.get('game_index')} {msg.get('result')}: {msg.get('reason')}")  # never exit here
    try:
        g = STATE["game"]
        memory.append_log(memory.game_dir(g.get("game_id", ""), g.get("rules", "")), {
            "t": time.time(), "match_id": g.get("match_id"), "game_index": msg.get("game_index"),
            "result": msg.get("result"), "reason": str(msg.get("reason", ""))[:200],
            "opponent": g.get("opponent") or g.get("opponent_id"), "variant": (g.get("variant") or {}).get("label")
            if isinstance(g.get("variant"), dict) else None})
    except Exception:
        traceback.print_exc()


def main():
    protocol.setup_stdio()
    wk = worker.WorkerClient()
    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            traceback.print_exc()
            continue
        if not line:
            break  # EOF: arena is done
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError("not an object")
        except ValueError:
            protocol.log("bad line from arena:", line[:200])
            continue
        kind = msg.get("type")
        try:
            if kind == "prep":
                on_prep(msg, wk)
            elif kind == "start":
                on_start(msg, wk)
            elif kind == "turn":
                on_turn(msg, wk)
            elif kind == "end":
                on_end(msg)
            elif kind == "shutdown":
                break
        except Exception:
            traceback.print_exc()
            # never leave the arena waiting
            try:
                if kind == "prep":
                    protocol.send({"type": "ready"})
                elif kind == "start":
                    protocol.send({"type": "ready", "chat": START_CHAT})
                elif kind == "turn":
                    a, c = fallback.fallback_decision(msg, None)
                    protocol.send({"type": "action", "action": a, "chat": c})
            except Exception:
                traceback.print_exc()
    wk.stop()


if __name__ == "__main__":
    main()
