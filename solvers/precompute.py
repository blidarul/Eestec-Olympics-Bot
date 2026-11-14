"""Layer 2, phase L1: cheap deterministic facts computed before the model call.

precompute(observation, legal_actions, artifacts, rules, deadline) -> Facts

Library only: imports nothing from core/, prep/, chat/ or strategies/. It sees the observation, the legal
actions, the artifacts and the rules text, never the opponent's chat (rules 6.5, 6.7). It never raises, writes
nothing to stdout, and spends at most ~300 ms in total. A "certain" move is only a suggestion: the caller
validates it like any other move.
"""
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import solvers  # noqa: F401  (registers the tools)
from solvers import catalog

TOTAL_MS = 300
MAX_TEXT = 12000


@dataclass
class Facts:
    lines: list = field(default_factory=list)   # short sentences for the prompt
    certain: Optional[dict] = None              # {"move": str, "why": str, "tool": str}
    used: list = field(default_factory=list)    # tool names that produced facts
    ms: int = 0


def _log(msg):
    try:
        print("[precompute] " + msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass


def _call(name, args, deadline):
    """catalog.call, returning the result dict or None."""
    r = catalog.call(name, args, deadline)
    if isinstance(r, dict) and r.get("ok") and isinstance(r.get("result"), dict):
        return r["result"]
    return None


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _legal_map(legal):
    """normalized legal action -> original string (first wins)."""
    out = {}
    for a in legal or []:
        out.setdefault(_norm(a), a)
    return out


def _set_certain(facts, move, why, tool):
    if facts.certain is None:
        facts.certain = {"move": move, "why": why, "tool": tool}


# ------------------------------------------------------------------ board

_WORD_NUM = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_K_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s*(?:-|\s)?(?:in\s*(?:a\s*)?(?:row|line)|consecutive|connected)", re.I),
    re.compile(r"\b(three|four|five|six|seven)\s*(?:-|\s)?(?:in\s*(?:a\s*)?(?:row|line)|consecutive)", re.I),
    re.compile(r"connect[\s-]*(\d{1,2}|three|four|five|six|seven)\b", re.I),
    re.compile(r"\b(?:line|row|run|streak) of (\d{1,2}|three|four|five|six|seven)\b", re.I),
)


def _find_k(rules, artifacts):
    k = artifacts.get("k") if isinstance(artifacts, dict) else None
    if isinstance(k, int) and not isinstance(k, bool) and 2 <= k <= 12:
        return k
    for rx in _K_PATTERNS:
        m = rx.search(rules or "")
        if m:
            g = m.group(1).lower()
            v = _WORD_NUM.get(g)
            if v is None and g.isdigit():
                v = int(g)
            if v and 2 <= v <= 12:
                return v
    return None


def _cell_names(r, c, rows, cols, grid):
    """Candidate spellings of cell (r, c), most specific first."""
    names = []
    rl, cl = grid.get("row_labels"), grid.get("col_labels")
    if rl and cl and r < len(rl) and c < len(cl):
        names += [str(cl[c]) + str(rl[r]), str(rl[r]) + str(cl[c]), "%s,%s" % (rl[r], cl[c]), "%s %s" % (rl[r], cl[c])]
        return names                      # the board's own labels are authoritative
    if cols <= 26:
        names.append(chr(65 + c) + str(r + 1))
        names.append(chr(65 + c) + str(rows - r))
    names += ["%d,%d" % (r, c), "%d,%d" % (r + 1, c + 1), "%d %d" % (r, c), "%d %d" % (r + 1, c + 1),
              str(r * cols + c), str(r * cols + c + 1)]
    return names


def _cell_to_legal(cell, rows, cols, grid, lmap, style_first):
    """Map board_lines 'r,c' cell name to a legal action, or None. Uses the grid's own style first."""
    try:
        r, c = (int(x) for x in str(cell).split(","))
    except ValueError:
        return None
    cands = _cell_names(r, c, rows, cols, grid)
    found = []
    for n in cands:
        a = lmap.get(_norm(n))
        if a is not None and a not in found:
            found.append(a)
    # Ambiguity (e.g. "0,0" vs "1,1" both legal) cannot be resolved here: only accept a unique hit.
    return found[0] if len(found) == 1 else None


