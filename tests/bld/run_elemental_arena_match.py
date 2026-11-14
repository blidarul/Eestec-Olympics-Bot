"""Arena match runner: ElementalDuel bot-a (harness with LLM) vs bot-b (predetermined bot).

Sets up a local OpenAI-compatible gateway on an ephemeral port, writes a temporary
env file for the arena runner, executes the arena match, verifies that the harness
successfully plays ElementalDuel using the LLM (no illegal moves, no forfeits),
and cleans up.
Owned by agent `bld`.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARENA_DIR = os.path.join(REPO_ROOT, "arena-lite")


class MockGatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence HTTP server logs to stdout
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)
        try:
            req = json.loads(body)
        except Exception:
            req = {}

        messages = req.get("messages", [])
        user_content = ""
        for m in messages:
            if m.get("role") == "user":
                user_content = m.get("content", "")

        # 1. Prep Phase: Strategic Playbook Synthesis
        if "Synthesize strategic playbook JSON" in user_content:
            content = json.dumps({
                "invariants": [
                    "Elemental duel between two wizards using mana-based spells",
                    "Spells cost mana; damage is dealt simultaneously",
                ],
                "traps": [
                    "Never cast a spell without sufficient mana",
                    "Do not waste high-cost spells when near fatal damage",
                ],
                "opening_guidelines": [
                    "Meditate or siphon in opening turns to secure mana advantage",
                    "Counter incoming lightning with ground spike or ice barrier",
                ],
                "endgame_goals": [
                    "Reduce opponent wizard HP to 0 or maintain higher HP after all rounds",
                ],
            })
        else:
            # 2. Turn Phase: Select an affordable elemental spell
            affordable = []
            m = re.search(r"Affordable spells:\s*(.*?)\.", user_content, re.IGNORECASE)
            if m:
                affordable = [s.strip().upper() for s in m.group(1).split(",") if s.strip()]

            # Strategic decision priority based on mana
            priority = ["CAST LIGHTNING", "CAST FIREBALL", "CAST GROUND_SPIKE", "CAST SIPHON", "CAST MEDITATE"]
            chosen = "CAST MEDITATE"
            for p in priority:
                if p in affordable:
                    chosen = p
                    break
            if not affordable:
                chosen = "CAST MEDITATE"

            chat_lines = {
                "CAST LIGHTNING": "Lightning arcs across the arcane sky!",
                "CAST FIREBALL": "Feel the searing flame!",
                "CAST GROUND_SPIKE": "Earthen spikes shield and strike!",
                "CAST SIPHON": "Your arcane energy drains to me.",
                "CAST MEDITATE": "I channel the ambient mana.",
            }
            chat = chat_lines.get(chosen, "Arcane power guides my hand.")
            content = json.dumps({"a": chosen, "c": chat})

        out = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "model": "haiku",
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }],
            "usage": {
                "prompt_tokens": len(user_content) // 4,
                "completion_tokens": len(content) // 4,
                "total_tokens": (len(user_content) + len(content)) // 4,
            },
        }
        resp_bytes = json.dumps(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_match():
    port = get_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), MockGatewayHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"[runner] mock LLM gateway running on 127.0.0.1:{port}", file=sys.stderr)

    env_path = os.path.join(ARENA_DIR, "elemental_test.env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"LLM_BASE_URL=http://127.0.0.1:{port}/v1\n")
        f.write("LLM_API_KEY=test-arena-key\n")
        f.write("LLM_MODEL=haiku\n")

    try:
        cmd = [
            sys.executable,
            "-m",
            "arena",
            "practice",
            "--bot-a",
            f"{sys.executable} ../main.py",
            "--bot-b",
            f"{sys.executable} examples/elemental_bot.py",
            "--game",
            "elemental_duel",
            "--prep",
            "--prep-seconds",
            "5",
            "--best-of",
            "1",
            "--seed",
            "2",
            "--env-file",
            "elemental_test.env",
        ]
        print(f"[runner] executing arena command: {' '.join(cmd)}", file=sys.stderr)
        proc = subprocess.run(cmd, cwd=ARENA_DIR, capture_output=True, text=True, timeout=60)
        print("=== STDOUT ===")
        print(proc.stdout)
        print("=== STDERR ===")
        print(proc.stderr)

        # Assertions
        assert "illegal move" not in proc.stdout.lower(), "Match contained illegal moves!"
        assert "forfeit" not in proc.stdout.lower(), "Match contained forfeits!"
        assert "bot-a: CAST" in proc.stdout, "bot-a did not cast any elemental spells!"
        assert proc.returncode == 0, f"Arena process failed with code {proc.returncode}"
        print("\n[SUCCESS] ElementalDuel arena practice match completed without warnings, errors, or forfeits!")
    finally:
        server.shutdown()
        if os.path.exists(env_path):
            os.remove(env_path)


if __name__ == "__main__":
    run_match()
