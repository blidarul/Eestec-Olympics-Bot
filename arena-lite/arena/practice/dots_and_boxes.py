"""Dots and Boxes: line-drawing territory duel with chained bonus turns."""
from __future__ import annotations

import re

from ..core import Game

_LINE_RE = re.compile(r"^(?:line\s+)?([a-z])(\d+)[-\s]+([a-z])(\d+)$", re.IGNORECASE)


class DotsAndBoxes(Game):
    id = "dots_and_boxes"
    name = "Dots and Boxes"
    category = "think"
    blurb = "Classic pen-and-paper territory control: draw edges, box in squares, and chain chain-reactions to sweep the board."
    howto = "Players take turns drawing horizontal or vertical lines between dots. Completing the fourth side of a box claims it and gives you another turn. Most boxes wins."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "4x4 boxes", "rows": 4, "cols": 4},
            {"label": "3x3 boxes", "rows": 3, "cols": 3},
            {"label": "3x5 boxes", "rows": 3, "cols": 5},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "4x4 boxes"))
        self.rows = max(2, min(8, int(self.variant.get("rows", 4))))
        self.cols = max(2, min(8, int(self.variant.get("cols", 4))))

        # Horizontal edges: (rows + 1) rows of cols edges
        self.h: list[list[int | None]] = [[None] * self.cols for _ in range(self.rows + 1)]
        # Vertical edges: rows rows of (cols + 1) edges
        self.v: list[list[int | None]] = [[None] * (self.cols + 1) for _ in range(self.rows)]
        # Boxes: rows x cols
        self.boxes: list[list[int | None]] = [[None] * self.cols for _ in range(self.rows)]

        self.scores = [0, 0]
        self.current = 0
        self.moves = 0
        self.total_edges = (self.rows + 1) * self.cols + self.rows * (self.cols + 1)
        self.drawn_edges = 0
        self.last: dict | None = None
        self.history: list[dict] = []
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _canonical_edge(self, c1: int, r1: int, c2: int, r2: int) -> tuple[str, int, int] | None:
        """Returns ('h', r, c) or ('v', r, c) in 0-indexed bounds, or None."""
        if r1 == r2 and abs(c1 - c2) == 1:
            r = r1
            c = min(c1, c2)
            if 0 <= r <= self.rows and 0 <= c < self.cols:
                return ("h", r, c)
        elif c1 == c2 and abs(r1 - r2) == 1:
            c = c1
            r = min(r1, r2)
            if 0 <= r < self.rows and 0 <= c <= self.cols:
                return ("v", r, c)
        return None

    def _edge_name(self, kind: str, r: int, c: int) -> str:
        if kind == "h":
            d1 = f"{chr(ord('a') + c)}{r + 1}"
            d2 = f"{chr(ord('a') + c + 1)}{r + 1}"
            return f"line {d1}-{d2}"
        else:
            d1 = f"{chr(ord('a') + c)}{r + 1}"
            d2 = f"{chr(ord('a') + c)}{r + 2}"
            return f"line {d1}-{d2}"

    def rules(self) -> str:
        dot_r = self.rows + 1
        last_col = chr(ord("a") + self.cols)
        num_boxes = self.rows * self.cols
        return f"""DOTS AND BOXES - {self.label} ({dot_r}x{self.cols + 1} dots).

GOAL
Own more boxes than your opponent when every line has been drawn.

BOARD AND COORDINATES
The board is a grid of dots: {dot_r} rows numbered 1..{dot_r} from TOP to BOTTOM and {self.cols + 1} columns
lettered a..{last_col} from LEFT to RIGHT. A dot is named column letter + row number: "a1" is the top-left
dot, "{last_col}{dot_r}" the bottom-right dot. A line joins two neighbouring dots, either horizontally
(same row, neighbouring letters, e.g. a1-b1) or vertically (same letter, neighbouring rows, e.g.
a1-a2). Diagonal or longer lines do not exist. There are {self.total_edges} possible lines and
{num_boxes} boxes.

TURN ORDER
Player 0 moves first. On your turn you draw ONE line that has not been drawn yet.
- If your line completes the 4th side of one box (or of two boxes at once), you claim those boxes
  AND you must move again immediately (another line). This can repeat many times in a row.
- If your line completes no box, the turn passes to the opponent.
Passing is not allowed. Lines belong to nobody; only boxes are owned.

ACTION FORMAT
    line <dot>-<dot>
Examples:  "line a1-b1"   "line c2-c3"   "line b{self.rows + 1}-c{self.rows + 1}"
The two dots may be given in any order and separated by "-" or a space ("line b1 a1" works too).
A line that is already drawn, dots that are not neighbours, or any other text is illegal (first
time: a warning and the same turn again; second time: you lose the game). The arena sends the
complete list of legal moves every turn.

WHAT YOU OBSERVE
The board in text: "+" = dot, "---" = horizontal line, "|" = vertical line, and a claimed box shows
the number of its owner (0 or 1). You also see the score, the move history and whether you are moving again.

HOW THE GAME ENDS AND IS SCORED
The game ends when all {self.total_edges} lines are drawn (that is also the move cap). The player who
owns more boxes wins (score = boxes owned). There can be a tie when the boxes are split evenly (draw, 0.5 each).
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def _all_legal(self) -> list[str]:
        moves = []
        for r in range(self.rows + 1):
            for c in range(self.cols):
                if self.h[r][c] is None:
                    moves.append(self._edge_name("h", r, c))
        for r in range(self.rows):
            for c in range(self.cols + 1):
                if self.v[r][c] is None:
                    moves.append(self._edge_name("v", r, c))
        return moves

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over or seat != self.current:
            return []
        return self.cap_list(self._all_legal())

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        m = _LINE_RE.match(self.clean(action))
        if not m:
            return None
        c1 = ord(m.group(1).lower()) - ord("a")
        r1 = int(m.group(2)) - 1
        c2 = ord(m.group(3).lower()) - ord("a")
        r2 = int(m.group(4)) - 1
        parsed = self._canonical_edge(c1, r1, c2, r2)
        if not parsed:
            return None
        kind, r, c = parsed
        if kind == "h" and self.h[r][c] is not None:
            return None
        if kind == "v" and self.v[r][c] is not None:
            return None
        return self._edge_name(kind, r, c)

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        m = _LINE_RE.match(norm)
        c1 = ord(m.group(1).lower()) - ord("a")
        r1 = int(m.group(2)) - 1
        c2 = ord(m.group(3).lower()) - ord("a")
        r2 = int(m.group(4)) - 1
        kind, r, c = self._canonical_edge(c1, r1, c2, r2)

        if kind == "h":
            self.h[r][c] = self.current
        else:
            self.v[r][c] = self.current

        self.drawn_edges += 1
        self.moves += 1

        # Check completed boxes
        completed = []
        adjacent_boxes = []
        if kind == "h":
            if r > 0:
                adjacent_boxes.append((r - 1, c))
            if r < self.rows:
                adjacent_boxes.append((r, c))
        else:
            if c > 0:
                adjacent_boxes.append((r, c - 1))
            if c < self.cols:
                adjacent_boxes.append((r, c))

        for br, bc in adjacent_boxes:
            if self.boxes[br][bc] is None:
                # Check 4 edges
                if (
                    self.h[br][bc] is not None
                    and self.h[br + 1][bc] is not None
                    and self.v[br][bc] is not None
                    and self.v[br][bc + 1] is not None
                ):
                    self.boxes[br][bc] = self.current
                    self.scores[self.current] += 1
                    completed.append([br, bc])

        record = {
            "seat": self.current,
            "edge": norm,
            "kind": kind,
            "r": r,
            "c": c,
            "completed": completed,
        }
        self.history.append(record)
        self.last = record

        # If box completed, player moves again; otherwise turn passes
        if self.drawn_edges >= self.total_edges:
            self.over = True
            if self.scores[0] > self.scores[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won {self.scores[0]} to {self.scores[1]} boxes"
            elif self.scores[1] > self.scores[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won {self.scores[1]} to {self.scores[0]} boxes"
            else:
                self.winner = None
                self.end_reason = f"draw {self.scores[0]} to {self.scores[1]} boxes"
        else:
            if not completed:
                self.current = 1 - self.current

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        lines = [
            f"DOTS AND BOXES ({self.label}). You are Player {seat}.",
            f"Current scores: Player 0 = {self.scores[0]}, Player 1 = {self.scores[1]}.",
            f"Turn: Player {self.current} (move {self.moves + 1}). Remaining lines: {self.total_edges - self.drawn_edges}.",
            "",
        ]
        # Render board
        col_headers = "   " + "   ".join(chr(ord("a") + c) for c in range(self.cols + 1))
        lines.append(col_headers)
        for r in range(self.rows):
            # Row of dots and h-edges
            row_str = f"{r + 1:>2} +"
            for c in range(self.cols):
                edge = "---+" if self.h[r][c] is not None else "   +"
                row_str += edge
            lines.append(row_str)
            # Row of v-edges and boxes
            v_str = "   "
            for c in range(self.cols + 1):
                v_edge = "|" if self.v[r][c] is not None else " "
                box_str = ""
                if c < self.cols:
                    b_owner = self.boxes[r][c]
                    box_str = f" {b_owner} " if b_owner is not None else "   "
                v_str += v_edge + box_str
            lines.append(v_str)
        # Bottom dot row
        last_r = self.rows
        row_str = f"{last_r + 1:>2} +"
        for c in range(self.cols):
            edge = "---+" if self.h[last_r][c] is not None else "   +"
            row_str += edge
        lines.append(row_str)

        lines.append("")
        if self.last:
            lines.append(f"Last move: Player {self.last['seat']} drew {self.last['edge']}" + (f" and claimed {len(self.last['completed'])} box(es)!" if self.last["completed"] else "."))
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": list(self.scores),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "h": [list(row) for row in self.h],
            "v": [list(row) for row in self.v],
            "boxes": [list(row) for row in self.boxes],
            "scores": list(self.scores),
            "last": self.last,
            "moves": self.moves,
            "total_edges": self.total_edges,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
