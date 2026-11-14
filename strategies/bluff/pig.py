"""Push-your-luck dice races (Pig): when to roll and when to hold. No I/O.

One roll can add points or wipe the turn. Keep rolling while the expected gain beats the expected loss: with bust
chance p and an average gain g on a good roll, rolling is worth it while  turn_total < g * (1 - p) / p.
One die: p = 1/6, g = 4 -> hold at 20 (the famous "hold at 20"). Two dice: p = 11/36, g = 8 -> about 18.
Race adjustments: always hold when holding wins; roll on when the opponent is about to win.
"""
import re

_TARGET = re.compile(r"target:\s*(\d+)", re.I)
_BANKED = re.compile(r"banked:\s*you\s+(\d+),\s*opponent\s+(\d+)", re.I)
_TOTAL = re.compile(r"turn\s+total:\s*(\d+)", re.I)


def parse(observation):
    """{"target", "mine", "theirs", "total"} (ints, None when missing) from the observation text."""
    obs = observation if isinstance(observation, str) else ""
    t, b, tt = _TARGET.search(obs), _BANKED.search(obs), _TOTAL.search(obs)
    return {"target": int(t.group(1)) if t else None, "mine": int(b.group(1)) if b else None,
            "theirs": int(b.group(2)) if b else None, "total": int(tt.group(1)) if tt else None}


def two_dice(rules):
    low = (rules or "").lower()
    return bool(re.search(r"two\s+dice|2\s+dice|2d6|a\s+pair\s+of\s+dice", low))


def threshold(rules, state):
    """The turn total at which we hold."""
    p, g = (11 / 36, 8.0) if two_dice(rules) else (1 / 6, 4.0)
    thr = round(g * (1 - p) / p)   # 20 for one die, 18 for two dice
    target, mine, theirs = state["target"], state["mine"], state["theirs"]
    if target and theirs is not None and theirs + 12 >= target and (mine or 0) < theirs:
        thr += 10   # the opponent is about to win: a normal turn is not enough
    if target and mine is not None and mine >= target - 8:
        thr = max(0, min(thr, target - mine))   # close to the end: hold as soon as holding wins
    return thr


def decide(rules, observation, legal):
    """"roll" or "hold" (the legal spelling), or None when the observation cannot be read."""
    state = parse(observation)
    if state["total"] is None:
        return None
    roll = next((a for a in legal if a.lower() == "roll"), None)
    hold = next((a for a in legal if a.lower() == "hold"), None)
    if not roll or not hold:
        return None
    if state["total"] == 0:
        return roll                      # holding with nothing banks nothing
    if state["target"] and state["mine"] is not None and state["mine"] + state["total"] >= state["target"]:
        return hold                      # holding wins the game
    return hold if state["total"] >= threshold(rules, state) else roll
