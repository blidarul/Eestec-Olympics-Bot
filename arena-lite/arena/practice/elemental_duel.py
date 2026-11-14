"""Elemental Duel: simultaneous elemental magic duel between two wizards."""
from __future__ import annotations

import copy
import random
import re
from typing import Any

from ..core import Game

SPELLS: dict[str, dict[str, Any]] = {
    "MEDITATE": {"cost": 0, "damage": 0, "block": 0, "restore": 20, "desc": "Costs 0 mana. Restores 20 mana."},
    "FIREBALL": {"cost": 15, "damage": 25, "block": 0, "restore": 0, "desc": "Costs 15 mana. Deals 25 damage (blocked by ICE_BARRIER)."},
    "ICE_BARRIER": {"cost": 10, "damage": 0, "block": 30, "restore": 0, "desc": "Costs 10 mana. Blocks up to 30 incoming damage."},
    "LIGHTNING": {"cost": 20, "damage": 35, "block": 0, "restore": 0, "desc": "Costs 20 mana. Deals 35 damage (blocked by ICE_BARRIER or GROUND_SPIKE)."},
    "GROUND_SPIKE": {"cost": 10, "damage": 15, "block": 20, "restore": 0, "desc": "Costs 10 mana. Deals 15 damage and grounds LIGHTNING (blocks 20 lightning damage)."},
    "SIPHON": {"cost": 5, "damage": 5, "block": 0, "restore": 10, "desc": "Costs 5 mana. Deals 5 damage and drains 10 mana from the opponent."},
}


