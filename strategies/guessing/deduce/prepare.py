"""prepare(): ask the gateway Haiku (thinking on, 7.3) to write the feedback model from the rules text, verify it, save it.

Only verified code is ever used (strategies/guessing/deduce/__init__.py checks artifacts["prepared"]["deduce"]["verified"]).
Game content (rules, sample turn) goes to the gateway only (7.7, 7.11).
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time

from strategies.guessing.deduce import model as fm

PROMPT = """You write small, pure-Python helpers for a bot that plays a GUESSING game (the bot tries to find a hidden \
secret using feedback after each guess). Read the rules and the sample observation, then write these module-level functions:

candidate_space(variant) -> iterable of hashable secrets: every value the secret can take = every legal guess. \
`variant` is a dict; variant["rules"] holds the rules text (parse the ranges/lengths from it with `re`).
extract_history(observation) -> list of (guess, feedback) for OUR OWN guesses so far, oldest first, exactly as the \
observation text reports them (ignore the opponent's guesses at our secret). `guess` must be a member of candidate_space; \
`feedback` any hashable value (e.g. the word or a tuple of counts).
feedback(secret, guess) -> the feedback the game would give for `guess` if the hidden secret were `secret`; the SAME form \
and values extract_history returns, so that feedback(true_secret, g) == the feedback printed in the observation.
format_guess(guess) -> the action string to send, exactly in the rules' action format (one line).
max_guesses(variant) -> int, the rules' limit on how many guesses we get (None if unlimited).

Rules: standard library only, and only these imports: re, math, itertools, collections, functools, string. No files, no \
network, no printing, no global state. Fast: feedback() is called millions of times. Reply with ONE ```python code block and \
nothing else."""


def _extract_code(text):
    if not text:
        return None
    try:  # canned/JSON answers: {"code": "..."}
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and isinstance(obj.get("code"), str):
                return obj["code"]
    except ValueError:
        pass
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    return text if "def feedback" in text else None


def _save(directory, code):
    """Atomic write of the verified code under /memory/<game_id>/<rules_hash>/ (5.14)."""
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "feedback_model.py")
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        os.replace(tmp, path)
        return path
    except Exception:
        return None


def prepare(rules, variant, llm, deadline):
    """-> {"verified": bool, "reason": str, ["code", "path", "sha", stats...]}. Never raises."""
    t0 = time.monotonic()
    try:
        variant = dict(variant or {})
        variant.setdefault("rules", rules)
        sample = variant.get("sample_turn")
        if not isinstance(sample, dict):
            return {"verified": False, "reason": "no sample_turn to verify against"}
        if llm is None or not llm.available():
            return {"verified": False, "reason": "no llm in prep"}
        legal = sample.get("legal_actions")
        user = (f"RULES:\n{str(rules)[:9000]}\n\nSAMPLE OBSERVATION (a real turn):\n{str(sample.get('observation', ''))[:4000]}\n\n"
                f"SAMPLE LEGAL ACTIONS: {json.dumps(legal[:8]) if isinstance(legal, list) else 'null (more than 50 moves)'}")
        why = "no answer"
        for attempt in (1, 2):
            left = deadline - time.monotonic()
            if left < 20:
                return {"verified": False, "reason": f"no prep time left ({why})"}
            ask = user if attempt == 1 else user + f"\n\nYour previous code failed verification: {why}. Fix it."
            text = llm.ask(PROMPT, ask, prep=True, timeout=min(75.0, left - 10), budget=1500, max_tokens=5000)
            code = _extract_code(text)
            if not code:
                why = "no code in the answer"
                continue
            ok, why, stats = fm.verify_isolated(code, variant, timeout=min(45.0, max(5.0, deadline - time.monotonic() - 5)))
            if ok:
                res = {"verified": True, "reason": "ok", "code": code, "sha": hashlib.sha1(code.encode()).hexdigest()[:12],
                       "path": _save(variant.get("memory_dir") or "", code) if variant.get("memory_dir") else None,
                       "attempt": attempt, "secs": round(time.monotonic() - t0, 1)}
                res.update(stats)
                return res
            print(f"deduce.prepare: attempt {attempt} failed verification: {why}", file=sys.stderr, flush=True)
        return {"verified": False, "reason": why}
    except BaseException as e:
        return {"verified": False, "reason": f"{type(e).__name__}: {str(e)[:100]}"}