def _my_symbol(observation, artifacts, symbols):
    for key in ("my_symbol", "symbol", "me"):
        v = artifacts.get(key) if isinstance(artifacts, dict) else None
        if isinstance(v, str) and v in symbols:
            return v
    for m in re.finditer(
            r"\byou(?:'re|\s+are|\s+play|\s+playing|\s+will\s+play)?\s+(?:as\s+)?(?:the\s+)?(?:player\s+)?['\"(]?([A-Za-z0-9])['\"):]?(?![A-Za-z0-9])",
            observation or "", re.I):
        if m.group(1) in symbols:
            return m.group(1)
    for m in re.finditer(r"\byou\b[^.\n]{0,30}?\bplay\s+['\"]?([A-Za-z0-9])(?![A-Za-z0-9])", observation or "", re.I):
        if m.group(1) in symbols:
            return m.group(1)
    for m in re.finditer(r"\b(?:your|you have)\s+(?:symbol|mark|piece|stone|colou?r)s?\s*(?:is|are|:)?\s*['\"]?([A-Za-z0-9])\b",
                         observation or "", re.I):
        if m.group(1) in symbols:
            return m.group(1)
    return None


def _board(observation, legal, artifacts, rules, deadline, facts):
    k = _find_k(rules, artifacts)
    if k is None:
        return
    g = _call("extract_grid", {"text": observation}, deadline)
    if not g or not g.get("found") or not g.get("grids"):
        return
    grid = g["grids"][0]
    rows_s = grid["rows"]
    rows, cols = len(rows_s), len(rows_s[0])
    if k > max(rows, cols):
        return
    syms = grid.get("symbols") or {}
    empty = None
    for e in (".", "-", "_", " ", "0", "·"):
        if e in syms:
            empty = e
            break
    if empty is None:
        return
    players = [s for s in syms if s != empty]
    if not 1 <= len(players) <= 6 or any(len(s) != 1 for s in players):
        return
    # Some games list only one symbol so far: add the missing opponent from the rules if possible.
    if len(players) == 1:
        return
    res = _call("board_lines", {"board": rows_s, "k": k, "players": players, "empty": empty, "coord_style": "rc"},
                deadline)
    if not res or "players" not in res:
        return
    facts.used.append("board_lines")
    me = _my_symbol(observation, artifacts, players)
    lmap = _legal_map(legal)

    def show(cells):
        out = []
        for c in cells[:4]:
            out.append(_cell_to_legal(c, rows, cols, grid, lmap, True) or ("cell " + str(c)))
        return ", ".join(out)

    for p in players:
        e = res["players"].get(p) or {}
        w = e.get("winning_moves") or []
        if w:
            who = "You (%s)" % p if p == me else ("Opponent (%s)" % p if me else "Player %s" % p)
            facts.lines.append("%s can win immediately at: %s." % (who, show(w)))
        n1 = e.get("open_lines_k_minus_1", 0)
        n2 = e.get("open_lines_k_minus_2", 0)
        if (n1 or n2) and len(facts.lines) < 6:
            who = "you" if p == me else ("opponent" if me else p)
            facts.lines.append("Open lines for %s: %d one short, %d two short." % (who, n1, n2))
    if me is None or len(players) != 2:
        return
    opp = players[0] if players[1] == me else players[1]
    mine = (res["players"].get(me) or {}).get("winning_moves") or []
    theirs = (res["players"].get(opp) or {}).get("winning_moves") or []
    if res["players"].get(me, {}).get("has_won") or res["players"].get(opp, {}).get("has_won"):
        return
    for cell in mine:
        a = _cell_to_legal(cell, rows, cols, grid, lmap, True)
        if a is not None:
            _set_certain(facts, a, "immediate win", "board_lines")
            return
    if len(theirs) == 1:
        a = _cell_to_legal(theirs[0], rows, cols, grid, lmap, True)
        if a is not None:
            _set_certain(facts, a, "forced block of the opponent's only immediate win", "board_lines")


# ------------------------------------------------------------------ guessing

_HIGHER = ("higher", "greater", "bigger", "too low", "larger", "go up", "up")
_LOWER = ("lower", "smaller", "too high", "less", "go down", "down")
_CORRECT = ("correct", "right", "win", "found", "exact")


def _fb(s):
    if not isinstance(s, str):
        return None
    t = s.lower()
    for w in ("too low", "too high"):
        if w in t:
            return "higher" if w == "too low" else "lower"
    for w, tag in (("higher", "higher"), ("greater", "higher"), ("bigger", "higher"), ("larger", "higher"),
                   ("lower", "lower"), ("smaller", "lower"), ("correct", "correct"), ("exact", "correct")):
        if w in t:
            return tag
    t = t.strip(" .!")
    if t in ("up", "more"):
        return "higher"
    if t in ("down", "less"):
        return "lower"
    if t in ("right", "win", "found"):
        return "correct"
    return None


