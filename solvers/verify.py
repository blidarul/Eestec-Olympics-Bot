"""Simulator verification: a prep-written simulator is trusted only if it passes ALL of these on the variant's
sample turn (no sample_turn -> not verified):
  1. parse(sample_turn.observation) does not raise and returns a state that is not terminal;
  2. when the sample's legal_actions is a list: set(legal(state)) == set(that list);
  3. 200 random playouts from that state end within 500 steps, no exception, legal moves only;
  4. (extra) when the state tells whose turn it is, it is the sample's seat (0).
verify() runs in-process; verify_isolated() runs it in a child process with a hard timeout (generated code can loop).
"""
import multiprocessing as mp
import random
import time

PLAYOUTS = 200
MAX_STEPS = 500


def verify_report(sim, variant, deadline_s=8.0, seed=7):
    """Return (ok: bool, reason: str)."""
    try:
        if sim is None:
            return False, "no simulator"
        sample = (variant or {}).get("sample_turn")
        if not isinstance(sample, dict) or not isinstance(sample.get("observation"), str):
            return False, "no sample_turn"
        seat = sample.get("seat", 0)
        seat = seat if isinstance(seat, int) else 0
        if not sim.can_parse:
            return False, "simulator has no parse(observation, seat)"
        state = sim.parse(sample["observation"], seat)
        if sim.is_terminal(state):
            return False, "parsed state is terminal at a sample turn"
        legal = sim.legal(state)
        want = sample.get("legal_actions")
        if isinstance(want, list) and set(legal) != {str(a) for a in want}:
            return False, f"legal set differs ({len(legal)} vs {len(want)})"
        if not legal:
            return False, "no legal move at a sample turn"
        if callable(getattr(sim, "to_move", None)):
            try:
                if sim.to_move(state) != seat:
                    return False, "parsed state is not the sample seat's turn"
            except Exception as e:
                return False, f"to_move failed: {e}"
        rng = random.Random(seed)
        t_end = time.monotonic() + deadline_s
        for _ in range(PLAYOUTS):
            s, steps = state, 0
            while not sim.is_terminal(s):
                ms = sim.legal(s)
                if not ms:
                    break  # stuck without moves: allowed (acts as terminal)
                s = sim.apply(s, rng.choice(ms))
                steps += 1
                if steps > MAX_STEPS:
                    return False, f"playout longer than {MAX_STEPS} steps"
            if time.monotonic() > t_end:
                return False, "playouts too slow"
        return True, "ok"
    except Exception as e:  # any exception = not verified
        return False, f"{type(e).__name__}: {str(e)[:100]}"


def verify(sim, variant):
    return verify_report(sim, variant)[0]


def _child(path, variant, conn):
    try:
        from solvers.adapter import load_simulator
        sim = load_simulator(path)
        ok, reason = verify_report(sim, variant)
        has_chance = bool(sim.has_chance(sim.parse(variant["sample_turn"]["observation"], 0))) if ok else False
        conn.send({"verified": ok, "reason": reason, "has_chance": has_chance})
    except BaseException as e:
        try:
            conn.send({"verified": False, "reason": f"{type(e).__name__}: {str(e)[:100]}", "has_chance": False})
        except Exception:
            pass


def verify_isolated(path, variant, timeout=20.0):
    """verify() on the simulator file at `path` in a spawned child with a hard timeout -> dict
    {"verified", "reason", "has_chance"}; never raises."""
    try:
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe()
        p = ctx.Process(target=_child, args=(path, variant, child), daemon=True)
        p.start()
        child.close()
        out = parent.recv() if parent.poll(timeout) else {"verified": False, "reason": "timeout", "has_chance": False}
        try:
            if p.is_alive():
                p.kill()
            p.join(1.0)
        except Exception:
            pass
        return out
    except Exception as e:
        return {"verified": False, "reason": f"isolation failed: {type(e).__name__}", "has_chance": False}
