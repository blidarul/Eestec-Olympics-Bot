"""Token and cost per turn from the fake gateway log. Usage: python tests/mbappe/measure_cost.py <gateway.jsonl>

Input tokens are ESTIMATED as characters / 4 (the fake gateway has no tokenizer). Output tokens are
the length of the fake model's answer / 4: for the compact JSON that is the real format; for the starter's
"ACTION/CHAT" text it is an ASSUMED typical answer (short reasoning + action + one chat sentence). Prices: rule 7.5.
"""
import json
import sys

IN_PRICE, OUT_PRICE = 0.10 / 1e6, 0.50 / 1e6
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
turns = [r for r in rows if "Observation:" in r["user"] or "Legal actions" in r["user"]]
if not turns:
    sys.exit("no turn calls in the log")
n = len(turns)
tin = sum(r["usage"]["prompt_tokens"] for r in turns) / n
tout = sum(r["usage"]["completion_tokens"] for r in turns) / n
print(f"turn calls: {n}   avg input tokens: {tin:.0f}   avg output tokens: {tout:.0f}   max_tokens sent: {sorted({r.get('max_tokens') for r in turns})}")
print(f"cost per turn: ${tin * IN_PRICE + tout * OUT_PRICE:.6f}  (input ${tin * IN_PRICE:.6f} + output ${tout * OUT_PRICE:.6f})")
print(f"cost for a 3-game match of ~30 turns: ${30 * (tin * IN_PRICE + tout * OUT_PRICE):.4f}")
