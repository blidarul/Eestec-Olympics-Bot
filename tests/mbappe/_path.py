"""Lets the tests import the `chat` package from the repo root (run from anywhere)."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# The older tests describe the COLD persona; test_battle.py switches to the battle persona on purpose.
from chat import config as _config  # noqa: E402

_config.PERSONA = "cold"