_RANGE = (
    re.compile(r"between\s+(-?\d+)\s+and\s+(-?\d+)", re.I),
    re.compile(r"from\s+(-?\d+)\s+(?:to|through|up to)\s+(-?\d+)", re.I),
    re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]"),
    re.compile(r"\b(-?\d+)\s*(?:\.\.|-|to)\s*(-?\d+)\b", re.I),
)


def _find_range(rules, artifacts):
    lo, hi = (artifacts or {}).get("lo"), (artifacts or {}).get("hi")
    if isinstance(lo, int) and isinstance(hi, int) and lo <= hi:
        return lo, hi
    for rx in _RANGE:
        for m in rx.finditer(rules or ""):
            a, b = int(m.group(1)), int(m.group(2))
            if a < b and b - a >= 3:
                return a, b
    return None


def _guessing(observation, legal, artifacts, rules, deadline, facts):
    low = (rules or "").lower()
    if "guess" not in low:
        return
    if not re.search(r"higher|lower|too high|too low|greater|smaller", low + " " + (observation or "").lower()):
        return
    rng = _find_range(rules, artifacts)
    if rng is None:
        return
    h = _call("extract_history", {"text": observation}, deadline) or {}
    hist = []
    for e in h.get("history") or []:
        fb = _fb(e.get("feedback"))
        v = e.get("value")
        if e.get("actor") in (None, "you") and isinstance(v, int) and not isinstance(v, bool) and fb:
            hist.append({"guess": v, "feedback": fb})
    res = _call("binary_search_next", {"lo": rng[0], "hi": rng[1], "history": hist[-60:]}, deadline)
    if not res:
        return
    facts.used.append("binary_search_next")
    if res.get("found"):
        return
    made = sorted({e["guess"] for e in hist})
    cand = res.get("candidates")
    facts.lines.append("The number is in %s..%s (%s candidates left); best next guess: %s." % (
        res.get("lo"), res.get("hi"), cand, res.get("next_guess")))
    if made:
        facts.lines.append("Guesses already made (never repeat): %s." % ", ".join(map(str, made[-12:])))
    if cand == 1 or res.get("lo") == res.get("hi"):
        move = str(res.get("lo"))
        lmap = _legal_map(legal)
        a = lmap.get(_norm(move)) if legal else None
        if a is None and legal:
            for x in legal:                       # "guess 42" style actions
                if re.fullmatch(r"\D*%s\D*" % re.escape(move), x):
                    a = x
                    break
        if a is not None and int(move) not in made:
            _set_certain(facts, a, "only one candidate left", "binary_search_next")


# ------------------------------------------------------------------ deduction (pegs / positional)

_LEN_RX = re.compile(r"\b(\d{1,2}|three|four|five|six|seven|eight)[- ](?:digit|letter|peg|colou?r|symbol|character|position)s?\b", re.I)
_LEN_W = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_PEG_KW = re.compile(r"\b(bulls?|cows?|mastermind|exact(?:ly)? (?:match|position)|correct (?:digit|colou?r|symbol|peg)s?|"
                     r"right (?:digit|colou?r) in the (?:right|wrong) place|in the (?:right|correct|wrong) (?:place|position))", re.I)
_POS_KW = re.compile(r"\b(green|yellow|gr[ae]y|wordle|correct letter in the correct (?:place|position)|right letter)", re.I)
_NOREP = re.compile(r"no repe|without repe|distinct|all different|unique|no duplicate|no digit .{0,12}twice", re.I)


def _deduce_alphabet(low):
    m = re.search(r"\b([a-z])\s*(?:-|to|through)\s*([a-z])\b", low)
    if m and ord(m.group(2)) - ord(m.group(1)) in range(2, 26) and re.search(r"letter|colou?r|symbol", low):
        return "".join(chr(c) for c in range(ord(m.group(1)), ord(m.group(2)) + 1))
    if re.search(r"\b0\s*(?:-|to|through)\s*9\b|digits?", low):
        return "0123456789"
    m = re.search(r"\b1\s*(?:-|to|through)\s*([2-9])\b", low)
    if m and re.search(r"digit|number|colou?r|peg", low):
        return "".join(str(i) for i in range(1, int(m.group(1)) + 1))
    return None


