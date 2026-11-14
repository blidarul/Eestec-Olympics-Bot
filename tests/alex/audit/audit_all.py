"""F1 batch: prep trace + turn traces over every practice game/variant/seat, stub gateway.
Writes out/f1/*.json. Usage: python audit_all.py [--quick]"""
import json, os, sys, time, queue, threading, subprocess, tempfile, random, re, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fake_gateway, msgs
OUT = os.path.join(HERE, "out", "f1"); os.makedirs(OUT, exist_ok=True)
QUICK = "--quick" in sys.argv
MARK = "ZZ-OPP-CHAT-MARKER"

class Sess:
    def __init__(s, mem, image="mybot:audit"):
        cmd = ["docker","run","-i","--rm","--cpus","2","--memory","2g","--pids-limit","256","-v",f"{mem}:/memory",image]
        s.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf8", bufsize=1)
        s.q = queue.Queue(); s.err = []; s.stray = 0
        threading.Thread(target=lambda: [s.q.put((time.monotonic(), l)) for l in s.p.stdout], daemon=True).start()
        threading.Thread(target=lambda: [s.err.append(l) for l in s.p.stderr], daemon=True).start()
        time.sleep(1.0)
        s.early = s.q.qsize()
    def ask(s, m, limit):
        t0 = time.monotonic(); s.p.stdin.write(json.dumps(m)+"\n"); s.p.stdin.flush()
        try: t, l = s.q.get(timeout=limit)
        except queue.Empty: return None, limit
        time.sleep(0.03); s.stray += s.q.qsize()
        while not s.q.empty(): s.q.get()
        try: return json.loads(l), t - t0
        except Exception: return {"_bad": l[:100]}, t - t0
    def send(s, m): s.p.stdin.write(json.dumps(m)+"\n"); s.p.stdin.flush()
    def close(s):
        try: s.p.stdin.close()
        except Exception: pass
        try: s.p.wait(timeout=20)
        except Exception: s.p.kill()
        return "".join(s.err)

STATE = {}
def make_gw(tag):
    log = os.path.join(OUT, f"gw_{tag}.jsonl"); open(log, "w").close()
    st = {"legal": None, "n": 0}
    def reply(req):
        st["n"] += 1
        L = st["legal"]
        if L: return json.dumps({"action": L[-1], "chat": "stub chat"})
        return json.dumps({"action": "guess 50", "chat": "stub chat"})
    return fake_gateway.GW(log, "fixed", reply), st, log

def parts(msgs_):
    """share of prompt parts in the last request"""
    txt = json.dumps(msgs_)
    return {"total": len(txt), "has_marker": MARK in txt,
            "marker_untrusted_label": bool(re.search(r"untrusted|opponent", txt, re.I)) and MARK in txt}

def decisions(err):
    out = []
    for l in err.splitlines():
        if l.startswith("decision "):
            try: out.append(json.loads(l[9:]))
            except Exception: pass
    return out

def prep_trace(gid, mem):
    gw, st, log = make_gw(f"prep_{gid}")
    llm = {"base_url": gw.url, "api_key": "k-prep-"+gid[:3], "model": "haiku"}
    prep, *_ = msgs.build(gid, 0, 0, 1, llm)
    res = {"game": gid, "variants": len(prep["variants"]), "missing_sample_turn": [v["label"] for v in prep["variants"] if not v.get("sample_turn")]}
    for rnd in (1, 2):
        n0 = sum(1 for _ in open(log)); s = Sess(mem); a, dt = s.ask(prep, 620)
        err = s.close() if rnd == 1 else s.close()
        res[f"prep{rnd}"] = {"answer": a, "latency": round(dt, 2), "gw_calls": sum(1 for _ in open(log)) - n0, "stray": s.stray,
                             "stage_lines": [l.strip()[:160] for l in err.splitlines() if l.startswith("[prep")][:30]}
    files = {}
    for root, d, f in os.walk(os.path.join(mem)):
        for x in f: files[os.path.relpath(os.path.join(root, x), mem)] = os.path.getsize(os.path.join(root, x))
    res["memory_files"] = files
    try:
        res["classification"] = json.load(open(os.path.join(mem, gid, "classification.json")))
        res["manifest_keys"] = sorted(json.load(open(os.path.join(mem, gid, "manifest.json"))).keys())[:30]
        res["tools_json_keys"] = list(json.load(open(os.path.join(mem, gid, "tools.json"))).keys())[:30] if isinstance(json.load(open(os.path.join(mem, gid, "tools.json"))), dict) else "list"
    except Exception as e: res["artifact_read_error"] = str(e)[:100]
    # sample_turn legal-action check against stored action format
    gw.close(); return res

