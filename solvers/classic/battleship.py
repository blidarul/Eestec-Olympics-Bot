"""battleship_target: probability-density shooting for hidden-ship grids (hunt, then target).

Counts every placement of every remaining ship that fits the known misses/sunk cells; hits not yet sunk force
placements through them (target mode). Cells come from the legal actions (letter+number or 'r,c'); letter vs number
as row is irrelevant because ships may lie both ways. Parameters, not game names. Never proven (hidden information).
"""
import re

from solvers.classic import ClassicSolver, register

_STD = (5, 4, 3, 3, 2)
_NAMES = {"carrier": 5, "battleship": 4, "cruiser": 3, "submarine": 3, "destroyer": 2}
_CELL = re.compile(r"^\s*\(?\s*([A-Za-z])\s*[-:]?\s*(\d{1,2})\s*\)?\s*$")
_PAIR = re.compile(r"^\s*\(?\s*(\d{1,2})\s*[, ]\s*(\d{1,2})\s*\)?\s*$")
_REC1 = re.compile(r"\b([A-Za-z]\d{1,2})\b[^A-Za-z0-9\n]{0,6}\b(hit|miss|sunk)\b", re.I)
_REC2 = re.compile(r"\b(hit|miss|sunk)\b[^A-Za-z0-9\n]{0,12}(?:at\s+|on\s+)?\(?([A-Za-z]\d{1,2})\b", re.I)
_REC3 = re.compile(r"\(?\b(\d{1,2})\s*,\s*(\d{1,2})\)?[^A-Za-z0-9\n]{0,6}\b(hit|miss|sunk)\b", re.I)
_REC4 = re.compile(r"\b(hit|miss|sunk)\b[^A-Za-z0-9\n]{0,12}(?:at\s+|on\s+)?\(?(\d{1,2})\s*,\s*(\d{1,2})\)?", re.I)


def detect(rules, variant):
    low = (rules or "").lower()
    if "ship" not in low or not re.search(r"\bhit\b", low) or not re.search(r"\bmiss", low):
        return None
    if not re.search(r"grid|board|coordinate|cell|square", low):
        return None
    lens = []
    for m in re.finditer(r"\b(carrier|battleship|cruiser|submarine|destroyer)\b[^0-9\n]{0,12}\(?(\d)\b", low):
        lens.append(int(m.group(2)))
    if not lens:
        m = re.search(r"(?:ships?|lengths?)[^.\n]{0,40}?((?:\b[2-6]\b[\s,and&x×]*){2,8})", low)
        if m:
            lens = [int(x) for x in re.findall(r"\b([2-6])\b", m.group(1))]
    if not lens:
        found = [v for k, v in _NAMES.items() if k in low]
        if len(found) >= 3:
            lens = list(_STD)
    if not lens:
        return None
    size = 10
    m = re.search(r"\b(\d{1,2})\s*[x×*]\s*(\d{1,2})\b", low)
    if m and 3 <= int(m.group(1)) <= 26 and 3 <= int(m.group(2)) <= 26:
        return {"ships": lens[:8], "rows": int(m.group(1)), "cols": int(m.group(2))}
    return {"ships": lens[:8], "rows": size, "cols": size}


def _cell(a):
    s = str(a)
    m = _CELL.match(s)
    if m:
        return ("A", ord(m.group(1).upper()) - 65, int(m.group(2)) - 1)
    m = _PAIR.match(s)
    if m:
        return ("N", int(m.group(1)), int(m.group(2)))
    return None


def verify(params, sample):
    legal = sample.get("legal_actions")
    if not legal:
        return False
    cells = [_cell(a) for a in legal]
    return all(c is not None for c in cells) and len({c[0] for c in cells}) == 1 and len(set(legal)) == len(legal)


def _records(observation, style):
    out = {}                                   # (r, c) -> "hit" | "miss" | "sunk"

    def put(r, c, kind):
        out[(r, c)] = kind.lower()
    text = observation or ""
    if style == "A":
        for m in _REC1.finditer(text):
            c = _cell(m.group(1))
            if c:
                put(c[1], c[2], m.group(2))
        for m in _REC2.finditer(text):
            c = _cell(m.group(2))
            if c:
                put(c[1], c[2], m.group(1))
    else:
        for m in _REC3.finditer(text):
            put(int(m.group(1)), int(m.group(2)), m.group(3))
        for m in _REC4.finditer(text):
            put(int(m.group(2)), int(m.group(3)), m.group(1))
    return out


def solve(observation, legal, params, deadline):
    cells = {a: _cell(a) for a in legal or []}
    if not cells:
        return {"move": None, "value": None, "why": "no legal cells", "proven": False}
    style = next(iter(cells.values()))[0]
    rec = _records(observation, style)
    rows = max([params["rows"]] + [c[1] + 1 for c in cells.values()])
    cols = max([params["cols"]] + [c[2] + 1 for c in cells.values()])
    if style == "N":
        lo = min(min(c[1], c[2]) for c in cells.values())
        if lo >= 1:                              # 1-based numbering: shift to 0-based internally
            cells = {a: ("N", c[1] - 1, c[2] - 1) for a, c in cells.items()}
            rec = {(r - 1, c - 1): k for (r, c), k in rec.items()}
            rows, cols = max(rows - 1, max(c[1] for c in cells.values()) + 1), max(cols - 1, max(c[2] for c in cells.values()) + 1)
            rows, cols = max(rows, params["rows"]), max(cols, params["cols"])
    shootable = {(c[1], c[2]): a for a, c in cells.items()}
    blocked = {p for p, k in rec.items() if k in ("miss", "sunk")}
    hits = {p for p, k in rec.items() if k == "hit"}
    sunk_n = sum(1 for k in rec.values() if k == "sunk")
    ships = sorted(params["ships"], reverse=True)
    # a 'sunk' record removes the longest ship that could still fit its run (best effort)
    for _ in range(min(sunk_n, len(ships) - 1)):
        ships.pop(0) if not hits else ships.pop()
    dens = {}
    for L in ships:
        for r in range(rows):
            for c in range(cols):
                for dr, dc in ((0, 1), (1, 0)):
                    cs = [(r + dr * i, c + dc * i) for i in range(L)]
                    if cs[-1][0] >= rows or cs[-1][1] >= cols or any(p in blocked for p in cs):
                        continue
                    touched = sum(1 for p in cs if p in hits)
                    if hits and touched == 0:
                        continue
                    w = 1 + 50 * touched * touched
                    for p in cs:
                        if p in shootable and p not in hits:
                            dens[p] = dens.get(p, 0) + w
    if not dens:
        p = sorted(shootable)[len(shootable) // 2]
        return {"move": shootable[p], "value": None, "why": "no ship placement fits: shooting a middle cell", "proven": False}
    best = max(dens, key=lambda p: (dens[p], (p[0] + p[1]) % 2 == 0, -p[0], -p[1]))
    mode = "target (unsunk hits: %d)" % len(hits) if hits else "hunt"
    return {"move": shootable[best], "value": None,
            "why": "density %s: %s has the most ship placements (%d)" % (mode, shootable[best], dens[best]), "proven": False}


register(ClassicSolver("battleship", detect, verify, solve))
