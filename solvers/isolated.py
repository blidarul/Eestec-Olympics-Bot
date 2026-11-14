"""Run a function of this repo in a child interpreter with a hard timeout (generated code may loop or hang).

    run_isolated("solvers.verify", "child_verify", {...json args...}, timeout) -> dict | None   (None = timeout/crash)

A plain subprocess (not multiprocessing): the prep worker is a daemon process and daemons cannot have mp children.
The child reads one JSON object on stdin, calls module.func(args) and prints one JSON line on stdout; everything the
called code prints goes to stderr. No game content leaves the machine (7.11).
"""
import importlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_isolated(module, func, args, timeout):
    try:
        env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-m", "solvers.isolated", module, func], input=json.dumps(args), cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", timeout=max(1.0, timeout), env=env)
        for line in reversed(p.stdout.splitlines()):
            if line.startswith("{"):
                return json.loads(line)
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def _main():
    real = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    module, func = sys.argv[1], sys.argv[2]
    args = json.loads(sys.stdin.read())
    out = getattr(importlib.import_module(module), func)(args)
    real.write(json.dumps(out) + "\n")
    real.flush()


if __name__ == "__main__":
    _main()
