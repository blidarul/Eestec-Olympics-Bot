"""OpponentTracker: what we know about an opponent, kept in /memory/opponents/<name>.json (rules 5.14, 5.15).

record_turn(...) adds one observed turn; get_profile(name) returns aggregated tendencies for strategies:
    {match_count, turns, dominant_actions, cooperation_rate, bluff_rate, recent_moves,
     cycle_period, pressure_rate, probe_rate, repeat_rate, known}
An unseen or unreadable opponent gives a NEUTRAL profile (known = False, rates 0.5 / 0.0), never an error.

Safety (all containers share /memory at the same time, rule 5.14):
  - every write goes to a temp file in the same folder, then os.replace (atomic: a reader sees the old or the new
    file, never half of one); a missing, partial or corrupt file is ignored and started again;
  - the file is small and capped (50 recent moves, 100 actions per game, 200 match ids); the name is sanitized;
  - two containers writing at the same moment can lose one turn (read-modify-write): acceptable for statistics;
  - pure Python, no network; a lookup is one small file read (well under 5 ms), nothing here ever raises.
The opponent's chat text is analysed with chat.injection (flags only); the text itself is NOT stored.
"""
import json
import os
import re
import tempfile
import time

from . import patterns

COOP_WORDS = {"cooperate", "cooperation", "c", "share", "trust", "silent", "stay silent", "truth", "honest"}
DEFECT_WORDS = {"defect", "defection", "d", "betray", "steal", "lie", "confess"}
MAX_RECENT, MAX_ACTIONS, MAX_MATCHES = 50, 100, 200


def neutral_profile():
    """What we assume about an opponent we have never seen."""
    return {"known": False, "match_count": 0, "turns": 0, "dominant_actions": [], "cooperation_rate": 0.5,
            "bluff_rate": 0.5, "recent_moves": [], "cycle_period": None, "pressure_rate": 0.0, "probe_rate": 0.0,
            "repeat_rate": 0.0}


def _fresh(name):
    return {"name": name, "turns": 0, "matches": [], "actions": {}, "overall": {}, "recent": [], "coop": 0, "defect": 0,
            "bluff": 0, "bluff_chances": 0, "chat_lines": 0, "pressure": 0, "probes": 0, "repeats": 0, "last_chat": ""}


def _norm(action):
    return " ".join(str(action or "").lower().split())[:60]


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(name or ""))[:60] or "unknown"


class OpponentTracker:
    def __init__(self, memory_dir="/memory"):
        self.dir = os.path.join(str(memory_dir), "opponents")

    # ---- storage ----------------------------------------------------------------------
    def _path(self, name):
        return os.path.join(self.dir, safe_name(name) + ".json")

    def _load(self, name):
        """The stored record, or a fresh one when the file is missing, partial, corrupt or of the wrong shape."""
        try:
            with open(self._path(name), encoding="utf-8") as fh:
                data = json.load(fh)
            fresh = _fresh(name)
            if not isinstance(data, dict):
                return fresh
            for key, default in fresh.items():
                if not isinstance(data.get(key), type(default)):
                    data[key] = default
            return data
        except (OSError, ValueError):
            return _fresh(name)

    def _save(self, name, data):
        try:
            os.makedirs(self.dir, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".tmp_", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, self._path(name))  # atomic: readers never see half a file
            return True
        except OSError:
            return False

    # ---- recording --------------------------------------------------------------------
    def record_turn(self, opponent_name, game_id, our_action, opp_action, opp_chat, context=None):
        """Add one turn. `context` (optional): {"match_id": str, "bluffed": bool, "cooperated": bool}.
        Never raises; a failed write only means this turn is forgotten."""
        try:
            context = context if isinstance(context, dict) else {}
            data = self._load(opponent_name)
            data["turns"] += 1
            mid = context.get("match_id")
            if mid is not None and str(mid) not in data["matches"]:
                data["matches"] = (data["matches"] + [str(mid)])[-MAX_MATCHES:]
            opp = _norm(opp_action)
            if opp:
                per_game = data["actions"].setdefault(str(game_id)[:60], {})
                if opp in per_game or len(per_game) < MAX_ACTIONS:
                    per_game[opp] = per_game.get(opp, 0) + 1
                data["overall"][opp] = data["overall"].get(opp, 0) + 1
                if len(data["overall"]) > MAX_ACTIONS:  # keep the file small: drop the rarest action
                    rare = min(data["overall"], key=data["overall"].get)
                    data["overall"].pop(rare, None)
                data["recent"] = (data["recent"] + [{"g": str(game_id)[:30], "us": _norm(our_action), "opp": opp,
                                                     "t": int(time.time())}])[-MAX_RECENT:]
                if "cooperated" in context:
                    data["coop" if context["cooperated"] else "defect"] += 1
                elif opp in COOP_WORDS:
                    data["coop"] += 1
                elif opp in DEFECT_WORDS:
                    data["defect"] += 1
            if "bluffed" in context:
                data["bluff_chances"] += 1
                data["bluff"] += 1 if context["bluffed"] else 0
            self._count_chat(data, opp_chat)
            self._save(opponent_name, data)
        except Exception:
            return None

    @staticmethod
    def _count_chat(data, opp_chat):
        """Count what the opponent's chat does (flags only, the text is not kept)."""
        if not isinstance(opp_chat, str) or not opp_chat.strip():
            return
        try:
            from chat import injection  # our own chat package: pure Python
            flags = set(injection.analyze(opp_chat).flags)
        except Exception:
            flags = set()
        data["chat_lines"] += 1
        data["pressure"] += 1 if ({"PRESSURE", "CONCEDE_REQUEST"} & flags) else 0
        data["probes"] += 1 if ({"PROBE_STRATEGY", "REVEAL_PRIVATE", "REVEAL_PROMPT"} & flags) else 0
        text = " ".join(opp_chat.lower().split())
        data["repeats"] += 1 if text == data.get("last_chat") else 0
        data["last_chat"] = text[:200]

    # ---- reading ----------------------------------------------------------------------
    def get_profile(self, opponent_name):
        """Aggregated tendencies; the neutral profile when the opponent is unseen. Never raises."""
        try:
            data = self._load(opponent_name)
            if not data["turns"]:
                return neutral_profile()
            overall = sorted(data["overall"].items(), key=lambda kv: (-kv[1], kv[0]))
            moves = [r.get("opp", "") for r in data["recent"] if isinstance(r, dict)]
            judged = data["coop"] + data["defect"]
            lines = max(1, data["chat_lines"])
            return {"known": True, "match_count": len(data["matches"]), "turns": data["turns"],
                    "dominant_actions": [a for a, _n in overall[:3]],
                    "cooperation_rate": data["coop"] / judged if judged else 0.5,
                    "bluff_rate": data["bluff"] / data["bluff_chances"] if data["bluff_chances"] else 0.5,
                    "recent_moves": moves[-20:], "cycle_period": patterns.detect_cycle(moves),
                    "pressure_rate": data["pressure"] / lines, "probe_rate": data["probes"] / lines,
                    "repeat_rate": data["repeats"] / lines}
        except Exception:
            return neutral_profile()
