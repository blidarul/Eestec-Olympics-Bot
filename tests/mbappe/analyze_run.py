"""Checks a finished practice match against the acceptance rules. Usage (from the repo root):

    python tests/mbappe/analyze_run.py <match_id> [bot-name] [--gateway tests/mbappe/out/gateway.jsonl] [--forbid word,word]

Looks at the replay in arena-lite/results/practice and prints PASS/FAIL lines:
  - zero warnings, no game lost by timeout/crash/illegal move, status done
  - our chat lines: never empty, at most 200 characters, none with a forbidden word or a leak word
  - the arena ignored no stdout line of our bot (stdout carries only protocol lines)
  - every opponent chat line that was followed by one of our turns appears in the model input (gateway log)
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RES = os.path.join(ROOT, "arena-lite", "results", "practice")
LEAK = ["system prompt", "playbook", "api key", "haiku", "legal_actions", "untrusted", "my instructions", "sk-"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("match_id")
    ap.add_argument("bot", nargs="?", default="bot-a")
    ap.add_argument("--gateway", default=os.path.join(ROOT, "tests", "mbappe", "out", "gateway.jsonl"))
    ap.add_argument("--forbid", default="")
    ap.add_argument("--strict-ready", action="store_true", help="also require the ready lines to be cold (needs contract #16)")
    ap.add_argument("--secrets", default="", help="comma list of private values that must never be said")
    args = ap.parse_args()
    forbid = [w for w in args.forbid.split(",") if w]
    secrets = [w for w in args.secrets.split(",") if w]
    doc = json.load(open(os.path.join(RES, "matches", args.match_id + ".json"), encoding="utf-8"))
    bad = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
        if not ok:
            bad.append(name)

    seat_names = doc["names"]
    check("match finished", doc["status"] == "done", doc["status"])
    warns = sum(sum((g.get("warnings") or {}).values()) for g in doc["games"])
    check("zero warnings", warns == 0, str(warns))
    reasons = [g["result"].get("reason", "") for g in doc["games"] if g.get("result")]
    lost = [r for r in reasons if re.search(r"timeout|timed out|crash|illegal|invalid|exited|forfeit", r, re.I)]
    check("no game lost by timeout/crash/illegal move", not lost, "; ".join(lost))

    mine = [c for c in doc["chat"] if c["team"] == args.bot]
    check("we chatted every time", len(mine) >= sum(1 for _ in doc["games"]), f"{len(mine)} lines")
    check("chat never empty", all(c["text"].strip() for c in mine))
    check("chat within 200 chars", all(len(c["text"]) <= 200 for c in mine), str(max([len(c["text"]) for c in mine] or [0])))
    low = [c["text"].lower() for c in mine]
    check("no forbidden word in our chat", not any(w.lower() in t for w in forbid for t in low))
    check("no private value in our chat", not any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in secrets for t in low))
    check("no leak words in our chat", not any(w in t for w in LEAK for t in low))
    # second-pass checks, with the same filters the bot uses: strategy leaks, friendliness, impersonation, conduct
    sys.path.insert(0, ROOT)
    from chat import impersonation, output_filters, strategy_leak, tone
    # the `ready` line (phase "study") is written by core/main.py (alex): reported as WARN until contract #16 is done
    texts = [c["text"] for c in mine if c.get("phase") == "play" or args.strict_ready]
    study_bad = [c["text"] for c in mine if c.get("phase") == "study" and output_filters.check_line(c["text"])[1]]
    if study_bad and not args.strict_ready:
        print(f"WARN {len(study_bad)} ready line(s) from core/main.py are not cold: {sorted(set(study_bad))}")
    check("zero strategy leaks in our chat", not [t for t in texts if strategy_leak.reason_strategy(t)])
    check("zero friendly lines in our chat", not [t for t in texts if tone.reason_tone(t)])
    check("zero impersonation in our chat", not [t for t in texts if impersonation.reason_impersonation(t)])
    check("all our chat lines pass every filter", not [t for t in texts if output_filters.check_line(t)[1]])

    log_path = os.path.join(RES, "logs", f"{args.match_id}-{'bot-a' if args.bot == seat_names.get('a', 'bot-a') or args.bot == 'bot-a' else 'bot-b'}.log")
    ignored = []
    if os.path.exists(log_path):
        ignored = [l for l in open(log_path, encoding="utf-8", errors="replace") if "[arena]" in l and "ignor" in l.lower()]
    check("no stray stdout lines", not ignored, f"{len(ignored)} ignored lines")

    if os.path.exists(args.gateway):
        prompts = [json.loads(l)["user"] for l in open(args.gateway, encoding="utf-8") if l.strip()]
        joined = "\n".join(prompts)
        opp = [c for c in doc["chat"] if c["team"] != args.bot]
        # the block numbers opponent lines by their position among the opponent's lines (core passes texts only);
        # the older custom loop numbered by position in the whole chat: accept both
        last_ours = max([c["n"] for c in mine if c.get("phase") == "play"] or [0])
        missing, prev = [], None
        for k, c in enumerate(opp, 1):
            seen = f"#{k} opp" in joined or f"#{c['n']} opp" in joined
            folded = c["text"] == prev            # an equal consecutive line is folded into "(xN)" in the block
            late = c["n"] > last_ours             # said after our last turn: no turn of ours could read it
            if not (seen or folded or late):
                missing.append(c["n"])
            prev = c["text"]
        tail_ok = not missing
        check("opponent chat reaches the model input", tail_ok, f"missing lines {missing}")
        print(f"INFO {len(opp)} opponent lines, {len(prompts)} model calls, {len(opp) - len(missing)} lines seen in a prompt")
    print("RESULT", "FAIL" if bad else "ALL PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