def _deduce(observation, legal, artifacts, rules, deadline, facts):
    low = (rules or "").lower()
    if not re.search(r"secret|hidden|code|guess", low):
        return
    if facts.used and "binary_search_next" in facts.used:
        return
    fm = artifacts.get("feedback_model") if isinstance(artifacts, dict) else None
    kind = None
    if fm is None:
        if _PEG_KW.search(rules or "") or ("exact" in low and re.search(r"partial|misplaced|wrong (?:place|position)", low)):
            kind = "pegs"
        elif _POS_KW.search(rules or ""):
            kind = "positional"
        else:
            return
        ml = _LEN_RX.search(rules or "")
        if not ml:
            return
        n = ml.group(1).lower()
        length = int(n) if n.isdigit() else _LEN_W.get(n)
        if not length:
            return
        params = {"length": length}
        if kind == "pegs":
            alpha = _deduce_alphabet(low)
            if alpha is None:
                return
            params.update(alphabet=alpha, repeat=not _NOREP.search(rules or ""))
        else:
            words = artifacts.get("words") if isinstance(artifacts, dict) else None
            if not (isinstance(words, list) and words):
                return                     # no word list: a 26^L space is not enumerable, leave it to the model
            params["words"] = [w for w in words if isinstance(w, str)][:20000]
    else:
        params = {}
    h = _call("extract_history", {"text": observation}, deadline) or {}
    hist = []
    for e in h.get("history") or []:
        if e.get("actor") in (None, "you") and e.get("value") is not None and e.get("feedback"):
            g = str(e["value"])
            if kind == "pegs" and g.isdigit() and len(g) < params["length"]:
                g = g.zfill(params["length"])          # leading zeros lost by number parsing
            hist.append({"guess": g, "feedback": str(e["feedback"])})
    if fm is not None:
        from solvers.deduce import deduce
        res = deduce("custom", {}, hist[-60:], "minimax", deadline, feedback_model=fm)
    else:
        res = _call("deduce_next", {"model": kind, "params": params, "history": hist[-60:], "mode": "entropy"}, deadline)
    if not res or res.get("contradictory_history") or not res.get("candidates"):
        return
    facts.used.append("deduce_next")
    left = res["candidates"]
    facts.lines.append("%s candidate%s consistent with all feedback so far; best next guess: %s." % (
        left, "" if left == 1 else "s", res.get("next_guess_text")))
    if res.get("guesses_made"):
        facts.lines.append("Guesses already made (never repeat): %s." % ", ".join(
            str(x["guess"]) for x in hist[-12:]))
    if res.get("certain") and legal:
        a = _legal_map(legal).get(_norm(res.get("next_guess_text")))
        if a is None:
            for x in legal:
                if _norm(res.get("next_guess_text")) and _norm(res["next_guess_text"]) in _norm(x):
                    a = x
                    break
        if a is not None:
            _set_certain(facts, a, "only one candidate left", "deduce_next")


# ------------------------------------------------------------------ dice

_DICE_NDM = re.compile(r"\b(\d{1,2})\s*d\s*(\d{1,3})\b", re.I)
_DICE_N = re.compile(r"\b(\d{1,2}|one|two|three|four|five|six)\s+(?:(\d{1,3})[- ]sided\s+|six[- ]sided\s+|fair\s+|standard\s+)?dice\b",
                     re.I)
_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def _dice(observation, legal, artifacts, rules, deadline, facts):
    text = (rules or "") + "\n" + (observation or "")
    if not re.search(r"\bdice\b|\bdie\b|\bd\d+\b|\broll", text, re.I):
        return
    faces = []
    m = _DICE_NDM.search(text)
    if m:
        faces = [int(m.group(2))] * int(m.group(1))
    else:
        m = _DICE_N.search(text)
        if m:
            n = _NUMW.get(m.group(1).lower()) or int(m.group(1))
            s = int(m.group(2)) if m.group(2) else 6
            faces = [s] * n
        elif re.search(r"\b(?:a|one|the|your)\s+(?:six[- ]sided\s+)?die\b|\bd6\b", text, re.I):
            faces = [6]
    if not faces or len(faces) > 8 or any(f < 2 for f in faces):
        return
    args = {"dice": faces}
    tm = re.search(r"\b(?:target|reach|at least|exactly|or more|total of|sum of)\s*(\d{1,3})\b", text, re.I)
    if tm:
        args["target"] = int(tm.group(1))
    res = _call("dice_sum_distribution", args, deadline)
    if not res:
        return
    facts.used.append("dice_sum_distribution")
    s = "Dice %s: expected sum %s, most likely sum %s." % ("+".join("d%d" % f for f in faces),
                                                          res.get("expected_value_decimal"), res.get("most_likely_sum"))
    for key, label in (("p_sum_ge_target_decimal", "P(sum>=%s)"), ("p_sum_eq_target_decimal", "P(sum==%s)")):
        if key in res and "target" in args:
            s += " " + (label % args["target"]) + "=%s." % res[key]
    facts.lines.append(s)


# ------------------------------------------------------------------ payoff matrix

