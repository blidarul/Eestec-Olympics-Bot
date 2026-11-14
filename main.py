"""AI Harness Arena bot: protocol loop. Never exits except on `shutdown` or EOF on stdin.

The main process imports nothing from strategies/, prep/, chat/: strategy work happens in a
worker process (core/worker.py) with a hard deadline, backed by core/fallback.py.
"""
import json
import sys
import time
import traceback

from core import fallback, protocol, worker

PREP_DEADLINE = 540.0  # arena gives 600 s
START_DEADLINE = 2.0  # arena gives 30 s (120 cold)
TURN_DEADLINE = 12.0  # arena gives 20 s
START_CHAT = "Good luck, have fun!"

STATE = {"llm": None, "game": {}, "artifacts": {}}


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


def on_prep(msg):
    use_llm(msg)
    # P1: nothing to build. Answer ready at once (deadline PREP_DEADLINE is for later phases).
    protocol.send({"type": "ready"})


def on_start(msg):
    use_llm(msg)
    STATE["game"] = msg
    protocol.send({"type": "ready", "chat": protocol.clean_chat(START_CHAT) or fallback.NEUTRAL_CHAT})


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
            "budget": max(0.5, limit - 2.0)}
        ans = wk.ask(req, limit - (time.monotonic() - t0) - 0.5)
        if ans:
            a, c = ans.get("action"), ans.get("chat")
            a = a if isinstance(a, str) else ""
            rejected = (msg.get("warning") or {}).get("rejected") if isinstance(msg.get("warning"), dict) else None
            ok = bool(a.strip()) and a != rejected and (not isinstance(legal, list) or not legal or a in legal)
            if ok:
                action = a
                chat = protocol.clean_chat(c) or fb_chat
    except Exception:
        traceback.print_exc()
    protocol.send({"type": "action", "action": action, "chat": protocol.clean_chat(chat) or fallback.NEUTRAL_CHAT})
    protocol.log(f"turn {msg.get('turn')}: {action!r} in {time.monotonic() - t0:.2f}s")


def on_end(msg):
    protocol.log(f"game {msg.get('game_index')} {msg.get('result')}: {msg.get('reason')}")  # never exit here


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
                on_prep(msg)
            elif kind == "start":
                on_start(msg)
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
