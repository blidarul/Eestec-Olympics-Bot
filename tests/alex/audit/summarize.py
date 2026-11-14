"""Summarize a gateway JSONL log and a drive.py result json (decisions by source, prompt sizes)."""
import json, sys, collections
def gw(path):
    rs = [json.loads(l) for l in open(path, encoding="utf8")]
    if not rs: return "gateway: 0 requests"
    ch = [r["chars"] for r in rs]
    return f"gateway: {len(rs)} req, chars avg {sum(ch)//len(ch)} max {max(ch)}, keys {sorted({r['key_tail'] for r in rs})}, thinking {collections.Counter(json.dumps(r['thinking']) for r in rs).most_common(2)}"
def decisions(stderr):
    src = collections.Counter(); tools = collections.Counter(); ms = []
    for l in stderr.splitlines():
        i = l.find("{")
        if i < 0: continue
        try: d = json.loads(l[i:])
        except Exception: continue
        if "source" in d: src[d["source"]] += 1; ms.append(d.get("answer_ms") or 0)
        if d.get("tool"): tools[d["tool"]] += 1
    return f"decisions {dict(src)} tools {dict(tools)} max answer_ms {max(ms or [0])}"
if __name__ == "__main__":
    for a in sys.argv[1:]:
        if a.endswith(".jsonl"): print(gw(a))
        else: r = json.load(open(a)); print(decisions(r.get("stderr_tail", "")), "| stray", len(r["stray"]))