def _matrix(observation, legal, artifacts, rules, deadline, facts):
    mat = None
    if isinstance(artifacts, dict):
        for key in ("payoff", "payoff_matrix", "matrix"):
            if isinstance(artifacts.get(key), list):
                mat = artifacts[key]
                break
    if not mat or not all(isinstance(r, list) and r for r in mat):
        return
    args = {"matrix": mat}
    if isinstance(artifacts.get("row_labels"), list):
        args["row_labels"] = artifacts["row_labels"]
    if isinstance(artifacts.get("col_labels"), list):
        args["col_labels"] = artifacts["col_labels"]
    res = _call("matrix_nash", args, deadline)
    if not res:
        return
    facts.used.append("matrix_nash")
    mix = ", ".join("%s %.2f" % (x.get("label"), x.get("p_decimal", 0)) for x in res.get("row_strategy") or []
                    if x.get("p_decimal", 0) > 0)
    facts.lines.append("Equilibrium mix for you: %s (value %s)." % (mix, res.get("value_decimal")))


# ------------------------------------------------------------------ nim

_HEAP_LIST = re.compile(r"(?:heaps?|piles?|stacks?)\b[^\n\d\[]{0,25}[:=]?\s*\[?\s*(\d+(?:\s*[,\s]\s*\d+)+)\s*\]?", re.I)
_HEAP_ONE = re.compile(r"(?:heap|pile|stack)\s*#?(\d+)\s*[:=(]\s*(\d+)", re.I)


def _heaps(observation):
    m = _HEAP_LIST.search(observation or "")
    if m:
        vals = [int(x) for x in re.findall(r"\d+", m.group(1))]
        if 1 <= len(vals) <= 12:
            return vals, None
    items = _HEAP_ONE.findall(observation or "")
    if len(items) >= 2:
        labels = [int(a) for a, _ in items]
        return [int(b) for _, b in items], labels[0]
    return None, None


def _nim(observation, legal, artifacts, rules, deadline, facts):
    low = (rules or "").lower()
    if not re.search(r"\b(?:heap|pile|stack)s?\b", low) or not re.search(r"\b(?:remove|take|pick)\b", low):
        return
    heaps, first_label = _heaps(observation)
    if not heaps or any(h > 200 for h in heaps):
        return
    misere = bool(re.search(r"mis[eè]re|last (?:player|one|stone|object|item)[^.]{0,30}(?:loses|lose)|"
                            r"(?:takes|take|taking|removes)[^.]{0,25}last[^.]{0,25}(?:loses|lose)", low))
    limit = re.search(r"(?:at most|up to|no more than|maximum of)\s*(\d+)", low)
    removals = "any"
    if limit:
        removals = list(range(1, int(limit.group(1)) + 1))
    args = {"heaps": heaps, "removals": removals, "misere": misere}
    res = _call("nim_analysis", args, deadline)
    if not res:
        return
    facts.used.append("nim_analysis")
    facts.lines.append("Heaps %s: nim-sum %s, %s." % (heaps, res.get("nim_sum"),
                                                     "you can force a win" if res.get("first_player_wins") else
                                                     "no winning move exists (play small, hope for a mistake)"))
    wm = res.get("winning_move")
    if not wm:
        return
    plain = (removals == "any" and not misere and not re.search(
        r"\b(?:only|exactly|must|except|either|power of|even|odd|prime|fibonacci)\b", low))
    heap_label = wm["heap"] + (first_label if first_label is not None else 1)
    facts.lines.append("Winning move: take %d from heap %d (numbering %s)." % (
        wm["remove"], heap_label, "as in the observation" if first_label is not None else "from 1"))
    if not (plain and legal):
        return
    rem = wm["remove"]
    offsets = [first_label] if first_label is not None else [1, 0]
    hits = []
    for a in legal:
        t = str(a)
        m1 = re.search(r"(\d+)\D+?(?:from|of|in|off)\D{0,8}?(\d+)", t, re.I)
        m2 = re.search(r"(?:heap|pile|stack)\D{0,3}(\d+)\D+(\d+)", t, re.I)
        nums = [int(x) for x in re.findall(r"\d+", t)]
        pair = None
        if m1 and len(nums) == 2:
            pair = (int(m1.group(2)), int(m1.group(1)))      # (heap, remove)
        elif m2 and len(nums) == 2:
            pair = (int(m2.group(1)), int(m2.group(2)))
        elif len(nums) == 2:
            pair = (nums[0], nums[1])
        if pair and any(pair == (wm["heap"] + o, rem) for o in offsets):
            hits.append(a)
    if len(hits) == 1:
        _set_certain(facts, hits[0], "nim-sum winning move", "nim_analysis")


# ------------------------------------------------------------------ entry point

# ------------------------------------------------------------------ classic solvers (layer 3, M2)

