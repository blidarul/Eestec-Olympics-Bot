"""Solvers and the general toolbox. Tool modules register themselves on import (see catalog.py);
an import error in one module is logged to stderr and skipped, never fatal."""
import importlib
import sys

from solvers import catalog  # noqa: F401
from solvers.catalog import call, list_tools, openai_tools  # noqa: F401

_TOOL_MODULES = (
    "solvers.basic.numbers",
    "solvers.basic.graphs",
    "solvers.basic.probability",
    "solvers.basic.gametheory",
    "solvers.basic.textparse",
)

for _name in _TOOL_MODULES:
    try:
        importlib.import_module(_name)
    except Exception as _exc:  # noqa: BLE001
        print("[solvers] could not import %s: %s: %s" % (_name, type(_exc).__name__, _exc), file=sys.stderr)
