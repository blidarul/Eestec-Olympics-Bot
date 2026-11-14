"""Harness check of assist_turn on the real sample_turn of every variant of a game (no docker, no real model).

    python -m tests.alex.e2e_assist <memory_root> <game_id> [<game_id> ...]

memory_root holds <game_id>/<rules hash>/artifacts.json as written by prep (a copy of arena-lite/memory/<bot>/).
Simulator paths written as /memory/... are remapped to memory_root. The model is a stub: 'good' answers with the first
legal action, 'dead' returns an invalid action (exercises the search fallback). Prints one line per variant and stub.
"""
import glob
import json
import os
import subprocess
import sys
import time

from solvers.assist import assist_turn


def _show(game):
    out = subprocess.run([sys.executable, "-m", "arena", "prep", "--bot", "x", "--game", game, "--show"],
                         cwd=os.path.join(os.path.dirname(__file__), "..", "..", "arena-lite"),
                         capture_output=True, text=True, timeout=60).stdout
    return json.loads(out)


def _artifacts(root, game, label):
    for f in glob.glob(os.path.join(root, game, "*", "artifacts.json")):
        try:
            a = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if a.get("label") == label:
            sim = a.get("simulator")
            if isinstance(sim, dict) and str(sim.get("path") or "").startswith("/memory/"):
                sim["path"] = os.path.join(root, sim["path"][len("/memory/"):])
            return a
    return {}


def main(root, games):
    for game in games:
        msg = _show(game)
        for v in msg["variants"]:
            art = _artifacts(root, game, v["label"])
            smp = v["sample_turn"]
            sim = art.get("simulator") or {}
            print("%s | %s | simulator: %s (%s)" % (game, v["label"], "verified" if sim.get("verified") else "NOT verified",
                                                     sim.get("reason", "none in artifacts")))
            for name, reply in (("good", None), ("dead", '{"a": "zzz", "c": "x"}')):
                legal = smp.get("legal_actions")
                content = reply or json.dumps({"a": (legal or ["1"])[0], "c": "ok"})
                llm = lambda m, t, to, mt, c=content: {"content": c, "tool_calls": [], "error": None}  # noqa: E731
                t = time.monotonic()
                a = assist_turn(smp["observation"], legal, art, v["rules"], llm, "sys", "user", t + 12.0, False)
                el = time.monotonic() - t
                s = a.suggestion or {}
                print("   stub %-4s %5.2fs used=%s certain=%s -> %s/%s (%s)" % (
                    name, el, a.facts.used, (a.facts.certain or {}).get("move"), s.get("source"), s.get("action"),
                    str(s.get("why"))[:50]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
