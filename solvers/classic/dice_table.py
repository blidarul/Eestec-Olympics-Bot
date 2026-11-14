"""Offline generator for the exact roll/hold table (run by hand, not at play time).

python -m solvers.classic.dice_table 100 6 1   -> writes solvers/data/dice_race_t100_d6_b1.json
Value iteration over (mover score i, opponent score j, turn total k); the file stores, for every (i, j), the
smallest turn total at which holding is optimal ("hold_at"), so lookups are one list index.
"""
import json
import os
import sys


def compute(target, faces, bust, tol=1e-9, max_sweeps=200):
    n = target
    # P[i][j][k]: win probability of the player to move; k in 0..n-i-1 (k >= n-i means hold wins).
    P = [[[0.5] * (n - i) for _ in range(n)] for i in range(n)]
    pr = 1.0 / faces
    rolls = [r for r in range(1, faces + 1) if r != bust]
    for sweep in range(max_sweeps):
        delta = 0.0
        for i in range(n - 1, -1, -1):
            for j in range(n - 1, -1, -1):
                Pij, Pji0 = P[i][j], P[j][i][0]
                for k in range(n - i - 1, -1, -1):
                    cont = pr * (1.0 - Pji0)
                    for r in rolls:
                        nk = k + r
                        cont += pr * (1.0 if i + nk >= n else Pij[nk])
                    if k > 0:
                        hold = 1.0 - (P[j][i + k][0] if i + k < n else 0.0)
                        v = cont if cont > hold else hold
                    else:
                        v = cont
                    d = abs(v - Pij[k])
                    if d > delta:
                        delta = d
                    Pij[k] = v
        if delta < tol:
            break
    hold_at = []
    for i in range(n):
        row = []
        for j in range(n):
            Pij, Pji0 = P[i][j], P[j][i][0]
            h = n - i                                   # reaching the target always holds
            for k in range(1, n - i):
                cont = pr * (1.0 - Pji0) + sum(pr * (1.0 if i + k + r >= n else Pij[k + r]) for r in rolls)
                hold = 1.0 - (P[j][i + k][0] if i + k < n else 0.0)
                if hold >= cont - 1e-12:
                    h = k
                    break
            row.append(h)
        hold_at.append(row)
    return {"target": target, "faces": faces, "bust": bust, "p_first": P[0][0][0], "hold_at": hold_at}


if __name__ == "__main__":
    t, f, b = (int(x) for x in sys.argv[1:4])
    out = compute(t, f, b)
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data",
                        "dice_race_t%d_d%d_b%d.json" % (t, f, b))
    with open(path, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("wrote", path, "p_first=%.4f" % out["p_first"], file=sys.stderr)
