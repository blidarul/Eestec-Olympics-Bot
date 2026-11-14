"""Starter harness for the AI Harness Arena (EESTEC Olympics 14, dvloper.io challenge).

Deliberately minimal: one LLM call to prepare, one LLM call per turn, no tools. It plays legal
moves and not much more. Your job is to turn it into a real harness.

Life of a container (see PROTOCOL.md):
- `prep` (fully automatic, after the freeze): the arena starts your image once per needed game and hands
  this copy that ONE game's rules (every variant). The copy has `seconds` (600) to turn itself into a
  specialist for that game, then answers `ready` and waits. Each variant also carries `sample_turn`: one
  real `turn` message from the middle of a sample game (the exact observation format). The starter only
  asks the model for a short playbook (rules + example turns) and saves it and the samples in
  /memory/<game_id>/ (a real harness builds a simulator, a solver, a parser tested on the samples, a chat plan).
- `start` / `turn` / `end`: whenever a match draws this game. The same container plays it in match
  after match; `end` with `match_over` is NOT the end of its life. A container that got no prep (a cold
  one) starts directly with `start` and the normal study clock.
- `shutdown` (or stdin closed): save what you want and exit.

The LLM key changes every match: always use `msg["llm"]` from the latest `prep` / `start`.

Protocol: one JSON object per line on stdin, one JSON object per line on stdout. Anything you want to
print for debugging goes to stderr.
"""
import hashlib
import json
import os
import re
import sys
import time

from openai import OpenAI

# The chat defense package (chat/) lives at the repo root; in the image it is copied next to main.py.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chat.pipeline import ChatDefense, RECOMMENDED_MAX_TOKENS  # noqa: E402

MEMORY_DIR = os.environ.get("MEMORY_DIR", "/memory")
LLM = {"base_url": os.environ.get("LLM_BASE_URL", "http://localhost:4000/v1"),
       "api_key": os.environ.get("LLM_API_KEY", "missing-key"),
       "model": os.environ.get("LLM_MODEL", "haiku")}
_client = {"key": None, "client": None}
PLAYBOOKS = {}  # game_id -> playbook text (this container usually only ever sees one game)
DEFENSE = {"obj": None}  # the ChatDefense of this container (created on first use)

PREP_SYSTEM = """You are preparing to play a two-player game in a tournament. Below are the rules of
every variant. Write a compact playbook (at most 25 lines): the action format, the winning idea,
opening moves, what to look for each turn, common traps, and how to bluff or read the opponent if that
matters. Plain text, no preamble."""

def log(*parts):
    print(*parts, file=sys.stderr, flush=True)


def defense(game_id=None):
    """The ChatDefense, with this game's /memory folder for its speech-rule cache."""
    if DEFENSE["obj"] is None:
        DEFENSE["obj"] = ChatDefense(memory_dir=game_dir(game_id) if game_id else None, log=log)
    return DEFENSE["obj"]


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def use_llm(msg):
    """`prep` and `start` carry the LLM settings for what follows (a fresh key per match)."""
    info = msg.get("llm") or {}
    for k in ("base_url", "api_key", "model"):
        if info.get(k):
            LLM[k] = info[k]


def client():
    if _client["client"] is None or _client["key"] != (LLM["base_url"], LLM["api_key"]):
        _client["client"] = OpenAI(base_url=LLM["base_url"], api_key=LLM["api_key"], max_retries=0)  # no hidden retries: they eat the clock
        _client["key"] = (LLM["base_url"], LLM["api_key"])
    return _client["client"]


