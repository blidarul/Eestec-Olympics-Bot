"""Prints chips per hand (95 percent half-width) of the poker player on 10,000 hands against each scripted opponent."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import poker_sim as S  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "strategies", "bluff", "poker")

for kind in ("kuhn", "leduc"):
    leduc = kind == "leduc"
    data = json.load(open(os.path.join(HERE, f"table_{kind}.json"), encoding="utf-8"))
    print(f"{kind}: table value {data['value_first_actor']} chips/hand, exploitability {data['exploitability']}, iterations {data['iterations']}")
    for opp in ("random", "always_call", "always_raise", "bluffer", "folder", "equilibrium"):
        row = []
        for log in (True, False):
            m, ci = S.play_match(lambda: S.player_bot("MINI POKER " + kind.title(), leduc), S.adversary(opp, data["strategy"]),
                                 leduc, 10000, 11, log)
            row.append(f"{m:+.3f} +-{ci:.3f} ({'log' if log else 'deduced'})")
        print(f"  vs {opp:13s} " + "   ".join(row))
