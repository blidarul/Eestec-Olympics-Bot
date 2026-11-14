"""Predetermined opponent bot for Elemental Duel practice matches.

This bot plays a predetermined sequence of elemental spells, tracking its mana
and falling back to affordable spells (or MEDITATE) if drained.
DO NOT IMPORT OR USE THIS BOT IN THE HARNESS FALLBACK (per user instruction).
"""
from __future__ import annotations

import json
import re
import sys

PREDETERMINED_SPELLS = [
    "CAST MEDITATE",
    "CAST FIREBALL",
    "CAST LIGHTNING",
    "CAST GROUND_SPIKE",
    "CAST FIREBALL",
    "CAST SIPHON",
]

PREDETERMINED_CHATS = [
    "I focus my arcane energy.",
    "Behold the roaring flame!",
    "Call down the thunder!",
    "The earth rises to shield me.",
    "A final searing burst!",
    "Your power is mine.",
]


def pick_action(obs: str, turn_num: int) -> tuple[str, str]:
    # Extract affordable spells from observation if present
    affordable = []
    m = re.search(r"Affordable spells:\s*(.*?)\.", obs, re.IGNORECASE)
    if m:
        affordable = [s.strip().upper() for s in m.group(1).split(",") if s.strip()]

    idx = max(0, turn_num - 1) % len(PREDETERMINED_SPELLS)
    desired = PREDETERMINED_SPELLS[idx]
    chat = PREDETERMINED_CHATS[idx]

    if affordable:
        if desired in affordable:
            return desired, chat
        # If desired is not affordable (e.g. siphoned), pick first non-meditate or meditate
        for cand in affordable:
            if "MEDITATE" not in cand:
                return cand, "I adjust my casting."
        return affordable[0], "Gathering mana."

    return desired, chat


def main():
    turn_counter = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue

        msg_type = msg.get("type")
        if msg_type == "prep":
            print(json.dumps({"type": "ready"}), flush=True)
        elif msg_type == "start":
            turn_counter = 0
            print(json.dumps({"type": "ready", "chat": "The elemental arena awaits."}), flush=True)
        elif msg_type == "turn":
            turn_counter += 1
            obs = str(msg.get("observation", ""))
            action, chat = pick_action(obs, turn_counter)
            print(json.dumps({"type": "action", "action": action, "chat": chat}), flush=True)
        elif msg_type == "end":
            turn_counter = 0
        elif msg_type == "shutdown":
            break


if __name__ == "__main__":
    main()
