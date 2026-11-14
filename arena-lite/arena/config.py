"""Paths, defaults and tiny helpers shared by the arena engine (stdlib only).

Path resolution:
- ARENA_ROOT (env) wins when set.
- Inside the organizer repo (A:\\eestec\\platform\\arena) the root is the repo
  root (two levels above this package).
- Anywhere else (participant-kit/arena-lite) the root is the current directory,
  so results/ and memory/ land next to where you run `python -m arena`.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def _detect_root() -> Path:
    env = os.environ.get("ARENA_ROOT")
    if env:
        return Path(env).resolve()
    platform_dir = PACKAGE_DIR.parent
    if platform_dir.name == "platform" and (platform_dir.parent / "docs").is_dir():
        return platform_dir.parent
    return Path.cwd().resolve()


ROOT = _detect_root()
PLATFORM = ROOT / "platform"
RESULTS = ROOT / "results"
MEMORY = ROOT / "memory"
TEAMS_JSON = PLATFORM / "teams.json"
GATEWAY_ENV = PLATFORM / "infra" / "gateway" / ".env"
HARBOR_ENV = PLATFORM / "infra" / "harbor" / ".env"
STANDINGS_JSON = RESULTS / "standings.json"
EVENT_JSON = PLATFORM / "event.json"  # organizer-only event settings (reserved games); optional
RELEASED_JSON = PLATFORM / "released.json"  # tournament games released to the practice kit (arena release)

# ---- event defaults (ARCHITECTURE.md sections 4-5) -----------------------
STUDY_SECONDS = 120  # in-match study clock of a cold container (no warm container for the drawn game)
WARM_STUDY_SECONDS = 30  # in-match study clock of a warm container (already prepared for the drawn game)
MOVE_SECONDS = 20
BEST_OF = 3
MAX_SUDDEN_DEATH = 3
PARALLEL = 4
MAX_BUDGET = 0.75  # USD per bot per match
KEY_DURATION = "6h"
MODEL = "haiku"
SHUTDOWN_GRACE = 15.0  # seconds a bot gets to exit after stdin is closed
CLOCK_GRACE = 0.5  # transport slack added to every deadline (not shown to bots)
MAX_STEPS = 2000  # engine safety cap on decisions per game (games have their own caps)
COMMENT_MAX = 200
CHAT_MAX = 200  # chars per chat line (`chat`, or the legacy `comment` alias)
CHAT_HISTORY = None  # every start / turn / end message carries the WHOLE match chat (no cap)
BAD_ANSWERS_TO_LOSE = 2  # per seat per game: the 1st bad turn answer is a warning, the 2nd loses
HUMAN_IDLE_SECONDS = 900  # a person at a seat has no move clock; this long without a move abandons the run

# ---- prep: warm per-game containers (ARCHITECTURE.md section 4.1) ---------
PREP_SECONDS = 600  # a container's time alone with the rules of its game before the bracket (10 min)
PREP_BUDGET = 0.75  # USD per prep run (its own key, deleted after the prep)
PREP_PARALLEL = 16  # prep runs at a time (each container gets DOCKER_CPUS)
WARM_CAP = 200  # warm containers alive at once per session; beyond it games are played by cold containers
SESSION_STALE = 30.0  # seconds without a heartbeat after which a warm session counts as dead

# ---- docker / network ------------------------------------------------------
NETWORK = "eestec-arena"
GATEWAY_URL = os.environ.get("ARENA_GATEWAY_URL", "http://localhost:4000")
CONTAINER_LLM_BASE_URL = "http://gateway:4000/v1"
HOST_LLM_BASE_URL = "http://localhost:4000/v1"
DOCKER_CPUS = "2"
DOCKER_MEMORY = "2g"
DOCKER_PIDS = "256"
CONTAINER_LABEL = "eestec-arena.bot=1"
# Internet for bots: the egress proxy (platform/infra/egress) joins the arena network as `egress`.
# Bot containers on NETWORK get HTTP(S)_PROXY pointing at it (model services and private addresses
# refused, every host logged); the gateway stays direct. ARENA_EGRESS_PROXY="" turns the internet off.
EGRESS_PROXY = os.environ.get("ARENA_EGRESS_PROXY", "http://egress:3128")
NO_PROXY = "gateway,localhost,127.0.0.1"
EGRESS_LOG = PLATFORM / "infra" / "egress" / "logs" / "egress.jsonl"

PLACEMENT_POINTS = {1: 10, 2: 7, 3: 5, 5: 3, 9: 1}
# ---- who competes (decided 11 Nov 2026) --------------------------------------
# Tournaments and the round robin are played by the student teams only. The organizers' bots
# (kind house / baseline) are practice and show opponents: exhibitions only (`--with-house` overrides).
COMPETING_KINDS = ("team",)
FINAL_FIELD = 8  # the final (T3) is played by the top 8 of the round-robin table (Rulebook 10.8)
NOT_QUALIFIED_PLACE = 9  # a team outside the final field gets the round-of-16 placement in the final


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_name(text: str, max_len: int = 60) -> str:
    """Lower-case [a-z0-9_.-] slug usable in file names and container names."""
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(text)).strip("-.").lower()
    return (s or "x")[:max_len]


def load_env_file(path: str | os.PathLike | None) -> dict[str, str]:
    """Parse KEY=VALUE lines (ignores comments, strips optional quotes)."""
    out: dict[str, str] = {}
    if not path:
        return out
    p = Path(path)
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def read_json(path: str | os.PathLike, default=None):
    """Read JSON, tolerating a concurrent writer (retries briefly)."""
    p = Path(path)
    for attempt in range(5):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return default
        except (json.JSONDecodeError, PermissionError):
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))
    return default


def write_json_atomic(path: str | os.PathLike, data) -> None:
    """Write to a temp file in the same directory, then os.replace().

    On Windows os.replace fails with PermissionError while a reader holds the
    target open, so retry for a short while.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, default=str)
    fd, tmp = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        for attempt in range(40):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
