"""Strategy and prep work runs in a spawned worker process; the main process only waits with a deadline.

Main side: WorkerClient.ask(request, timeout) -> dict | None (None = timeout/crash; worker restarted).
The main process imports nothing from strategies/, prep/, chat/; the child does, lazily.
"""
import multiprocessing as mp
import os
import sys
import time
import traceback

_ctx = mp.get_context("spawn")


def _worker_main(conn):
    # fd 1 may be the protocol pipe in a naive setup: never let the child write to it.
    try:
        os.dup2(2, 1)
        sys.stdout = sys.stderr
    except Exception:
        pass
    strategies, llm = None, None
    try:
        from strategies import default_strategy
        from strategies.base import TurnState
        fallback_strategy = default_strategy()
    except BaseException:
        traceback.print_exc()
        return
    while True:
        try:
            req = conn.recv()
        except (EOFError, OSError):
            return
        try:
            kind = req.get("kind")
            if kind == "ping":
                conn.send({"pong": True})
                continue
            if kind in ("prep", "load"):
                from core import hooks
                if kind == "prep":
                    conn.send({"prep": hooks.run_prep(req["msg"])})
                else:
                    conn.send({"artifacts": hooks.load_artifacts(req.get("game_id", ""), req.get("rules", ""))})
                continue
            info = req.get("llm")
            if llm is None or (isinstance(info, dict) and info != llm.info):
                try:
                    from core.llm import LLM
                    new = LLM(info)
                    if llm is not None:
                        new.spend, new.fails, new.skip = llm.spend, llm.fails, llm.skip
                    llm = new
                except Exception:
                    traceback.print_exc()
            if llm is not None:
                llm.tick_turn()
            fields = dict(req["state"])
            fields["deadline"] = time.monotonic() + float(req.get("budget", 8.0))
            fields["llm"] = llm
            state = TurnState(**fields)
            strategy = fallback_strategy
            try:
                from core import registry
                strategy = registry.pick(state.rules, state.artifacts)
            except BaseException:
                traceback.print_exc()
            try:
                d = strategy.decide(state)
            except BaseException:
                traceback.print_exc()
                d = fallback_strategy.decide(state)
            conn.send({"action": d.action, "chat": d.chat, "source": d.source})
        except BaseException:
            traceback.print_exc()
            try:
                conn.send(None)
            except Exception:
                return


class WorkerClient:
    def __init__(self, target=_worker_main):
        self._target = target
        self._proc = None
        self._conn = None
        self.start()

    def start(self):
        self.stop()
        try:
            parent, child = _ctx.Pipe()
            proc = _ctx.Process(target=self._target, args=(child,), daemon=True)
            proc.start()
            child.close()
            self._proc, self._conn = proc, parent
        except Exception:
            traceback.print_exc()
            self._proc = self._conn = None

    def stop(self):
        proc, conn = self._proc, self._conn
        self._proc = self._conn = None
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        try:
            if proc and proc.is_alive():
                proc.kill()
                proc.join(1.0)
        except Exception:
            pass

    def ask(self, request: dict, timeout: float):
        """Return the worker's answer dict, or None (worker is then restarted)."""
        try:
            if self._conn is None or not self._proc.is_alive():
                self.start()
            self._conn.send(request)
            if self._conn.poll(max(0.0, timeout)):
                ans = self._conn.recv()
                if isinstance(ans, dict):
                    return ans
                # strategy raised: worker is still alive and healthy
                return None
        except Exception:
            traceback.print_exc()
        self.start()  # timeout or crash: kill and restart
        return None
