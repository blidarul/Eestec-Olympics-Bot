"""Feedback model of a guessing game: load, run and VERIFY code written by Haiku during prep (7.7: the gateway Haiku only).

The code (see PROMPT in prepare.py) defines, from the rules text only:
    candidate_space(variant) -> iterable of hashable secrets (= the set of legal guesses)
    extract_history(observation) -> [(guess, feedback), ...]  our guesses so far with the feedback the observation reports
    feedback(secret, guess) -> feedback, in the same form extract_history returns
    format_guess(guess) -> the action string to send
    max_guesses(variant) -> int | None   the rules' limit on our guesses (None = no limit)
It is exec'd with a small import whitelist and builtins without open/eval/exec: no file, no network (7.11).
A model is trusted ONLY after verify_model() (isolated in a child process with a hard timeout) passes.
"""
import builtins
import hashlib
import random
import time

from solvers.deduction import best_split

SAFE_MODULES = {"re", "math", "itertools", "collections", "functools", "string", "fractions", "operator"}
_BAD_BUILTINS = {"open", "eval", "exec", "compile", "input", "breakpoint", "exit", "quit", "help", "globals",
                 "locals", "vars", "memoryview", "__loader__"}
MAX_SPACE = 200_000
SIM_SECRETS = 50
REQUIRED = ("candidate_space", "extract_history", "feedback", "format_guess")


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in SAFE_MODULES:
        raise ImportError(f"import of {name!r} is not allowed")
    return builtins.__import__(name, globals, locals, fromlist, level)


class Model:
    def __init__(self, code):
        self.sha = hashlib.sha1(code.encode("utf-8", "replace")).hexdigest()[:12]
        safe = {k: v for k, v in vars(builtins).items() if k not in _BAD_BUILTINS}
        safe["__import__"] = _safe_import
        ns = {"__builtins__": safe, "__name__": "feedback_model"}
        exec(compile(code, "feedback_model", "exec"), ns)
        for n in REQUIRED:
            if not callable(ns.get(n)):
                raise ValueError(f"model lacks {n}()")
        self._ns = ns

    def space(self, variant):
        out = []
        for c in self._ns["candidate_space"](variant):
            out.append(c)
            if len(out) > MAX_SPACE:
                raise ValueError("candidate space too large")
        hash(out[0] if out else 0)
        return out

    def history(self, observation):
        h = [tuple(p) for p in self._ns["extract_history"](observation)]
        if any(len(p) != 2 for p in h):
            raise ValueError("history items must be (guess, feedback)")
        return h

    def feedback(self, secret, guess):
        return self._ns["feedback"](secret, guess)

    def format(self, guess):
        out = self._ns["format_guess"](guess)
        if not isinstance(out, str) or not out.strip() or len(out) > 120 or "\n" in out:
            raise ValueError("format_guess must return a short one-line string")
        return out.strip()

    def max_guesses(self, variant):
        f = self._ns.get("max_guesses")
        if not callable(f):
            return None
        n = f(variant)
        return int(n) if isinstance(n, (int, float)) and n > 0 else None


_MODELS = {}


def get_model(code):
    m = _MODELS.get(code)
    if m is None:
        if len(_MODELS) > 8:
            _MODELS.clear()
        m = _MODELS[code] = Model(code)
    return m


def choose_guess(model, cands, deadline, pool_n=300, probe_n=400):
    """The guess with the best worst-case split of `cands` (solvers/deduction.py); a candidate on ties."""
    if len(cands) <= 2:
        return cands[0]
    pool = cands if len(cands) <= pool_n else random.sample(cands, pool_n)
    return best_split(cands, pool, model.feedback, deadline=deadline, sample=probe_n)


def verify_model(code, variant, seed=11, sims=SIM_SECRETS):
    """Return (ok, reason, stats). `variant`: the prep variant (rules, sample_turn)."""
    t0 = time.monotonic()
    try:
        m = Model(code)
        sample = variant.get("sample_turn")
        if not isinstance(sample, dict) or not isinstance(sample.get("observation"), str):
            return False, "no sample_turn", {}
        space = m.space(variant)
        if len(space) < 2:
            return False, "candidate space has fewer than 2 candidates", {}
        sset = set(space)
        hist = m.history(sample["observation"])
        obs = sample.get("observation", "")
        if not hist:
            obs_lower = obs.lower()
            if "->" in obs or "you guessed" in obs_lower or ("round 1:" in obs_lower and "(none yet)" not in obs_lower):
                return False, "extract_history found nothing in the sample turn", {}
        else:
            for g, _ in hist:
                if g not in sset:
                    return False, f"sample guess {g!r} not in candidate_space", {}
            if not [c for c in space if all(m.feedback(c, g) == fb for g, fb in hist)]:
                return False, "feedback() contradicts the sample turn's real feedback", {}
        legal = sample.get("legal_actions")
        legal = {str(a) for a in legal} if isinstance(legal, list) else None
        cap = m.max_guesses(variant) or 2 * len(bin(len(space))) + 8
        rng = random.Random(seed)
        random.seed(seed)
        used = []
        for _ in range(sims):
            secret = rng.choice(space)
            cands, seen, solved = list(space), set(), None
            for k in range(1, cap + 1):
                g = choose_guess(m, cands, time.monotonic() + 0.2, pool_n=40, probe_n=120)
                if g not in sset:
                    return False, f"guess {g!r} is not in candidate_space", {}
                a = m.format(g)
                if g in seen or (legal is not None and a not in legal):
                    return False, f"illegal or repeated guess {a!r}", {}
                seen.add(g)
                if g == secret:
                    solved = k
                    break
                fb = m.feedback(secret, g)
                cands = [c for c in cands if m.feedback(c, g) == fb]
                if secret not in cands:
                    return False, "feedback() is not consistent with itself", {}
            if solved is None:
                return False, f"secret {secret!r} not found within {cap} guesses", {}
            used.append(solved)
        return True, "ok", {"space": len(space), "cap": cap, "avg_guesses": round(sum(used) / len(used), 2),
                            "max_guesses_used": max(used), "secs": round(time.monotonic() - t0, 2)}
    except BaseException as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}", {}


def child_verify(args):
    """Entry point of solvers.isolated: {"code", "variant"} -> {"ok", "reason", "stats"}."""
    try:
        ok, why, stats = verify_model(args["code"], args["variant"])
        return {"ok": ok, "reason": why, "stats": stats}
    except BaseException as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:100]}", "stats": {}}


def verify_isolated(code, variant, timeout=40.0):
    """verify_model() in a child interpreter with a hard timeout (generated code may loop): (ok, reason, stats)."""
    from solvers.isolated import run_isolated
    out = run_isolated("strategies.guessing.deduce.model", "child_verify", {"code": code, "variant": variant}, timeout)
    if not isinstance(out, dict):
        return False, "verification timeout or crash", {}
    return bool(out.get("ok")), str(out.get("reason")), out.get("stats") or {}