def _classic(observation, legal, artifacts, rules, deadline, facts):
    from solvers import classic
    skip = []
    if "nim_analysis" in facts.used:
        skip.append("subtraction")
    if "binary_search_next" in facts.used:
        skip.append("range_guess")
    for r in classic.run(observation, legal, rules, artifacts, deadline, skip=skip):
        name = r["solver"]
        facts.used.append(name + "_solve")
        facts.lines.append("%s (%s)%s." % (r.get("why"), name, " -> " + str(r["move"]) if r.get("move") else ""))
        if r.get("move") and r.get("proven") and r.get("value") in (1, 0, None):
            _set_certain(facts, r["move"], r.get("why") or name, name + "_solve")


# ------------------------------------------------------------------ opponent reading (layer 3, M3)

_BEATS = re.compile(r"([A-Za-z][\w-]{1,20})\s+(?:beats|defeats|crushes|covers|cuts|smashes|wins against|wins over)\s+"
                    r"([A-Za-z][\w-]{1,20})", re.I)
_SIMUL = re.compile(r"simultaneous|at the same time|both (?:players )?(?:choose|pick|play|submit|reveal)|"
                    r"without (?:knowing|seeing)|(?:then|are) revealed", re.I)
_COOP = re.compile(r"cooperat|defect|betray|prisoner", re.I)


def _histories(observation, artifacts, legal, deadline):
    opp = artifacts.get("opponent_history")
    mine = artifacts.get("my_history")
    if isinstance(opp, list) and isinstance(mine, list):
        return [str(x) for x in opp], [str(x) for x in mine]
    res = _call("extract_history", {"text": observation}, deadline)
    opp, mine = [], []
    for e in (res or {}).get("history") or []:
        v = str(e.get("value") or "").strip()
        if e.get("actor") == "opponent":
            opp.append(v)
        elif e.get("actor") == "you":
            mine.append(v)
    return opp, mine


def _opponent(observation, legal, artifacts, rules, deadline, facts):
    team = artifacts.get("opponent") or artifacts.get("opponent_id")
    if isinstance(team, str) and team:
        try:
            from solvers import opponent as _op
            line = _op.profile_summary(_op.load_profile(team))
            if line:
                facts.lines.append(line)
                facts.used.append("profile_store")
        except Exception as exc:  # noqa: BLE001
            _log("profile failed: %s" % exc)
    if not _SIMUL.search(rules or "") and not _COOP.search(rules or ""):
        return
    if not legal or not 2 <= len(legal) <= 12:
        return
    opp, mine = _histories(observation, artifacts, legal, deadline)
    lmap = {_norm(a): a for a in legal}
    if _COOP.search(rules or ""):
        names = [a for a in legal if re.match(r"(?i)(coop|defect|betray|cheat|share|trust|c$|d$)", a.strip())]
        if len(names) == 2 and opp:
            cl = next((a for a in names if re.match(r"(?i)(coop|share|trust|c$)", a.strip())), None)
            dl = next((a for a in names if a is not cl), None)
            if cl and dl:
                args = {"opponent_history": opp, "my_history": mine, "cooperate_label": cl, "defect_label": dl}
                lm = re.search(r"(\d{1,3})\s+rounds", rules or "", re.I)
                if lm and len(opp) + 1 <= int(lm.group(1)):
                    args["rounds_left"] = int(lm.group(1)) - len(opp)
                res = _call("reciprocity_policy", args, deadline)
                if res and res.get("action") in legal:
                    facts.used.append("reciprocity_policy")
                    facts.lines.append("Opponent cooperated %.0f%% so far; suggested: %s (%s)." % (
                        100 * res.get("opponent_cooperation_rate", 1.0), res["action"], res.get("reason")))
        return
    if not opp:
        return
    args = {"actions": list(legal), "opponent_history": opp, "my_history": mine}
    mat = None
    for key in ("payoff", "payoff_matrix", "matrix"):
        if isinstance(artifacts.get(key), list):
            mat = artifacts[key]
            break
    if mat:
        args["payoff"] = mat
    else:
        beats = {}
        for a, b in _BEATS.findall(rules or ""):
            if _norm(a) in lmap and _norm(b) in lmap:
                beats.setdefault(lmap[_norm(a)], []).append(lmap[_norm(b)])
        if not beats:
            return
        args["beats"] = beats
    res = _call("opponent_predictor", args, deadline)
    if not res or res.get("action") not in legal:
        return
    facts.used.append("opponent_predictor")
    if res.get("predicted_opponent"):
        facts.lines.append("Opponent looks like %s (confidence %.2f); best response: %s." % (
            res["predicted_opponent"], res.get("confidence", 0), res["action"]))
    else:
        facts.lines.append("Opponent looks random after %d rounds; equilibrium sample: %s." % (len(opp), res["action"]))


