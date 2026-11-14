"""Fake OpenAI-compatible gateway: logs each request to a JSONL file, answers from a mode."""
import json, threading, time, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class GW:
    def __init__(self, log_path, mode="fixed", reply="", port=0, delay=0.0):
        self.log_path, self.mode, self.reply, self.delay = log_path, mode, reply, delay
        gw = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                try: req = json.loads(body)
                except Exception: req = {"raw": body[:200].decode("utf8", "ignore")}
                key = (self.headers.get("Authorization") or "")[-6:]
                msgs = req.get("messages") or []
                rec = {"t": time.time(), "path": self.path, "key_tail": key, "model": req.get("model"),
                       "max_tokens": req.get("max_tokens"), "thinking": (req.get("extra_body") or {}).get("thinking", req.get("thinking")),
                       "has_tools": bool(req.get("tools")), "n_msgs": len(msgs),
                       "chars": sum(len(json.dumps(m.get("content"))) for m in msgs), "messages": msgs}
                with open(gw.log_path, "a", encoding="utf8") as f: f.write(json.dumps(rec) + "\n")
                if gw.delay: time.sleep(gw.delay)
                if gw.mode.startswith("status:"):
                    self.send_response(int(gw.mode[7:])); self.end_headers(); self.wfile.write(b'{"error":"budget"}'); return
                if gw.mode == "500":
                    self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"boom"}'); return
                content = gw.reply(req) if callable(gw.reply) else {"empty": "", "garbage": "}{ not json \x00 ???"}.get(gw.mode, gw.reply)
                out = {"id": "x", "object": "chat.completion", "model": "haiku",
                       "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                       "usage": {"prompt_tokens": rec["chars"] // 4, "completion_tokens": len(content) // 4, "total_tokens": 0}}
                b = json.dumps(out).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        self.srv = ThreadingHTTPServer(("0.0.0.0", port), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def close(self): self.srv.shutdown()
    @property
    def url(self): return f"http://host.docker.internal:{self.port}/v1"

if __name__ == "__main__":
    g = GW(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "fixed", sys.argv[3] if len(sys.argv) > 3 else "")
    print(g.url); time.sleep(3600)
