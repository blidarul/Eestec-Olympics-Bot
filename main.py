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
START_CHAT = "Good luck, have fun!"

STATE = {"llm": None, "game": {}, "artifacts": {}, "prep": None}


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
    use_llm(msg)
    STATE["game"] = msg
    try:
        STATE["artifacts"] = pick_artifacts(msg, wk)
    except Exception:
        traceback.print_exc()
        STATE["artifacts"] = {}
    forbidden = STATE["artifacts"].get("forbidden_terms") or []
    chat = fallback.fallback_chat(STATE["artifacts"]) if STATE["artifacts"].get("chat_bank") else START_CHAT
    chat = wk_filter(chat, forbidden)
    protocol.send({"type": "ready", "chat": protocol.clean_chat(chat) or fallback.NEUTRAL_CHAT})


def wk_filter(text, forbidden):
    """Main-process forbidden-term cut (core.chatsafe is pure python, safe to import here)."""
    try:
        from core import chatsafe
        return chatsafe.filter_out(text, forbidden, default=fallback.NEUTRAL_CHAT)
    except Exception:
        return text


def on_turn(msg, wk):
    t0 = time.monotonic()
    art = STATE["artifacts"]
    legal = msg.get("legal_actions")
    # fallback FIRST, from the message alone
    fb_action, fb_chat = fallback.fallback_decision(msg, art)
    action, chat = fb_action, fb_chat
    try:
        limit = min(TURN_DEADLINE, 0.6 * float(msg.get("seconds") or 20))
        game = STATE["game"]
        req = {"state": {
            "game_id": str(game.get("game_id", "")), "rules": str(game.get("rules", "")),
            "variant": game.get("variant") or {}, "seat": int(game.get("seat", 0) or 0),
            "observation": str(msg.get("observation", "")),
            "legal_actions": [str(a) for a in legal] if isinstance(legal, list) else None,
            "turn": int(msg.get("turn", 0) or 0), "warning": msg.get("warning"),
            "opponent_chat": chat_texts(msg.get("chat")), "artifacts": art},
            "llm": STATE["llm"], "match_id": game.get("match_id"), "budget": max(0.5, limit - 2.0)}
        ans = wk.ask(req, limit - (time.monotonic() - t0) - 0.5)
        if ans:
            a, c = ans.get("action"), ans.get("chat")
            a = a if isinstance(a, str) else ""
            rejected = (msg.get("warning") or {}).get("rejected") if isinstance(msg.get("warning"), dict) else None
            v = validate.validate(a, legal, art, rejected)
            if v is not None:
                action = v
                chat = protocol.clean_chat(c) or fb_chat
    except Exception:
        traceback.print_exc()
    chat = wk_filter(protocol.clean_chat(chat), art.get("forbidden_terms") or [])
    protocol.send({"type": "action", "action": action, "chat": protocol.clean_chat(chat) or fallback.NEUTRAL_CHAT})
    protocol.log(f"turn {msg.get('turn')}: {action!r} in {time.monotonic() - t0:.2f}s")


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
