"""Battleship: naval hidden-information duel with hits, misses and sunk fleet tracking."""
from __future__ import annotations

import re

from ..core import Game

_FIRE_RE = re.compile(r"^(?:fire\s+)?([a-z])(\d+)$", re.IGNORECASE)

FLEETS = {
    "small": [
        {"name": "Cruiser", "letter": "C", "size": 3},
        {"name": "Destroyer", "letter": "D", "size": 2},
        {"name": "Patrol boat", "letter": "P", "size": 2},
    ],
    "standard": [
        {"name": "Battleship", "letter": "B", "size": 4},
        {"name": "Cruiser", "letter": "C", "size": 3},
        {"name": "Destroyer", "letter": "D", "size": 2},
        {"name": "Patrol boat", "letter": "P", "size": 2},
    ],
}


class Battleship(Game):
    id = "battleship"
    name = "Battleship"
    category = "guess"
    blurb = "Classic naval warfare: hide your fleet, probe enemy waters, track hits and hunt down surviving ships."
    howto = "Each player places a hidden fleet on their grid. Players take turns firing shots into enemy waters. First to sink all enemy ships wins."
    duplicate_safe = False

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "6x6, 3 ships", "size": 6, "fleet": "small", "salvo": False, "max_rounds": 30},
            {"label": "8x8, 4 ships", "size": 8, "fleet": "standard", "salvo": False, "max_rounds": 40},
            {"label": "8x8 salvo", "size": 8, "fleet": "standard", "salvo": True, "max_rounds": 40},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "6x6, 3 ships"))
        self.size = max(5, min(10, int(self.variant.get("size", 6))))
        self.fleet_type = str(self.variant.get("fleet", "small"))
        self.salvo = bool(self.variant.get("salvo", False))
        self.max_rounds = int(self.variant.get("max_rounds", 30))

        fleet_defs = FLEETS.get(self.fleet_type, FLEETS["small"])
        # Place ships randomly for each player
        self.boards = [
            {"ships": self._place_fleet(fleet_defs), "shots": []},
            {"ships": self._place_fleet(fleet_defs), "shots": []},
        ]
        self.hits = [0, 0]  # hits achieved BY seat against opponent
        self.afloat = [len(fleet_defs), len(fleet_defs)]
        self.round = 1
        self.current = 0
        self.last: dict | None = None
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def _place_fleet(self, fleet_defs: list[dict]) -> list[dict]:
        placed_ships: list[dict] = []
        occupied: set[tuple[int, int]] = set()

        for s_def in fleet_defs:
            size = s_def["size"]
            placed = False
            for _ in range(500):
                horiz = self.rng.choice([True, False])
                if horiz:
                    r = self.rng.randint(0, self.size - 1)
                    c = self.rng.randint(0, self.size - size)
                    cells = [[r, c + i] for i in range(size)]
                else:
                    r = self.rng.randint(0, self.size - size)
                    c = self.rng.randint(0, self.size - 1)
                    cells = [[r + i, c] for i in range(size)]

                if not any(tuple(cell) in occupied for cell in cells):
                    for cell in cells:
                        occupied.add(tuple(cell))
                    placed_ships.append({
                        "name": s_def["name"],
                        "letter": s_def["letter"],
                        "size": size,
                        "cells": cells,
                        "sunk": False,
                    })
                    placed = True
                    break
            if not placed:
                # Fallback: simple line placement if rng was unlucky
                r = len(placed_ships)
                cells = [[r, i] for i in range(size)]
                placed_ships.append({
                    "name": s_def["name"],
                    "letter": s_def["letter"],
                    "size": size,
                    "cells": cells,
                    "sunk": False,
                })
        return placed_ships

    def rules(self) -> str:
        last_col = chr(ord("a") + self.size - 1)
        fleet_names = ", ".join(f"{s['name']} ({s['size']} cells, letter {s['letter']})" for s in FLEETS.get(self.fleet_type, FLEETS["small"]))
        return f"""BATTLESHIP - {self.label}.

GOAL
Each player has a hidden fleet on their own {self.size}x{self.size} grid. Sink all of your opponent's ships before
they sink yours.

SETUP (done by the arena, randomly)
Fleet of each player: {fleet_names}.
Ships are straight lines (horizontal or vertical), never overlap, may touch each other, and stay
inside the grid. You see your own ships; you never see the opponent's ships.

COORDINATES
Columns are letters a..{last_col} from left to right, rows are numbers 1..{self.size} from top to bottom.
A cell is column letter + row number: "a1" is the top-left corner, "{last_col}{self.size}" the bottom-right.

TURN ORDER
Player 0 shoots first, then Player 1, alternating. One "round" = Player 0's turn + Player 1's turn.
Each turn you fire exactly ONE shot.

ACTION FORMAT
    fire <cell>
where <cell> is a cell you have never fired at before.
Examples:  "fire c4"   "fire a1"   "fire {last_col}{self.size}"
Firing at a cell you already fired at, a cell outside the grid, or any other text is illegal
(first time: a warning and the same turn again; second time: you lose the game). Case and extra
spaces do not matter.

FEEDBACK
After each shot you learn: "miss" (water), "hit" (a ship was hit; the ship is not named), or
"hit, sunk <Ship name> (<size>)" when that shot hit the last remaining cell of a ship.
You also see where the opponent's shots landed on your own grid.

WHAT YOU OBSERVE
- Status of both fleets (which ships are sunk), round number, how many shots you must fire.
- YOUR SHOTS grid (the opponent's waters):  . = not fired yet, o = miss, X = hit, # = hit on a ship
  that is already sunk.
- YOUR WATERS grid (your fleet): a ship letter = intact part of your ship, * = part of your ship
  that was hit, o = opponent's miss, . = untouched water.
- The recent shot history of both players.

HOW THE GAME ENDS AND IS SCORED
The game is checked at the END of every round, so both players always get the same number of turns:
- if only one player has sunk the whole enemy fleet, that player wins;
- if both did it in the same round (Player 1 equalised on the last turn), it is a draw.
Shot cap: after round {self.max_rounds} the game ends; the player who hit more enemy ship cells wins,
equal = draw. Score = number of enemy ship cells you hit.
"""

    def to_move(self) -> list[int]:
        return [] if self.over else [self.current]

    def legal_actions(self, seat: int) -> list[str] | None:
        return None  # large action space

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over or seat != self.current:
            return None
        m = _FIRE_RE.match(self.clean(action))
        if not m:
            return None
        c = ord(m.group(1).lower()) - ord("a")
        r = int(m.group(2)) - 1
        if not (0 <= r < self.size and 0 <= c < self.size):
            return None
        # Check if already fired at
        fired_cells = [s["cell"] for s in self.boards[seat]["shots"]]
        if [r, c] in fired_cells:
            return None
        return f"fire {chr(ord('a') + c)}{r + 1}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        act = actions.get(self.current)
        if not act:
            return
        norm = self.normalize(self.current, act)
        if not norm:
            return

        m = _FIRE_RE.match(norm)
        c = ord(m.group(1).lower()) - ord("a")
        r = int(m.group(2)) - 1
        opp = 1 - self.current

        # Check hit on opp's fleet
        hit_ship = None
        for ship in self.boards[opp]["ships"]:
            if [r, c] in ship["cells"]:
                hit_ship = ship
                break

        res = "miss"
        sunk_ship_name = None
        if hit_ship:
            self.hits[self.current] += 1
            # Check if all cells of hit_ship have been shot
            prior_shots = [s["cell"] for s in self.boards[self.current]["shots"]] + [[r, c]]
            if all(cell in prior_shots for cell in hit_ship["cells"]):
                hit_ship["sunk"] = True
                self.afloat[opp] -= 1
                res = "sunk"
                sunk_ship_name = hit_ship["name"]
            else:
                res = "hit"

        shot_record = {
            "cell": [r, c],
            "result": res,
            "ship": sunk_ship_name,
        }
        self.boards[self.current]["shots"].append(shot_record)
        self.last = {
            "seat": self.current,
            "action": norm,
            "cell": [r, c],
            "result": res,
            "sunk": sunk_ship_name,
        }

        # Check turn order / round completion
        if self.current == 1:
            # Round finished: check end conditions
            sunk0 = (self.afloat[0] == 0)
            sunk1 = (self.afloat[1] == 0)
            if sunk0 and sunk1:
                self.over = True
                self.winner = None
                self.end_reason = f"both fleets sunk in round {self.round} (draw)"
            elif sunk1:
                # Opponent 1's fleet is completely sunk by Seat 0
                self.over = True
                self.winner = 0
                self.end_reason = f"seat 0 sunk the whole enemy fleet in round {self.round}"
            elif sunk0:
                # Opponent 0's fleet is completely sunk by Seat 1
                self.over = True
                self.winner = 1
                self.end_reason = f"seat 1 sunk the whole enemy fleet in round {self.round}"
            elif self.round >= self.max_rounds:
                self.over = True
                if self.hits[0] > self.hits[1]:
                    self.winner = 0
                    self.end_reason = f"shot cap reached ({self.max_rounds} rounds); seat 0 hit more cells ({self.hits[0]} vs {self.hits[1]})"
                elif self.hits[1] > self.hits[0]:
                    self.winner = 1
                    self.end_reason = f"shot cap reached ({self.max_rounds} rounds); seat 1 hit more cells ({self.hits[1]} vs {self.hits[0]})"
                else:
                    self.winner = None
                    self.end_reason = f"shot cap reached ({self.max_rounds} rounds); equal hits {self.hits[0]}-{self.hits[1]} (draw)"
            else:
                self.round += 1
                self.current = 0
        else:
            self.current = 1

    def is_over(self) -> bool:
        return self.over

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        turn_owner = "your" if self.current == seat else "opponent's"
        lines = [
            f"BATTLESHIP ({self.label}). You are Player {seat}.",
            f"Round {self.round} of {self.max_rounds}. It is {turn_owner} turn.",
            f"Fleet status: you have {self.afloat[seat]} ships afloat; opponent has {self.afloat[opp]} ships afloat.",
            "",
            "YOUR SHOTS (targeting opponent's fleet):",
        ]
        # Build shots grid (. unhit, o miss, X hit, # hit on sunk ship)
        my_shots = self.boards[seat]["shots"]
        shot_map = {tuple(s["cell"]): s for s in my_shots}
        # Sunk ships on opponent side
        sunk_cells = set()
        for ship in self.boards[opp]["ships"]:
            if ship["sunk"]:
                for cell in ship["cells"]:
                    sunk_cells.add(tuple(cell))

        col_header = "   " + " ".join(chr(ord("a") + c) for c in range(self.size))
        lines.append(col_header)
        for r in range(self.size):
            row_chars = []
            for c in range(self.size):
                if (r, c) not in shot_map:
                    row_chars.append(".")
                elif (r, c) in sunk_cells:
                    row_chars.append("#")
                elif shot_map[(r, c)]["result"] in ("hit", "sunk"):
                    row_chars.append("X")
                else:
                    row_chars.append("o")
            lines.append(f"{r + 1:>2} " + " ".join(row_chars))

        lines.append("")
        lines.append("YOUR WATERS (your fleet and opponent's shots):")
        opp_shots = {tuple(s["cell"]): s for s in self.boards[opp]["shots"]}
        ship_cell_map = {}
        for ship in self.boards[seat]["ships"]:
            for cell in ship["cells"]:
                ship_cell_map[tuple(cell)] = ship["letter"]

        lines.append(col_header)
        for r in range(self.size):
            row_chars = []
            for c in range(self.size):
                if (r, c) in opp_shots:
                    if (r, c) in ship_cell_map:
                        row_chars.append("*")
                    else:
                        row_chars.append("o")
                elif (r, c) in ship_cell_map:
                    row_chars.append(ship_cell_map[(r, c)])
                else:
                    row_chars.append(".")
            lines.append(f"{r + 1:>2} " + " ".join(row_chars))

        if self.last:
            lines.append("")
            lines.append(f"Last shot: Player {self.last['seat']} fired {self.last['action']} -> {self.last['result']}" + (f" ({self.last['sunk']})!" if self.last["sunk"] else "."))
        return "\n".join(lines)

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "scores": list(self.hits),
            "reason": self.end_reason or ("in progress" if not self.over else "draw"),
        }

    def frame(self) -> dict:
        return {
            "size": self.size,
            "salvo": self.salvo,
            "round": self.round,
            "max_rounds": self.max_rounds,
            "boards": self.boards,
            "hits": list(self.hits),
            "afloat": list(self.afloat),
            "last": self.last,
            "to_move": self.to_move(),
            "over": self.over,
            "result": self.result() if self.over else None,
        }
