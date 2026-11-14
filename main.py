"""AI Harness Arena bot: protocol loop. Never exits except on `shutdown` or EOF on stdin.

The main process imports nothing from strategies/, prep/, chat/: strategy work happens in a
worker process (core/worker.py) with a hard deadline, backed by core/fallback.py.
"""
import json
import sys
import time
import traceback

from core import fallback, memory, protocol, validate, worker

PREP_DEADLINE = 540.0  # arena gives 600 s
START_DEADLINE = 2.0  # arena gives 30 s (120 cold)
TURN_DEADLINE = 12.0  # arena gives 20 s
START_CHAT = "Ready when you are."

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
    """[{"from", "text"}] of the chat of the turn, untrusted, latest last (strings only, bounded)."""
    out = []
    for c in chat or []:
        if isinstance(c, dict) and c.get("text"):
            out.append({"from": str(c.get("from", "?"))[:20], "text": str(c["text"])[:300]})
    return out[-20:]


def new_lines(obs, prev):
    """Observation lines that were not in the previous observation (what happened since our last action)."""
    seen = set(prev.splitlines())
    return [l.strip()[:200] for l in obs.splitlines() if l.strip() and l not in seen][:12]


def on_prep(msg, wk):
    use_llm(msg)
    try:  # specialise inside the worker (prep/, optimization/ never imported here); 540 s hard deadline
        ans = wk.ask({"kind": "prep", "msg": msg}, PREP_DEADLINE)
        res = ans.get("prep") if isinstance(ans, dict) else None
        if isinstance(res, dict) and isinstance(res.get("by_label"), dict):
            STATE["prep"] = res
    except Exception:
        traceback.print_exc()
    protocol.send({"type": "ready"})


def pick_artifacts(msg, wk):
    label = str((msg.get("variant") or {}).get("label", "")) if isinstance(msg.get("variant"), dict) else ""
    prep = STATE.get("prep") or {}
    by = prep.get("by_label") or {}
    art = by.get(label) or by.get(prep.get("first", "")) if by else None
    if not art:  # cold container or restarted: try /memory (worker, short deadline)
        ans = wk.ask({"kind": "load", "game_id": msg.get("game_id", ""), "rules": msg.get("rules", "")}, 1.0)
        art = ans.get("artifacts") if isinstance(ans, dict) else None
    return art if isinstance(art, dict) else {}


def on_start(msg, wk):
    t0 = time.monotonic()
    use_llm(msg)
    STATE["game"] = msg
    try:
        STATE["artifacts"] = pick_artifacts(msg, wk)
    except Exception:
        traceback.print_exc()
        STATE["artifacts"] = {}
    STATE["my_actions"], STATE["prev_obs"] = [], ""
    forbidden = STATE["artifacts"].get("forbidden_terms") or []
    chat = None
    try:  # chat.pipeline.ready_line in the worker (pure code, filtered, never empty); main keeps the 2 s start clock
        ans = wk.ask({"kind": "ready_line", "rules": msg.get("rules", ""), "forbidden": forbidden,
                      "seed": str(msg.get("match_id", ""))}, max(0.2, START_DEADLINE - 0.3 - (time.monotonic() - t0)))
        line = ans.get("line") if isinstance(ans, dict) else None
        chat = line if isinstance(line, str) and line.strip() else None
    except Exception:
        traceback.print_exc()
    if chat is None:
        chat = fallback.fallback_chat(STATE["artifacts"]) if STATE["artifacts"].get("chat_bank") else START_CHAT
        chat = wk_filter(chat, forbidden)
    protocol.send({"type": "ready", "chat": protocol.clean_chat(chat) or fallback.NEUTRAL_CHAT})


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
    legal = msg.get("legal_actions")
    warning = msg.get("warning") if isinstance(msg.get("warning"), dict) else None
    mine = STATE["my_actions"]
    if warning and mine:
        mine.pop()  # the turn is re-sent after a rejected answer: that answer does not count as played
    guessing = (legal is None) or art.get("family") in ("guessing", "deduction", "word", "wordle") or art.get("prep_family") in ("guessing", "deduction", "word", "wordle")
    previous = list(mine) if guessing else []  # guessing / word games: never send the same action twice (safety net)
    obs = str(msg.get("observation", ""))
    # fallback FIRST, from the message alone
    fb_action, fb_chat = fallback.fallback_decision(msg, art, previous)
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
            v = validate.validate(a, legal, art, rejected, previous)
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
            action = fallback.fallback_action(legal, art, rejected=rej, conservative=True, avoid_also=list(mine) + [rej])
            source = "fallback"
            meta["tool"] = "fallback"
            meta["reason"] = f"override rejected action '{rej}' with emergency fallback"
    chat = wk_filter(protocol.clean_chat(chat), art.get("forbidden_terms") or [])
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
