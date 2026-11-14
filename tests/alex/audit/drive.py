"""Drive the bot image over the JSON-lines protocol and record per-answer validity and latency."""
import json, os, subprocess, threading, time, queue, sys

EXPECT = {"prep": "ready", "start": "ready", "turn": "action"}


def run(messages, image="mybot:audit", env=None, env_file=None, memory_dir=None, wait_end=20,
        timeouts=None, extra_args=()):
    """messages: list of dicts. Returns {answers:[...], stray:[...], stderr_tail, exit, exit_s}."""
    cmd = ["docker", "run", "-i", "--rm", "--cpus", "2", "--memory", "2g", "--pids-limit", "256"]
    if env_file: cmd += ["--env-file", env_file]
    for k, v in (env or {}).items(): cmd += ["-e", f"{k}={v}"]
    if memory_dir: cmd += ["-v", f"{memory_dir}:/memory"]
    cmd += list(extra_args) + [image]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf8", bufsize=1)
    q, err = queue.Queue(), []
    threading.Thread(target=lambda: [q.put((time.monotonic(), l)) for l in p.stdout], daemon=True).start()
    threading.Thread(target=lambda: [err.append(l) for l in p.stderr], daemon=True).start()
    res = {"answers": [], "stray": [], "early_stdout": []}
    time.sleep(1.0)
    while not q.empty():  # output before any message
        res["early_stdout"].append(q.get()[1][:120])
    for m in messages:
        t0 = time.monotonic()
        p.stdin.write(json.dumps(m) + "\n"); p.stdin.flush()
        want = EXPECT.get(m.get("type"))
        if not want: continue
        limit = (timeouts or {}).get(m["type"], {"prep": 600, "start": 130, "turn": 25}[m["type"]])
        try:
            t, line = q.get(timeout=limit)
        except queue.Empty:
            res["answers"].append({"for": m["type"], "ok": False, "problem": "no answer", "latency": limit}); continue
        a = {"for": m["type"], "line": line.strip()[:300], "latency": round(t - t0, 3)}
        try:
            o = json.loads(line); a["json"] = isinstance(o, dict)
        except Exception:
            o = None; a["json"] = False
        probs = []
        if not a["json"]: probs.append("invalid json")
        else:
            a["type"] = o.get("type")
            if o.get("type") != want: probs.append(f"type {o.get('type')} != {want}")
            c = o.get("chat")
            a["chat_len"] = len(c) if isinstance(c, str) else None
            if want != "ready" or m["type"] == "start":
                if not isinstance(c, str) or len(c) > 200: probs.append("chat missing/too long")
            if want == "action":
                a["action"] = o.get("action")
                if not o.get("action"): probs.append("empty action")
                legal = m.get("legal_actions")
                if legal and o.get("action") not in legal: probs.append("not in legal_actions")
        a["problems"] = probs; a["ok"] = not probs
        res["answers"].append(a)
        time.sleep(0.05)
        while not q.empty():  # extra lines after the answer = stray stdout
            res["stray"].append(q.get()[1][:120])
    time.sleep(0.3)
    while not q.empty(): res["stray"].append(q.get()[1][:120])
    t0 = time.monotonic()
    try:
        p.stdin.close()
    except Exception: pass
    try:
        p.wait(timeout=wait_end); res["exit"] = p.returncode
    except subprocess.TimeoutExpired:
        res["exit"] = "still running"; p.kill()
    res["exit_s"] = round(time.monotonic() - t0, 2)
    res["stderr_tail"] = "".join(err)[-600:]; res["stderr_full"] = "".join(err)
    return res


def summarize(r):
    n = len(r["answers"]); ok = sum(a.get("ok", False) for a in r["answers"])
    mx = max([a.get("latency", 0) for a in r["answers"]] or [0])
    return f"answers {ok}/{n} ok, max latency {mx}s, stray stdout {len(r['stray'])}, early stdout {len(r['early_stdout'])}, exit {r['exit']} in {r['exit_s']}s"
