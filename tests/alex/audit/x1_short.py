"""X1 short F2: gravity 7x6 through the image (both seats, 2 seeds, 1 warm prep), forbidden_terms in artifacts
for the speech-rule game, plus the injection and strict-format checks via f2_all. Usage: python x1_short.py"""
import json, os, sys, tempfile, glob
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import f2_all as F, f2games
def main():
    out = {}; C = f2games.Gravity; mem = tempfile.mkdtemp(prefix="x1g_"); runs = []
    for seat in (0, 1):
        for seed in (1, 2): runs.append(F.run_game(C, 0, seat, seed, mem, f"x1_grav_{seat}_{seed}", prep_first=(seat == 0 and seed == 1), max_turns=30, tlimit=25))
    out["gravity"] = [{k: r.get(k) for k in ("seat", "seed", "problems", "result", "stray", "early", "gw_requests", "prep")} | {"n": len(r["turns"]), "max_lat": max([t["lat"] for t in r["turns"]] or [0]), "sources": sorted({str(t.get("source")) for t in r["turns"]}), "strategy": sorted({str(t.get("strategy")) for t in r["turns"]})} for r in runs]
    Q = f2games.QAGuard; mq = tempfile.mkdtemp(prefix="x1q_"); r = F.run_game(Q, 0, 0, 1, mq, "x1_qa", opp="nasty", prep_first=True, max_turns=5)
    arts = {p: json.load(open(p)).get("forbidden_terms") for p in glob.glob(os.path.join(mq, "**", "*.json"), recursive=True) if "artifact" in os.path.basename(p)}
    out["qa"] = {"problems": r["problems"], "broke": r["broke_speech_rule"], "ready_chat": r["ready_chat"], "artifact_forbidden_terms": arts}
    json.dump(out, open(os.path.join(F.OUT, "x1.json"), "w"), indent=1, default=str); print(json.dumps(out, indent=1, default=str)[:3500])
main()
