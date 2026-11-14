"""Build the equilibrium tables (run at BUILD time; the arena only reads the JSON files).

    python -m strategies.bluff.poker.build_table            # Kuhn 20000 and Leduc 12000 iterations
Writes table_kuhn.json and table_leduc.json next to this file and prints value and exploitability (chips per hand).
"""
import json
import os
import sys

from . import cfr, exploit

HERE = os.path.dirname(os.path.abspath(__file__))


def build(kind, iterations):
    leduc = kind == "leduc"
    value, table = cfr.solve(leduc, iterations)
    game = cfr.Game(leduc)
    expl = exploit.exploitability(game, table)
    ev = exploit.ev(game, table, table)
    path = os.path.join(HERE, f"table_{kind}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"game": kind, "iterations": iterations, "value_first_actor": round(ev, 5),
                   "exploitability": round(expl, 5), "strategy": table}, fh, separators=(",", ":"))
    print(f"{kind}: {iterations} iterations, value first actor {ev:.4f}, exploitability {expl:.5f}, {len(table)} infosets -> {path}")


if __name__ == "__main__":
    build("kuhn", int(sys.argv[1]) if len(sys.argv) > 1 else 20000)
    build("leduc", int(sys.argv[2]) if len(sys.argv) > 2 else 12000)
