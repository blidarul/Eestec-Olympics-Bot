"""Bot process wrapper: JSON lines over stdin/stdout with per-message timeouts.

Two modes:
- cmd   : a local command (practice / development). `cmd` is a string or a list.
- image : a docker image, started with
          docker run -i --rm --name <unique> --network eestec-arena --cpus 2
          --memory 2g --pids-limit 256 -v <memory dir>:/memory -e ... <image>
          On eestec-arena (internal: no route out) the container also gets
          HTTP(S)_PROXY = the egress proxy, its way to the internet (egress_env).

Windows pipes do not support select(), so a reader thread pushes stdout lines
into a queue and recv() waits on the queue with a timeout. stderr is copied to
a log file by a second thread (arena notes are added there prefixed [arena]).

Robustness: garbage lines, crashes (EOF), silence (timeout), double answers
(stale lines are drained before every request) and huge lines are all turned
into a Reply with a `kind` instead of exceptions.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config

MAX_LINE = 1_000_000  # bytes; longer stdout lines are invalid
MAX_QUEUE = 1000  # unread stdout lines kept per bot
NL = bytes([10])
MAX_LOG = 20_000_000  # bytes of stderr kept per bot start
_EOF = object()
_TOO_LONG = object()

# reply kinds
OK = "ok"
TIMEOUT = "timeout"
INVALID = "invalid"  # not a JSON object / too long / not UTF-8 text
WRONG_TYPE = "wrong_type"
EOF = "crash"  # process exited or closed stdout

_REPLY_TYPES = ("ready", "action")  # answers; the arena sends start/turn/end/prep/shutdown


@dataclass
class Reply:
    kind: str
    msg: dict | None = None
    raw: str = ""
    ms: int = 0
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.kind == OK

    def describe(self) -> str:
        if self.kind == TIMEOUT:
            return f"timed out after {self.ms / 1000:.1f} s"
        if self.kind == EOF:
            return "bot process exited" + (f" ({self.note})" if self.note else "")
        if self.kind == INVALID:
            return "invalid JSON on stdout" + (f": {self.raw[:80]!r}" if self.raw else "")
        if self.kind == WRONG_TYPE:
            return f"wrong message type ({self.note})"
        return "ok"


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_path(p: str | os.PathLike) -> str:
    """Host path in the form Docker Desktop accepts for -v on Windows (A:/x/y)."""
    return Path(p).resolve().as_posix()


def network_exists(name: str = config.NETWORK) -> bool:
    try:
        r = subprocess.run(["docker", "network", "inspect", name], capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_network(name: str = config.NETWORK) -> bool:
    """Create the internal arena network if it is missing ("already exists" is fine)."""
    if network_exists(name):
        return True
    r = subprocess.run(["docker", "network", "create", "--internal", name],
                       capture_output=True, text=True, timeout=60)
    return r.returncode == 0 or "already exists" in (r.stderr or "")


def egress_env(proxy: str | None = None) -> dict[str, str]:
    """Proxy variables for a container on the arena network ({} when the internet is off).

    Both spellings, because tools disagree (curl reads lower-case http_proxy only). NO_PROXY keeps
    the gateway direct. NODE_USE_ENV_PROXY makes Node's built-in fetch/http use them (Node 24+).
    """
    proxy = config.EGRESS_PROXY if proxy is None else proxy
    if not proxy:
        return {}
    env = {}
    for name in ("HTTP_PROXY", "HTTPS_PROXY"):
        env[name] = env[name.lower()] = proxy
    env["NO_PROXY"] = env["no_proxy"] = config.NO_PROXY
    env["NODE_USE_ENV_PROXY"] = "1"
    return env


class Bot:
    """One bot process. Thread-safe enough for one controller thread per bot."""

    def __init__(self, label: str, *, cmd: str | list[str] | None = None, image: str | None = None,
                 env: dict[str, str] | None = None, log_path: str | os.PathLike | None = None,
                 memory_dir: str | os.PathLike | None = None, network: str | None = config.NETWORK,
                 cwd: str | os.PathLike | None = None, docker_args: list[str] | None = None,
                 image_args: list[str] | None = None, labels: dict[str, str] | None = None,
                 shutdown_grace: float = config.SHUTDOWN_GRACE):
        if (cmd is None) == (image is None):
            raise ValueError("exactly one of cmd or image is required")
        self.label = label
        self.cmd = cmd
        self.image = image
        self.env = dict(env or {})
        self.log_path = Path(log_path) if log_path else None
        self.memory_dir = Path(memory_dir) if memory_dir else None
        self.network = network
        self.cwd = str(cwd) if cwd else None
        self.docker_args = list(docker_args or [])  # extra `docker run` options (before the image)
        self.image_args = list(image_args or [])  # container command override (after the image)
        self.labels = dict(labels or {})  # extra docker labels (used to clean up orphans)
        self.shutdown_grace = shutdown_grace
        self.proc: subprocess.Popen | None = None
        self.container: str | None = None
        self.starts = 0
        self._q: queue.Queue = queue.Queue(maxsize=MAX_QUEUE)
        self._log_lock = threading.Lock()
        self._log_fh = None
        self._threads: list[threading.Thread] = []
        self._outq: queue.Queue = queue.Queue()
        self._closing = False

    # ------------------------------------------------------------------ start
    @property
    def mode(self) -> str:
        return "image" if self.image else "cmd"

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _build(self) -> tuple[list[str] | str, dict[str, str]]:
        child_env = dict(os.environ)
        if self.mode == "cmd":
            child_env.update({"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
            if self.memory_dir:
                child_env["MEMORY_DIR"] = str(self.memory_dir)
            child_env.update(self.env)
            if isinstance(self.cmd, str) and os.name != "nt":
                args: list[str] | str = shlex.split(self.cmd)
            else:
                args = self.cmd  # Windows: CreateProcess parses the command line
            return args, child_env
        # image mode: values travel through the docker client's environment
        # (`-e NAME` without a value) so keys never appear on a command line.
        self.container = f"arena-{config.safe_name(self.label, 40)}-{uuid.uuid4().hex[:8]}"
        args = ["docker", "run", "-i", "--rm", "--name", self.container,
                "--label", config.CONTAINER_LABEL,
                *[x for k, v in self.labels.items() for x in ("--label", f"{k}={v}")],
                "--cpus", config.DOCKER_CPUS, "--memory", config.DOCKER_MEMORY,
                "--pids-limit", config.DOCKER_PIDS]
        if self.network:
            args += ["--network", self.network]
        if self.memory_dir:
            args += ["-v", f"{docker_path(self.memory_dir)}:/memory"]
        bot_env = dict(self.env)
        if self.memory_dir:
            bot_env.setdefault("MEMORY_DIR", "/memory")
        if self.network == config.NETWORK:
            for k, v in egress_env().items():
                bot_env.setdefault(k, v)
        for k, v in bot_env.items():
            args += ["-e", k]
            child_env[k] = str(v)
        args += self.docker_args
        args.append(self.image)
        args += self.image_args
        return args, child_env

    def start(self) -> None:
        if self.alive():
            return
        self._cleanup_proc()
        if self.memory_dir:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
        if self.log_path and self._log_fh is None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_fh = open(self.log_path, "ab")
        args, child_env = self._build()
        self._q = queue.Queue(maxsize=MAX_QUEUE)
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self.starts += 1
        self.note(f"start #{self.starts} ({self.mode}: {self.image or self._cmd_text()})")
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=child_env, cwd=self.cwd,
                                         bufsize=-1, **kwargs)
        except OSError as exc:
            self.proc = None
            self.note(f"failed to start: {exc}")
            self._q.put(_EOF)
            return
        self._outq = queue.Queue()
        self._closing = False
        out = threading.Thread(target=self._read_stdout, args=(self.proc, self._q), daemon=True)
        err = threading.Thread(target=self._read_stderr, args=(self.proc,), daemon=True)
        wr = threading.Thread(target=self._write_stdin, args=(self.proc, self._outq), daemon=True)
        out.start()
        err.start()
        wr.start()
        self._threads = [out, err, wr]

    def _cmd_text(self) -> str:
        return self.cmd if isinstance(self.cmd, str) else " ".join(map(str, self.cmd or []))

    # --------------------------------------------------------------- threads
    @staticmethod
    def _put(q: queue.Queue, item) -> None:
        """Queue a stdout item; a flooding bot loses its oldest unread lines, never the EOF."""
        while True:
            try:
                q.put_nowait(item)
                return
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass

    @staticmethod
    def _write_stdin(proc: subprocess.Popen, outq: queue.Queue) -> None:
        """Writes happen here so a bot that stops reading stdin can never block the arena;
        None closes stdin (after everything queued before it was written)."""
        stream = proc.stdin
        try:
            while True:
                data = outq.get()
                if data is None:
                    break
                stream.write(data)
                stream.flush()
        except (OSError, ValueError):
            pass
        try:
            stream.close()
        except (OSError, ValueError):
            pass

    @classmethod
    def _read_stdout(cls, proc: subprocess.Popen, q: queue.Queue) -> None:
        stream = proc.stdout
        try:
            while True:
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE and not line.endswith(NL):
                    cls._put(q, _TOO_LONG)
                    while True:  # discard the rest of the oversized line
                        chunk = stream.readline(MAX_LINE)
                        if not chunk or chunk.endswith(NL):
                            break
                    continue
                cls._put(q, line)
        except (OSError, ValueError):
            pass
        cls._put(q, _EOF)

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        stream = proc.stderr
        written = 0
        try:
            while True:
                chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(4096)
                if not chunk:
                    break
                if written > MAX_LOG:
                    continue  # keep draining so the bot never blocks on a full pipe
                written += len(chunk)
                with self._log_lock:
                    if self._log_fh:
                        try:
                            self._log_fh.write(chunk)
                            if written > MAX_LOG:
                                self._log_fh.write(NL + b"[arena] log limit reached: further stderr discarded" + NL)
                            self._log_fh.flush()
                        except (OSError, ValueError):
                            pass
        except (OSError, ValueError):
            pass

    def note(self, text: str) -> None:
        """Append an arena note to the bot's log file."""
        with self._log_lock:
            if self._log_fh:
                try:
                    stamp = time.strftime("%H:%M:%S")
                    self._log_fh.write(f"[arena {stamp}] {text}\n".encode("utf-8", "replace"))
                    self._log_fh.flush()
                except (OSError, ValueError):
                    pass

    # ------------------------------------------------------------- messaging
    def send(self, msg: dict) -> bool:
        """Queue one message for the writer thread (never blocks)."""
        if not self.alive() or self._closing:
            return False
        self._outq.put((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        return True

    def drain(self) -> list[str]:
        """Discard lines that arrived while no request was pending (double answers etc.)."""
        stale = []
        for _ in range(MAX_QUEUE * 2):  # bounded: a flooding bot cannot keep us here
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is _EOF:
                self._q.put(_EOF)  # keep the EOF marker for the next recv
                break
            if item is _TOO_LONG:
                stale.append("<oversized line>")
            else:
                stale.append(item.decode("utf-8", "replace").rstrip("\r\n"))
        shown = [s for s in stale if s.strip()]
        for s in shown[:10]:
            self.note(f"ignored unexpected stdout line: {s[:200]!r}")
        if len(shown) > 10:
            self.note(f"ignored {len(shown) - 10} more unexpected stdout lines")
        return stale

    def recv(self, timeout: float, expect: str | None = None, t0: float | None = None) -> Reply:
        """Wait for the next protocol line. `expect` = "ready" or "action"."""
        t0 = time.monotonic() if t0 is None else t0
        deadline = t0 + timeout + config.CLOCK_GRACE
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return Reply(TIMEOUT, ms=int(timeout * 1000))
            try:
                item = self._q.get(timeout=remaining)
            except queue.Empty:
                return Reply(TIMEOUT, ms=int(timeout * 1000))
            ms = int((time.monotonic() - t0) * 1000)
            if item is _EOF:
                self._q.put(_EOF)
                code = self.proc.poll() if self.proc else None
                return Reply(EOF, ms=ms, note=f"exit code {code}" if code is not None else "stdout closed")
            if item is _TOO_LONG:
                return Reply(INVALID, ms=ms, raw="<line longer than 1 MB>")
            raw = item.decode("utf-8", "replace").strip()
            if not raw:
                continue  # blank lines are tolerated
            try:
                msg = json.loads(raw)
            except ValueError:
                return Reply(INVALID, raw=raw[:500], ms=ms)
            if not isinstance(msg, dict):
                return Reply(INVALID, raw=raw[:500], ms=ms)
            mtype = msg.get("type")
            if expect and mtype != expect:
                if mtype in _REPLY_TYPES:
                    # a late answer to an earlier request (e.g. after a timeout)
                    self.note(f"ignored late/duplicate {mtype!r} message")
                    continue
                return Reply(WRONG_TYPE, msg=msg, raw=raw[:500], ms=ms,
                             note=f"expected {expect!r}, got {mtype!r}")
            return Reply(OK, msg=msg, raw=raw[:500], ms=ms)

    def request(self, msg: dict, timeout: float, expect: str) -> Reply:
        self.drain()
        t0 = time.monotonic()
        if not self.send(msg):
            code = self.proc.poll() if self.proc else None
            return Reply(EOF, note=f"exit code {code}" if code is not None else "not running")
        return self.recv(timeout, expect=expect, t0=t0)

    # -------------------------------------------------------------- shutdown
    def shutdown(self, grace: float | None = None) -> None:
        """End of the bot's life: send {"type": "shutdown"}, close stdin, wait `grace` seconds, kill."""
        self.send({"type": "shutdown"})
        self.close(grace)

    def close(self, grace: float | None = None) -> None:
        """Close stdin, give the bot `grace` seconds to exit, then kill it."""
        grace = self.shutdown_grace if grace is None else grace
        proc = self.proc
        if proc is not None:
            self._closing = True
            self._outq.put(None)  # the writer closes stdin after the queued messages (e.g. `end`)
            try:
                proc.wait(timeout=max(0.0, grace))
            except subprocess.TimeoutExpired:
                self.note(f"did not exit within {grace:.0f} s after stdin closed: killing")
                self.kill()
        self._cleanup_proc()
        with self._log_lock:
            if self._log_fh:
                try:
                    self._log_fh.close()
                except OSError:
                    pass
                self._log_fh = None

    def kill(self) -> None:
        proc = self.proc
        if self.mode == "image" and self.container:
            try:
                subprocess.run(["docker", "kill", self.container], capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        if proc is not None and proc.poll() is None:
            if os.name == "nt":
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                   capture_output=True, timeout=30)
                except (OSError, subprocess.SubprocessError):
                    pass
            else:
                try:
                    os.killpg(proc.pid, 9)
                except OSError:
                    pass
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass

    def _cleanup_proc(self) -> None:
        proc = self.proc
        if proc is None:
            return
        if proc.poll() is None:
            self.kill()
        self._outq.put(None)
        for t in self._threads:
            t.join(timeout=2)
        if not any(t.is_alive() for t in self._threads):  # never close a stream a thread is blocked on
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
                except (OSError, ValueError):
                    pass
        self._threads = []
        self.proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()


def kill_labeled(label: str, value: str) -> int:
    """docker kill every running bot container with label=value (orphans of a dead runner)."""
    try:
        r = subprocess.run(["docker", "ps", "-q", "--filter", f"label={config.CONTAINER_LABEL}",
                            "--filter", f"label={label}={value}"], capture_output=True, text=True, timeout=30)
        ids = r.stdout.split()
        if ids:
            subprocess.run(["docker", "kill", *ids], capture_output=True, timeout=60)
        return len(ids)
    except (OSError, subprocess.SubprocessError):
        return 0


_UNITS = {"b": 1, "kib": 1024, "kb": 1000, "mib": 1024 ** 2, "mb": 1000 ** 2, "gib": 1024 ** 3, "gb": 1000 ** 3,
          "tib": 1024 ** 4, "tb": 1000 ** 4}


def parse_size_mb(text: str) -> float | None:
    """'123.4MiB' / '1.2GiB' / '512kB' -> megabytes (MiB), None when unreadable."""
    m = re.match(r"\s*([0-9.]+)\s*([A-Za-z]+)", text or "")
    if not m:
        return None
    unit = _UNITS.get(m.group(2).lower())
    try:
        return round(float(m.group(1)) * unit / 1024 ** 2, 1) if unit else None
    except ValueError:
        return None


def container_memory(names: list[str], timeout: float = 60) -> dict[str, float]:
    """Current memory use (MiB) of running containers, from `docker stats --no-stream`."""
    names = [n for n in names if n]
    if not names:
        return {}
    out: dict[str, float] = {}
    try:
        r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}", *names],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return out
    for line in (r.stdout or "").splitlines():
        name, _, usage = line.partition("\t")
        mb = parse_size_mb(usage.split("/")[0])
        if name.strip() and mb is not None:
            out[name.strip()] = mb
    return out


def looks_like_image(spec: str) -> bool:
    """Heuristic for `practice --bot-a`: explicit `image:`/`cmd:` prefixes win."""
    s = spec.strip()
    if s.startswith("image:"):
        return True
    if s.startswith("cmd:"):
        return False
    if any(ch.isspace() for ch in s):
        return False
    if s.lower().endswith((".py", ".exe", ".bat", ".cmd", ".sh", ".js", ".ps1")) or os.path.exists(s):
        return False
    return True


def strip_prefix(spec: str) -> str:
    s = spec.strip()
    for p in ("image:", "cmd:"):
        if s.startswith(p):
            return s[len(p):].strip()
    return s


def python_cmd(script_path: str | os.PathLike) -> list[str]:
    """Command list running a Python script with this interpreter (tests, examples)."""
    return [sys.executable, "-u", str(script_path)]
