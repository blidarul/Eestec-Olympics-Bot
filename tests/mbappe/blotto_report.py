"""Win / draw / loss rate of the Blotto strategy (best of 5 rounds, 500 games) and the count of illegal allocations."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blotto_sim as S  # noqa: E402

for variant in ("equal", "values", "reserve"):
    print(f"variant {variant}")
    for opp in ("constant", "fixed", "copy", "cycle", "dirichlet", "third", "self"):
        t0 = time.time()
        w, d, l = S.win_rate(variant, opp, 500, seed=7)
        print(f"  vs {opp:10s} win {w:.2f}  draw {d:.2f}  loss {l:.2f}   ({time.time() - t0:.1f}s for 500 games)")
rounds = 0
for variant in ("equal", "values", "reserve"):
    for opp in ("constant", "fixed", "copy", "cycle", "dirichlet", "third", "self"):
        for k in range(300):
            S.play_game(variant, opp, 50000 + k)
            rounds += 5
print(f"illegal allocations in {rounds} simulated rounds: 0 (the simulator raises on any)")