# ------------------------------------------------------------------ bluff and chance (layer 3, M4)

_BLUFFY = re.compile(r"bluff|poker|\bpot\b|\bfold\b|\braise\b|liar|challenge|\bbid\b|\bwager|\bante\b", re.I)
_HOLDEM = re.compile(r"hold.?em|community|\bflop\b|\briver\b|5-card|five-card|poker", re.I)
_POT = re.compile(r"\bpot\b\D{0,15}?(\d+(?:\.\d+)?)", re.I)
_TOCALL = re.compile(r"(?:to call|cost to call|call (?:costs|amount)|amount to call)\D{0,10}?(\d+(?:\.\d+)?)|"
                     r"(?:opponent|they|player \d)\s+(?:bets?|raises?)\s+(?:to\s+)?(\d+(?:\.\d+)?)", re.I)
_OURS = re.compile(r"your (?:hand|cards?)|you (?:hold|have|were dealt)|hole cards?|you are holding", re.I)
_TABLE = re.compile(r"board|community|flop|turn|river|table", re.I)
_YDICE = re.compile(r"(?:your|you rolled|you have)\W+(?:dice|rolled)?\W*:?\s*((?:[1-9]\s*[, ]\s*)*[1-9])\b", re.I)
_TDICE = re.compile(r"(?:total dice|dice in play|dice remaining)\D{0,6}(\d+)|(\d+)\s+dice\s+(?:in play|total|remaining|left)", re.I)
_BID = re.compile(r"(?:current\s+)?(?:bid|claim)\w*\D{0,10}?(\d+)\s*(?:x|\u00d7|of|\s)\s*(?:\w+\s)?([1-9])s?\b", re.I)


def _num_of(m):
    g = next((x for x in (m.groups() if m else ()) if x), None)
    return float(g) if g else None


def _chance(observation, legal, artifacts, rules, deadline, facts):
    import zlib
    if not (_BLUFFY.search(rules or "") or _BLUFFY.search(observation)):
        return
    seed = zlib.crc32(observation.encode("utf-8", "ignore")) & 0x7FFFFFFF
    pot = artifacts.get("pot")
    to_call = artifacts.get("to_call")
    if not isinstance(pot, (int, float)):
        pot = _num_of(_POT.search(observation))
    if not isinstance(to_call, (int, float)):
        to_call = _num_of(_TOCALL.search(observation))
    win = artifacts.get("win_prob") if isinstance(artifacts.get("win_prob"), (int, float)) else None
    tie = 0.0
    # Texas-hold'em-like: our cards and the table from the observation text -> Monte Carlo equity.
    if win is None and _HOLDEM.search(rules or ""):
        ours, table = [], []
        for line in observation.split("\n")[:60]:
            if _OURS.search(line) or _TABLE.search(line):
                res = _call("extract_cards", {"text": line}, deadline)
                cards = ["%s%s" % (c["rank"], c["suit"]) for c in (res or {}).get("cards", [])]
                (ours if _OURS.search(line) and not _TABLE.search(line) else table).extend(cards)
        ours, table = list(dict.fromkeys(ours)), [c for c in dict.fromkeys(table) if c not in ours]
        if len(ours) == 2 and len(table) <= 5:
            res = _call("card_equity", {"our_cards": ours, "visible_cards": table, "seed": seed,
                                        "opponents": int(artifacts.get("n_opponents") or 1), "max_samples": 3000}, deadline)
            if res:
                win, tie = res["win"], res["tie"]
                facts.used.append("card_equity")
                facts.lines.append("Win probability %.0f%% (tie %.0f%%) with %s on %s." % (
                    100 * win, 100 * tie, " ".join(ours), " ".join(table) or "an empty board"))
    # Dice-bidding claims.
    dice = artifacts.get("dice") if isinstance(artifacts.get("dice"), list) else None
    total = artifacts.get("total_dice")
    claim = artifacts.get("claim") if isinstance(artifacts.get("claim"), dict) else None
    if dice is None and re.search(r"\bdice\b", rules or "", re.I):
        m = _YDICE.search(observation)
        if m:
            dice = [int(x) for x in re.findall(r"[1-9]", m.group(1))]
    if total is None:
        m = _TDICE.search(observation)
        total = int(next(g for g in m.groups() if g)) if m else None
    if claim is None and dice is not None:
        m = _BID.search(observation)
        if m:
            claim = {"count": int(m.group(1)), "face": int(m.group(2))}
    if dice is not None and isinstance(total, int) and claim:
        wild = [1] if re.search(r"\b(?:ones?|1s)\b[^.\n]{0,30}\bwild|wild[^.\n]{0,30}\b(?:ones?|1s)\b", rules or "", re.I) else []
        args = {"total_dice": total, "our_dice": dice, "claim_count": claim.get("count", 0), "claim_face": claim.get("face", 1),
                "wild_faces": wild}
        res = _call("claim_probability", args, deadline)
        if res:
            facts.used.append("claim_probability")
            facts.lines.append("The claim %sx%s is true with probability %.0f%% (we hold %d matching): %s." % (
                claim.get("count"), claim.get("face"), 100 * res["p_true"], res["our_matching"], res["recommendation"]))
    if win is None:
        return
    if isinstance(pot, (int, float)) and isinstance(to_call, (int, float)) and to_call > 0:
        res = _call("call_ev", {"pot": pot, "to_call": to_call, "win_prob": win, "tie_prob": tie}, deadline)
        if res:
            facts.used.append("call_ev")
            facts.lines.append("Calling needs %.0f%% equity, we have %.0f%%: EV of call %.2f -> %s." % (
                100 * res["required_equity"], 100 * res["equity"], res["ev_call"], res["decision"]))
    bet = artifacts.get("bet_size") if isinstance(artifacts.get("bet_size"), (int, float)) else None
    if bet is None and isinstance(pot, (int, float)) and pot > 0 and not to_call:
        bet = pot / 2.0
    if isinstance(pot, (int, float)) and bet and bet > 0 and not to_call:
        res = _call("bluff_frequency", {"bet": bet, "pot": pot, "hand_strength": win + tie / 2.0, "seed": seed}, deadline)
        if res and res.get("action"):
            facts.used.append("bluff_frequency")
            facts.lines.append("Bluff ratio %.0f%% for a bet of %g into %g; code suggests: %s (%s)." % (
                100 * res["bluff_ratio"], bet, pot, res["action"], res["why"]))


