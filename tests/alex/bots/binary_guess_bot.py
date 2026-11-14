"""Test opponent for the guess_number practice game (binary search from the observation). Tests only (rule 10.7)."""
import json
import re
import sys


def main():
    lo = hi = None
    for line in sys.stdin:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        t = m.get("type")
        if t == "prep":
            print(json.dumps({"type": "ready"}), flush=True)
        elif t == "start":
            print(json.dumps({"type": "ready", "chat": "Good luck."}), flush=True)
        elif t == "turn":
            obs = m.get("observation", "")
            r = re.search(r"\((\d+)-(\d+)\)", obs)
            a, b = (int(r.group(1)), int(r.group(2))) if r else (1, 100)
            for n, fb in re.findall(r"you guessed (\d+) -> (higher|lower)", obs):
                n = int(n)
                if fb == "higher":
                    a = max(a, n + 1)
                else:
                    b = min(b, n - 1)
            print(json.dumps({"type": "action", "action": f"guess {(a + b) // 2}", "chat": "Hmm."}), flush=True)
        elif t == "shutdown":
            return


if __name__ == "__main__":
    main()