class ElementalDuel(Game):
    id = "elemental_duel"
    name = "Elemental Duel"
    category = "duel"
    blurb = "Simultaneous wizard duel: balance mana, counter spells, and outwit your rival."
    howto = "Each round choose CAST <spell>. Spells cost mana and deal damage, shield, or restore mana. First to reduce opponent to 0 HP or most HP after all rounds wins."
    duplicate_safe = True

    @classmethod
    def variants(cls) -> list[dict]:
        return [
            {"label": "Standard Arcana (100 HP, 5 rounds)", "hp": 100, "mana": 30, "income": 10, "max_mana": 60, "rounds": 5},
            {"label": "High Mana Clash (150 HP, 6 rounds)", "hp": 150, "mana": 50, "income": 15, "max_mana": 80, "rounds": 6},
            {"label": "Sudden Death (60 HP, 3 rounds)", "hp": 60, "mana": 25, "income": 10, "max_mana": 50, "rounds": 3},
        ]

    def __init__(self, variant: dict, seed: int):
        super().__init__(variant, seed)
        self.label = str(self.variant.get("label", "Standard"))
        self.max_hp = int(self.variant.get("hp", 100))
        self.init_mana = int(self.variant.get("mana", 30))
        self.income = int(self.variant.get("income", 10))
        self.max_mana = int(self.variant.get("max_mana", 60))
        self.rounds = int(self.variant.get("rounds", 5))

        self.hp = [self.max_hp, self.max_hp]
        self.mana = [self.init_mana, self.init_mana]
        self.round_no = 1
        self.history: list[dict] = []
        self.over = False
        self.winner: int | None = None
        self.end_reason = ""

    def rules(self) -> str:
        spell_lines = "\n".join(f"- {name} (Cost: {info['cost']} mana): {info['desc']}" for name, info in SPELLS.items())
        return f"""ELEMENTAL DUEL - {self.label}. 2 players, simultaneous moves, {self.rounds} rounds.

GOAL
Defeat your rival wizard by reducing their HP to 0, or by having more HP remaining after {self.rounds} rounds.

RULES
Each wizard begins with {self.max_hp} HP and {self.init_mana} Mana.
At the end of each round, both surviving wizards regenerate +{self.income} Mana (up to a maximum of {self.max_mana}).
Every round, both players simultaneously select one spell to cast from the spellbook.
You can ONLY cast a spell if your current Mana is greater than or equal to its cost.
If incoming damage is shielded by ICE_BARRIER or GROUND_SPIKE, shield absorbs damage up to its block value.

SPELLBOOK
{spell_lines}

ACTION FORMAT
Cast a spell by typing: CAST <spell_name>
Where <spell_name> is one of: MEDITATE, FIREBALL, ICE_BARRIER, LIGHTNING, GROUND_SPIKE, SIPHON.
Examples: "CAST MEDITATE". The legal-actions list is null."""

    def to_move(self) -> list[int]:
        if self.over:
            return []
        return [0, 1]

    def legal_actions(self, seat: int) -> list[str] | None:
        if self.over:
            return []
        # Fallback has no legal list: the harness must follow action format from prep
        return None

    def normalize(self, seat: int, action: str) -> str | None:
        if self.over:
            return None
        clean = self.clean(action).upper()
        # Accept "CAST SPELL" or "SPELL"
        m = re.match(r"^(?:CAST\s+)?([A-Z_]+)$", clean)
        if not m:
            return None
        spell = m.group(1)
        if spell not in SPELLS:
            return None
        cost = SPELLS[spell]["cost"]
        if self.mana[seat] < cost:
            # Illegal move: insufficient mana
            return None
        return f"CAST {spell}"

    def apply(self, actions: dict[int, str]) -> None:
        if self.over:
            return
        a0 = self.normalize(0, actions.get(0, ""))
        a1 = self.normalize(1, actions.get(1, ""))
        if a0 is None:
            raise ValueError(f"illegal action {actions.get(0)!r} for seat 0")
        if a1 is None:
            raise ValueError(f"illegal action {actions.get(1)!r} for seat 1")

        s0 = a0.split()[-1]
        s1 = a1.split()[-1]

        info0 = SPELLS[s0]
        info1 = SPELLS[s1]

        # Deduct mana
        self.mana[0] -= info0["cost"]
        self.mana[1] -= info1["cost"]

        # Restore mana from spells
        self.mana[0] = min(self.max_mana, self.mana[0] + info0["restore"])
        self.mana[1] = min(self.max_mana, self.mana[1] + info1["restore"])

        # Siphon interaction: drains opponent mana
        if s0 == "SIPHON":
            drained = min(self.mana[1], 10)
            self.mana[1] -= drained
            self.mana[0] = min(self.max_mana, self.mana[0] + drained)
        if s1 == "SIPHON":
            drained = min(self.mana[0], 10)
            self.mana[0] -= drained
            self.mana[1] = min(self.max_mana, self.mana[1] + drained)

        # Calculate damage dealt by 0 to 1
        raw_dmg0 = info0["damage"]
        block1 = 0
        if s1 == "ICE_BARRIER":
            block1 = 30
        elif s1 == "GROUND_SPIKE" and s0 == "LIGHTNING":
            block1 = 20
        eff_dmg0 = max(0, raw_dmg0 - block1)

        # Calculate damage dealt by 1 to 0
        raw_dmg1 = info1["damage"]
        block0 = 0
        if s0 == "ICE_BARRIER":
            block0 = 30
        elif s0 == "GROUND_SPIKE" and s1 == "LIGHTNING":
            block0 = 20
        eff_dmg1 = max(0, raw_dmg1 - block0)

        # Apply damage
        self.hp[1] = max(0, self.hp[1] - eff_dmg0)
        self.hp[0] = max(0, self.hp[0] - eff_dmg1)

        # End of round mana regen for survivors
        self.mana[0] = min(self.max_mana, self.mana[0] + self.income)
        self.mana[1] = min(self.max_mana, self.mana[1] + self.income)

        # Record history
        round_record = {
            "round": self.round_no,
            "spells": [s0, s1],
            "dmg": [eff_dmg0, eff_dmg1],
            "hp": list(self.hp),
            "mana": list(self.mana),
        }
        self.history.append(round_record)

        # Check termination
        if self.hp[0] <= 0 or self.hp[1] <= 0:
            self.over = True
            if self.hp[0] > self.hp[1]:
                self.winner = 0
                self.end_reason = "seat 0 eliminated seat 1"
            elif self.hp[1] > self.hp[0]:
                self.winner = 1
                self.end_reason = "seat 1 eliminated seat 0"
            else:
                self.winner = None
                self.end_reason = "both wizards fell simultaneously: draw"
        elif self.round_no >= self.rounds:
            self.over = True
            if self.hp[0] > self.hp[1]:
                self.winner = 0
                self.end_reason = f"seat 0 won by HP ({self.hp[0]} vs {self.hp[1]})"
            elif self.hp[1] > self.hp[0]:
                self.winner = 1
                self.end_reason = f"seat 1 won by HP ({self.hp[1]} vs {self.hp[0]})"
            else:
                self.winner = None
                self.end_reason = "equal HP after all rounds: draw"
        else:
            self.round_no += 1

    def is_over(self) -> bool:
        return self.over

    def result(self) -> dict:
        if not self.over:
            return {"winner": None, "scores": [0, 0], "reason": "in progress"}
        scores = [0.0, 0.0]
        if self.winner is not None:
            scores[self.winner] = 1.0
        else:
            scores = [0.5, 0.5]
        return {"winner": self.winner, "scores": scores, "reason": self.end_reason}

    def observation(self, seat: int) -> str:
        opp = 1 - seat
        my_spells = [f"CAST {s}" for s, info in SPELLS.items() if self.mana[seat] >= info["cost"]]
        lines = [
            f"ELEMENTAL DUEL - {self.label}. Round {self.round_no}/{self.rounds}. You are seat {seat}.",
            f"Your status: HP={self.hp[seat]}/{self.max_hp}, Mana={self.mana[seat]}/{self.max_mana}.",
            f"Opponent status: HP={self.hp[opp]}/{self.max_hp}, Mana={self.mana[opp]}/{self.max_mana}.",
            f"Affordable spells: {', '.join(my_spells)}.",
        ]
        if self.history:
            lines.append("Previous rounds history:")
            for h in self.history:
                r = h["round"]
                my_s = h["spells"][seat]
                opp_s = h["spells"][opp]
                dealt = h["dmg"][seat]
                taken = h["dmg"][opp]
                lines.append(f"Round {r}: you CAST {my_s} (dealt {dealt}) | opponent CAST {opp_s} (dealt {taken})")
        lines.append(f'It is your turn: cast one affordable spell (e.g. "CAST {my_spells[0].split()[-1]}").')
        return "\n".join(lines)

    def random_action(self, seat: int, rng: random.Random) -> str:
        affordable = [s for s, info in SPELLS.items() if self.mana[seat] >= info["cost"]]
        chosen = rng.choice(affordable) if affordable else "MEDITATE"
        return f"CAST {chosen}"

    def frame(self) -> dict:
        return copy.deepcopy({
            "label": self.label,
            "round": self.round_no,
            "rounds": self.rounds,
            "hp": list(self.hp),
            "mana": list(self.mana),
            "history": list(self.history),
            "over": self.over,
            "winner": self.winner,
            "reason": self.end_reason,
        })
