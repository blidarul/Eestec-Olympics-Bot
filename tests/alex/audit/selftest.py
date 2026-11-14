"""Self-test of drive.py + fake_gateway.py on one tic_tac_toe exchange (no real model)."""
import json, os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import drive, fake_gateway, msgs
out = os.path.join(os.path.dirname(__file__), "out"); os.makedirs(out, exist_ok=True)
log = os.path.join(out, "selftest_gw.jsonl"); open(log, "w").close()
gw = fake_gateway.GW(log, "fixed", json.dumps({"action": "a1", "chat": "hi"}))
llm = {"base_url": gw.url, "api_key": "k-selftest", "model": "haiku"}
prep, start, turn, g = msgs.build("tic_tac_toe", 0, 0, 1, llm)
mem = tempfile.mkdtemp(prefix="auditmem_")
t = time.time()
r = drive.run([prep, start, turn(), {"type": "end", "game_index": 1, "result": "win"}, {"type": "shutdown"}],
              memory_dir=mem, timeouts={"prep": 600})
print(drive.summarize(r)); print("wall", round(time.time() - t, 1))
for a in r["answers"]: print(a["for"], a.get("latency"), a.get("ok"), a.get("problems"), (a.get("line") or "")[:100])
n = sum(1 for _ in open(log)); print("gateway requests", n)
print("stderr tail:", r["stderr_tail"][-250:].replace("\n", " | "))
json.dump(r, open(os.path.join(out, "selftest.json"), "w"), indent=1)