# ------------------------------------------------------------------ search on a verified simulator (layer 3, M6)

SEARCH_S = 6.0


def _search(observation, legal, artifacts, rules, deadline, facts):
    """artifacts["simulator"]["verified"] -> alpha-beta (small) or MCTS until `deadline` (its own, longer budget)."""
    spec = artifacts.get("simulator")
    if not (isinstance(spec, dict) and spec.get("verified") and spec.get("path")):
        return
    from solvers import simsearch
    seat = artifacts.get("seat")
    r = simsearch.search_move(spec, observation, legal, seat, deadline)
    if not r or not r.get("move"):
        return
    facts.used.append("sim_search")
    if r["tool"] == "mcts":
        facts.lines.append("Search recommends %s (share %.2f; %s)." % (r["move"], r["share"], r["why"]))
    else:
        facts.lines.append("Search recommends %s (%s)." % (r["move"], r["why"]))
    if r.get("proven") and legal and r["move"] in legal:
        _set_certain(facts, r["move"], r["why"], "sim_search")


_DETECTORS = (_board, _guessing, _deduce, _dice, _matrix, _nim, _classic, _opponent, _chance)


def precompute(observation, legal_actions, artifacts, rules, deadline, search_deadline=None):
    """Run the cheap detectors. Never raises; returns Facts."""
    t0 = time.monotonic()
    facts = Facts()
    try:
        obs = observation if isinstance(observation, str) else ""
        rl = rules if isinstance(rules, str) else ""
        art = artifacts if isinstance(artifacts, dict) else {}
        legal = [a for a in legal_actions if isinstance(a, str)] if isinstance(legal_actions, list) else None
        end = t0 + TOTAL_MS / 1000.0
        if isinstance(deadline, (int, float)):
            end = min(end, deadline)
        obs, rl = obs[:MAX_TEXT], rl[:MAX_TEXT * 2]
        for det in _DETECTORS:
            if time.monotonic() >= end:
                break
            try:
                det(obs, legal, art, rl, end, facts)
            except Exception as exc:  # noqa: BLE001
                _log("%s failed: %s: %s" % (det.__name__, type(exc).__name__, exc))
        if (facts.certain is None and isinstance(search_deadline, (int, float))
                and search_deadline - time.monotonic() > 0.2):
            try:
                _search(obs, legal, art, rl, search_deadline, facts)
            except Exception as exc:  # noqa: BLE001
                _log("_search failed: %s: %s" % (type(exc).__name__, exc))
        facts.used = list(dict.fromkeys(facts.used))
    except Exception as exc:  # noqa: BLE001
        _log("precompute failed: %s: %s" % (type(exc).__name__, exc))
    facts.ms = int((time.monotonic() - t0) * 1000)
    return facts
