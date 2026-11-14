"""Smallest possible bot: answers ready at once, then plays a random legal action.

    python -m arena practice --bot-a "python examples/random_bot.py" --bot-b "python examples/random_bot.py"

Debug output goes to stderr (it ends up in results/practice/logs/). stdout is for protocol JSON only.
It lives as long as the arena wants: `match_over` is not the end (a warm container plays match after
match); `shutdown` or a closed stdin is.
"""
import json
import random
import sys

for line in sys.stdin:
    if not line.strip():
        continue
    msg = json.loads(line)
    if msg["type"] == "prep":
        # a real harness spends up to msg["seconds"] turning itself into a specialist for msg["game_id"];
        # each variant has "rules" and (usually) "sample_turn": a real mid-game turn message to test a parser on
        print(f"prep {msg['game_id']}: {len(msg['variants'])} variant(s), nothing to build", file=sys.stderr, flush=True)
        print(json.dumps({"type": "ready"}), flush=True)
    elif msg["type"] == "shutdown":
        break
    elif msg["type"] == "start":
        print(f"game {msg['game_index']}: {msg['game_name']} as seat {msg['seat']}", file=sys.stderr, flush=True)
        print(json.dumps({"type": "ready"}), flush=True)
    elif msg["type"] == "turn":
        legal = msg.get("legal_actions")
        # legal_actions is null when there are more than 50 options: a real bot reads the rules
        action = random.choice(legal) if legal else "pass"
        # "chat" is read by your opponent and shown to the audience (msg["chat"] holds what was said so far)
        print(json.dumps({"type": "action", "action": action, "chat": "feeling lucky"}), flush=True)
    elif msg["type"] == "end":
        print(f"game over: {msg['result']} ({msg['reason']})", file=sys.stderr, flush=True)