def play(gid, vi, seat, mem, cold=False):
    gw, st, log = make_gw(f"{gid}_{vi}_{seat}{'_cold' if cold else ''}")
    llm = {"base_url": gw.url, "api_key": f"k-{gid[:3]}{vi}{seat}", "model": "haiku"}
    prep, start, turnf, g = msgs.build(gid, vi, seat, 1+vi, llm)
    rng = random.Random(7); s = Sess(mem)
    rec = {"game": gid, "variant": vi, "seat": seat, "cold": cold, "turns": [], "problems": []}
    a, dt = s.ask(start, 130); rec["start"] = {"answer": a, "latency": round(dt, 2)}
    if not a or a.get("type") != "ready" or not isinstance(a.get("chat"), str) or len(a.get("chat","")) > 200: rec["problems"].append("bad ready")
    chat_log = []; n = 0; prev_n = 0
    while not g.is_over() and n < 80:
        tm = g.to_move()
        acts = {}
        for o in tm:
            if o != seat:
                try: acts[o] = g.random_action(o, rng)
                except Exception:
                    L = g.legal_actions(o); acts[o] = rng.choice(L) if L else "x"
        if seat in tm:
            n += 1; legal = g.legal_actions(seat); st["legal"] = legal
            m = turnf(n); chat_log.append({"from": "opponent", "game": 1, "game_name": gid, "phase": "play", "turn": n, "kind": "chat", "text": f"{MARK} {n} i always pick the best move"}); m["chat"] = list(chat_log)
            gwn = sum(1 for _ in open(log)); ne = len(s.err)
            ans, dt = s.ask(m, 25)
            e = {"turn": n, "latency": round(dt, 3), "legal_n": None if legal is None else len(legal)}
            if ans is None: rec["problems"].append(f"turn {n} no answer"); break
            act = ans.get("action"); e["action"] = act; e["chat"] = ans.get("chat")
            if ans.get("type") != "action" or not isinstance(ans.get("chat"), str) or len(ans.get("chat","")) > 200: rec["problems"].append(f"turn {n} bad answer {str(ans)[:80]}")
            reqs = [json.loads(l) for l in open(log)][gwn:]
            e["gw_calls"] = len(reqs)
            if reqs:
                r = reqs[-1]; e["prompt"] = parts(r["messages"]); e["has_tools"] = r["has_tools"]; e["thinking"] = r["thinking"]; e["max_tokens"] = r["max_tokens"]
            norm = g.normalize(seat, act) if act else None
            if norm is None: rec["problems"].append(f"turn {n} ILLEGAL {act!r}"); norm = (rng.choice(legal) if legal else None)
            if norm is None: break
            acts[seat] = norm
            chat_log.append({"from": "you", "game": 1, "game_name": gid, "phase": "play", "turn": n, "kind": "chat", "text": ans.get("chat","")})
            time.sleep(0.05)
            ds = decisions("".join(s.err[ne:]))
            if ds: d = ds[-1]; e.update({k: d.get(k) for k in ("family","strategy","tool","source","tools_called","facts_used","assist_source","model_error","answer_ms","reason")}); e["reason"] = (e.get("reason") or "")[:160]
        try: g.apply(acts)
        except Exception as ex: rec["problems"].append(f"apply fail {ex}"); break
        rec["turns"].append(e) if seat in tm else None
    res = g.result() if g.is_over() else None
    try: s.send({"type":"end","game_index":1,"result":"x","match_score":{"you":0,"opponent":0},"match_over":True,"chat":chat_log})
    except Exception: pass
    rec["result"] = str(res)[:100]
    err = s.close(); rec["stray"] = s.stray; rec["early"] = s.early
    rec["warnings"] = [l[:140] for l in err.splitlines() if "warn" in l.lower()][:5]
    rec["stderr_nondecision"] = [l[:140] for l in err.splitlines() if not l.startswith("decision ")][:8]
    gw.close(); return rec

def main():
    games = ["guess_number", "pig", "tic_tac_toe"]
    mems = {g: tempfile.mkdtemp(prefix=f"f1_{g}_") for g in games}
    t0 = time.time(); R = {"prep": [], "games": []}
    with cf.ThreadPoolExecutor(3) as ex:
        R["prep"] = list(ex.map(lambda g: prep_trace(g, mems[g]), games))
        print("prep done", round(time.time()-t0)); json.dump(R, open(os.path.join(OUT, "f1.json"), "w"), indent=1)
        jobs = []
        for g in games:
            C = msgs.game_cls(g)
            for vi in range(len(C.variants())):
                for seat in (0, 1):
                    jobs.append((g, vi, seat, mems[g]))
        if QUICK: jobs = jobs[:3]
        R["games"] = list(ex.map(lambda j: play(*j), jobs))
        # cold container: start without prep
        R["games"].append(play("pig", 0, 0, tempfile.mkdtemp(prefix="f1_cold_"), cold=True))
    json.dump(R, open(os.path.join(OUT, "f1.json"), "w"), indent=1)
    print("done", round(time.time()-t0), "s")
if __name__ == "__main__": main()