def ask_llm(system, user, seconds, max_tokens=400):
    try:
        resp = client().chat.completions.create(
            model=LLM["model"],
            max_tokens=max_tokens,
            timeout=max(3.0, min(seconds - 8.0, 12.0)),  # well inside the move clock
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            # Haiku 5.5 thinks by default and thinking tokens count toward max_tokens:
            # disabled here for speed. Use {"type": "enabled", "budget_tokens": N} to think.
            extra_body={"thinking": {"type": "disabled"}},
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:  # one stderr line per call: used to measure tokens and cost
            log(f"USAGE in={getattr(usage, 'prompt_tokens', 0)} out={getattr(usage, 'completion_tokens', 0)}")
        return resp.choices[0].message.content or ""
    except Exception as exc:  # timeouts, budget exhausted, ...
        log("LLM error:", exc)
        return ""


# ------------------------------------------------------------------ memory
def game_dir(game_id):
    # /memory is shared by ALL your containers (one per game): keep each game in its own folder
    return os.path.join(MEMORY_DIR, re.sub(r"[^a-z0-9_-]", "_", str(game_id).lower()))


def fingerprint(variants):
    text = "\n".join(v.get("label", "") + "\n" + v.get("rules", "") for v in variants)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def save_playbook(game_id, fp, text):
    try:
        os.makedirs(game_dir(game_id), exist_ok=True)
        with open(os.path.join(game_dir(game_id), "playbook.json"), "w", encoding="utf-8") as fh:
            json.dump({"game_id": game_id, "fingerprint": fp, "playbook": text, "made": time.time()}, fh)
    except OSError as exc:
        log("memory write failed:", exc)


def save_samples(game_id, fp, variants):
    """`prep` brings one real `turn` message per variant (`sample_turn`, mid-game, the exact text format of
    an observation): keep them as notes, e.g. to test the parser your harness builds before the first real turn."""
    samples = {v.get("label", ""): v["sample_turn"] for v in variants if v.get("sample_turn")}
    try:
        os.makedirs(game_dir(game_id), exist_ok=True)
        with open(os.path.join(game_dir(game_id), "samples.json"), "w", encoding="utf-8") as fh:
            json.dump({"game_id": game_id, "fingerprint": fp, "sample_turns": samples}, fh)
    except OSError as exc:
        log("memory write failed:", exc)


def load_playbook(game_id):
    if game_id in PLAYBOOKS:
        return PLAYBOOKS[game_id]
    try:
        with open(os.path.join(game_dir(game_id), "playbook.json"), encoding="utf-8") as fh:
            PLAYBOOKS[game_id] = json.load(fh).get("playbook", "")
    except (OSError, ValueError):
        PLAYBOOKS[game_id] = ""
    return PLAYBOOKS[game_id]


# ------------------------------------------------------------------ the loop
def prep(msg):
    started = time.time()
    use_llm(msg)
    game_id = msg["game_id"]
    variants = msg.get("variants") or []
    fp = fingerprint(variants)
    save_samples(game_id, fp, variants)
    try:
        defense(game_id).prep(msg)  # speech rules of every variant, cached in /memory/<game>/
    except Exception as exc:  # the defense must never break prep
        log("chat prep failed:", exc)
    parts = []
    for v in variants:
        part = f"=== VARIANT: {v.get('label', '')} ===\n{v.get('rules', '')}"
        sample = v.get("sample_turn")  # a real mid-game turn of a sample deal: the exact observation format
        if sample:
            part += (f"\n--- Example turn (sample deal, turn {sample.get('turn')}) ---\n{sample.get('observation', '')}"
                     f"\nLegal actions: {sample.get('legal_actions')}")
        parts.append(part)
    rules = "\n\n".join(parts)
    budget = max(10.0, min(240.0, float(msg.get("seconds", 600)) - 60.0))  # keep a safety margin
    playbook = ask_llm(PREP_SYSTEM, rules, budget, max_tokens=1500)
    PLAYBOOKS[game_id] = playbook
    save_playbook(game_id, fp, playbook)
    log(f"prep {game_id}: {len(variants)} variant(s), playbook {len(playbook)} chars in {time.time() - started:.0f}s")
    send({"type": "ready"})


def main():
    game = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            break  # stdin closed: the arena is done with this container
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log("bad line from arena:", line[:200])
            continue
        kind = msg.get("type")

        if kind == "prep":
            prep(msg)

        elif kind == "start":
            use_llm(msg)  # this match's key
            game = msg
            log(f"start {msg['match_id']} game {msg['game_index']}: {msg['game_name']} ({msg['variant'].get('label')}) "
                f"as seat {msg['seat']} vs {msg['opponent']}, study {msg['study_seconds']}s")
            load_playbook(msg["game_id"])
            try:
                ready_chat = defense(msg["game_id"]).start(msg)  # a GREET template line, filtered
            except Exception as exc:
                log("chat start failed:", exc)
                ready_chat = "Good luck."
            send({"type": "ready", "chat": ready_chat})

        elif kind == "turn":
            started = time.time()
            legal = msg.get("legal_actions")
            fallback = legal[0] if legal else ""  # a legal move that needs no model
            try:
                d = defense(game.get("game_id"))
                # chat goes into the prompt inside untrusted tags, with the signals (see chat/wrap.py)
                system, user = d.prompts(msg, game.get("rules", ""), PLAYBOOKS.get(game.get("game_id"), ""),
                                         game.get("seat", 0))
                text = ask_llm(system, user, msg["seconds"], max_tokens=RECOMMENDED_MAX_TOKENS)
                # parse -> action guard -> chat line from templates -> filters (all in code, no second call)
                action, chat, info = d.finish(text, msg, fallback=fallback)
                log(f"turn {msg['turn']}: {action!r} intent={info['intent']} guard={info['guard']} "
                    f"parsed={info['parsed']} problems={info['problems']} sig={info['signals']['severity']}")
            except Exception as exc:  # never crash, never answer late: safe move and a neutral line
                log("turn failed:", repr(exc))
                action, chat = fallback, "Your move."
            send({"type": "action", "action": action, "chat": chat})
            log(f"turn {msg['turn']}: done in {time.time() - started:.1f}s")

        elif kind == "end":
            log(f"game {msg['game_index']} {msg['result']}: {msg['reason']}")
            try:
                defense(game.get("game_id")).end(msg)
            except Exception as exc:
                log("chat end failed:", exc)
            try:
                os.makedirs(game_dir(game.get("game_id")), exist_ok=True)
                with open(os.path.join(game_dir(game.get("game_id")), "results.jsonl"), "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"match": game.get("match_id"), "opponent": game.get("opponent"),
                                         "result": msg["result"], "reason": msg["reason"]}) + "\n")
            except OSError as exc:
                log("memory write failed:", exc)
            # match_over is NOT the end: a warm container waits for the next match that draws its game

        elif kind == "shutdown":
            log("shutdown: bye")
            break


if __name__ == "__main__":
    main()
