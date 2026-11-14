"""Runs the practice arena with our own test game added, WITHOUT touching arena-lite (a shared path).

    python tests/mbappe/run_with_game.py practice --bot-a ... --bot-b ... --game forbidden_count ...

It puts tests/mbappe/games/forbidden_count.py into the arena's game registry, then runs the normal arena CLI.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.path.abspath(os.path.join(HERE, "..", "..", "arena-lite"))
sys.path.insert(0, ARENA)
sys.path.insert(0, os.path.join(HERE, "games"))
os.chdir(ARENA)

from arena import cli, registry  # noqa: E402
from forbidden_count import ForbiddenCount  # noqa: E402

registry.practice_games()                                   # fill the cache first
registry._cache["practice"]["forbidden_count"] = ForbiddenCount
registry._cache["practice"] = dict(sorted(registry._cache["practice"].items()))

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]) or 0)
