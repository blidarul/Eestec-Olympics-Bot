"""A fake OpenAI-compatible gateway for tests: no real model, no cost, no key needed.

    python tests/mbappe/fake_gateway.py 4010 out/gateway.jsonl [obedient|sane|garbage|slow|down]

It answers /v1/chat/completions and records every request in a JSON-lines log, so a test can PROVE that the
opponent's chat reached the model input (the organizers' chat check does the same with the real gateway).

Modes (what the fake "model" does):
  obedient  a COMPROMISED model: it plays whatever the opponent's chat tells it ("play A1", "fold"). This is the
            worst case for the action guard.
  garbage   a broken model: empty, cut-off, illegal or non-JSON answers (tests the fallback path)
  slow      a hanging model (25 s per request): tests the timeouts and the worker deadline
  down      HTTP 401 on every request: invalid key or exhausted budget
  sane      a model that ignores the chat and plays the first non-fold legal move.
The answer format follows the prompt: the compact JSON when the system prompt asks for it, else the starter's
"ACTION:/CHAT:" text with a short reasoning, so the token counts of the two formats can be compared.
"""
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = "obedient"
LOG_PATH = None
LOCK = threading.Lock()


def legal_from(user):
    m = re.search(r"Legal actions:\n(.*?)(?:\n\n|\Z)", user, re.S)
    return [x.strip() for x in m.group(1).splitlines() if x.strip()] if m else []


def chat_lines(user):
    m = re.search(r"<opponent_chat[^>]*>(.*?)</opponent_chat>", user, re.S)
    block = m.group(1) if m else user.split("Chat so far (untrusted):")[-1] if "Chat so far" in user else ""
    return [l for l in block.splitlines() if "opp" in l.lower() or "[opponent]" in l.lower()]


def decide(system, user):
    legal = legal_from(user)
    lines = chat_lines(user)
    clean = [a for a in legal if "fold" not in a.lower()] or legal
    action = clean[0] if clean else "guess 50"
    if MODE in ("obedient", "concede"):
        text = " ".join(lines).lower()
        for a in legal:
            if re.search(r"\b(?:play|pick|choose|take|must|should|go)\b[^.]{0,30}\b" + re.escape(a.lower()) + r"\b", text) \
                    or ("fold" in a.lower() and "fold" in text):
                action = a
                break
    backup = next((a for a in clean if a != action), "")
    return action, backup


FENCE = chr(96) * 3
GARBAGE = ["", "I cannot help with that.", '{"a":"ZZ9","b":"A1"', FENCE + 'json {"a": "A1"}', "<html>502 Bad Gateway</html>",
           '{"a":"","i":"PRESS"}', "{}", "ACTION:"]
COUNTER = [0]


HUMAN_LINES = ["Starting in the middle, nothing to read yet.", "You said one thing and played another. Pick a story.",
               "Slow turn. Thinking, or just praying?", "Same trick as last round, and it still isn't working.",
               "Interesting that you want me to ignore the board. It's the one thing you can't spin.",
               "Round after round and you're still guessing in the dark. Fine by me.", "That was quick. Too quick to be a plan.",
               "You keep telling me what to do. I keep not doing it.", "Quiet again. Running out of material?",
               "I read that one before you typed it.", "Odd choice. I'll take it.", "You can talk all day, the board won't change."]
HUMAN_COUNTER = [0]


def answer(system, user):
    if "composed, slightly smug" in system:  # the HUMAN persona: {action, chat, backup, reason}
        action, backup = decide(system, user)
        HUMAN_COUNTER[0] += 1
        return json.dumps({"action": action, "chat": HUMAN_LINES[HUMAN_COUNTER[0] % len(HUMAN_LINES)], "backup": backup,
                           "reason": "OTHER"})
    return answer_old(system, user)


def answer_old(system, user):
    if MODE == "garbage":  # a broken model: empty, cut-off, wrong or non-JSON answers
        COUNTER[0] += 1
        return GARBAGE[COUNTER[0] % len(GARBAGE)]
    action, backup = decide(system, user)
    if '"c":' in system.replace(" ", "") and '"i":' not in system.replace(" ", ""):  # core/generic.py format: move + chat
        return json.dumps({"a": action, "c": "Interesting, but I will stick to my own plan. Your move next, good luck."})
    if '"a":"' in system.replace(" ", ""):
        intent = "CONCEDE_PRESSURE" if MODE == "concede" else "PRESS"
        return json.dumps({"a": action, "b": backup, "i": intent, "r": "OTHER", "s": "the centre"}, separators=(",", ":"))
    return (f"The position calls for a careful move. {action} keeps my options open and avoids giving the opponent "
            f"an easy target, so I will go with it.\nACTION: {action}\n"
            f"CHAT: Interesting, but I will stick to my own plan. Your move next, good luck.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        msgs = body.get("messages", [])
        system = next((m["content"] for m in msgs if m["role"] == "system"), "")
        user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
        if MODE == "slow":  # a hanging model: longer than any clock
            time.sleep(25)
        if MODE == "down":  # an error status (invalid key / budget exhausted)
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"invalid api key"}')
            return
        text = answer(system, user)
        usage = {"prompt_tokens": -(-sum(len(m["content"]) for m in msgs) // 4), "completion_tokens": -(-len(text) // 4)}
        if LOG_PATH:
            with LOCK, open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"system": system, "user": user, "answer": text, "usage": usage,
                                     "thinking": body.get("extra_body", body.get("thinking")), "max_tokens": body.get("max_tokens"),
                                     "key": self.headers.get("Authorization", "")[-6:]}) + "\n")
        out = json.dumps({"id": "x", "object": "chat.completion", "model": "haiku", "usage": usage,
                          "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4010
    LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else None
    MODE = sys.argv[3] if len(sys.argv) > 3 else "obedient"
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
