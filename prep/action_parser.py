"""Rules & Action Grammar Parser.
Extracts action format, coordinates/ranges/commands, and observation layout from rules and sample turns.
Owned by agent `bld`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionGrammar:
    kind: str  # "grid" | "discrete" | "numeric_range" | "generic"
    discrete_actions: list[str] = field(default_factory=list)
    grid_cols: int = 0
    grid_rows: int = 0
    grid_col_letters: list[str] = field(default_factory=list)
    numeric_min: int | None = None
    numeric_max: int | None = None
    numeric_prefix: str = ""
    case_sensitive: bool = False
    aliases: dict[str, str] = field(default_factory=dict)

    def validate(self, action: str, legal_actions: list[str] | None = None) -> bool:
        """Validate if an action conforms to legal_actions or grammar rules."""
        if not action or not isinstance(action, str):
            return False
        clean = action.strip()
        if not clean:
            return False

        if legal_actions:
            by_lower = {a.lower().strip(): a for a in legal_actions}
            if clean.lower() in by_lower:
                return True
            # Check if canonical alias matches
            if clean.lower() in self.aliases and self.aliases[clean.lower()].lower() in by_lower:
                return True
            return False

        # No legal_actions provided (null): validate against grammar
        if self.kind == "discrete":
            candidates = {a.lower() for a in self.discrete_actions}
            return clean.lower() in candidates or clean.lower() in self.aliases

        if self.kind == "grid":
            # Matches formats like A1, B2, or "place A1", "move A1"
            m = re.match(r"^(?:place|play|move)?\s*([a-zA-Z])\s*(\d{1,2})$", clean, re.IGNORECASE)
            if not m:
                m = re.match(r"^(?:place|play|move)?\s*(\d{1,2})\s*([a-zA-Z])$", clean, re.IGNORECASE)
                if not m:
                    return False
                r_str, c_str = m.group(1), m.group(2)
            else:
                c_str, r_str = m.group(1), m.group(2)

            col_idx = ord(c_str.upper()) - ord("A")
            try:
                row_idx = int(r_str) - 1
            except ValueError:
                return False

            if 0 <= col_idx < self.grid_cols and 0 <= row_idx < self.grid_rows:
                return True
            return False

        if self.kind == "numeric_range":
            # Match optional prefix + number, e.g. "guess 42" or "42"
            digits = re.search(r"(-?\d+)", clean)
            if not digits:
                return False
            val = int(digits.group(1))
            if self.numeric_min is not None and val < self.numeric_min:
                return False
            if self.numeric_max is not None and val > self.numeric_max:
                return False
            return True

        return True

    def normalize(self, action: str, legal_actions: list[str] | None = None) -> str:
        """Normalize an action string to its canonical representation."""
        clean = action.strip()
        if legal_actions:
            by_lower = {a.lower().strip(): a for a in legal_actions}
            if clean.lower() in by_lower:
                return by_lower[clean.lower()]
            if clean.lower() in self.aliases:
                alias = self.aliases[clean.lower()]
                if alias.lower() in by_lower:
                    return by_lower[alias.lower()]
            return legal_actions[0]

        if self.kind == "discrete":
            for d in self.discrete_actions:
                if d.lower() == clean.lower():
                    return d
            if clean.lower() in self.aliases:
                return self.aliases[clean.lower()]
            return clean

        if self.kind == "grid":
            m = re.match(r"^(?:place|play|move)?\s*([a-zA-Z])\s*(\d{1,2})$", clean, re.IGNORECASE)
            if m:
                return f"{m.group(1).upper()}{m.group(2)}"
            m_rev = re.match(r"^(?:place|play|move)?\s*(\d{1,2})\s*([a-zA-Z])$", clean, re.IGNORECASE)
            if m_rev:
                return f"{m_rev.group(2).upper()}{m_rev.group(1)}"
            return clean

        if self.kind == "numeric_range":
            digits = re.search(r"(-?\d+)", clean)
            if digits:
                val = digits.group(1)
                return f"{self.numeric_prefix}{val}".strip()
            return clean

        return clean

    def fallback_action(self, legal_actions: list[str] | None = None) -> str:
        """Return a safe fallback action guaranteed to be syntactically valid."""
        if legal_actions and len(legal_actions) > 0:
            return legal_actions[0]
        if self.discrete_actions:
            return self.discrete_actions[0]
        if self.kind == "grid":
            return "A1"
        if self.kind == "numeric_range" and self.numeric_min is not None:
            mid = (self.numeric_min + (self.numeric_max or self.numeric_min)) // 2
            return f"{self.numeric_prefix}{mid}".strip()
        return "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "discrete_actions": self.discrete_actions,
            "grid_cols": self.grid_cols,
            "grid_rows": self.grid_rows,
            "grid_col_letters": self.grid_col_letters,
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "numeric_prefix": self.numeric_prefix,
            "case_sensitive": self.case_sensitive,
            "aliases": self.aliases,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionGrammar:
        return cls(
            kind=data.get("kind", "generic"),
            discrete_actions=data.get("discrete_actions", []),
            grid_cols=data.get("grid_cols", 0),
            grid_rows=data.get("grid_rows", 0),
            grid_col_letters=data.get("grid_col_letters", []),
            numeric_min=data.get("numeric_min"),
            numeric_max=data.get("numeric_max"),
            numeric_prefix=data.get("numeric_prefix", ""),
            case_sensitive=data.get("case_sensitive", False),
            aliases=data.get("aliases", {}),
        )


def _extract_action_section(rules_text: str) -> str:
    """Extract ACTION FORMAT section or similar instruction blocks from rules text."""
    pattern = re.compile(r"ACTION\s+FORMAT\s*:?\s*(.*?)(?=\n[A-Z\s]{4,}|\Z)", re.DOTALL | re.IGNORECASE)
    match = pattern.search(rules_text)
    if match:
        return match.group(1).strip()
    return ""


def parse_action_grammar(rules_text: str, sample_turn: dict | None = None) -> ActionGrammar:
    """Parse rules text and optional sample_turn to construct ActionGrammar."""
    action_section = _extract_action_section(rules_text)
    combined_text = f"{rules_text}\n{action_section}"
    sample_legal = (sample_turn or {}).get("legal_actions")

    # 1. Check for discrete action keywords (e.g. roll | hold, pass, defect | cooperate)
    discrete_match = re.search(r"Reply with one word:\s*([a-zA-Z0-9_\s\|/]+)", action_section, re.IGNORECASE)
    if not discrete_match:
        discrete_match = re.search(r"choose:\s*([a-zA-Z0-9_\s\|/]+)", action_section, re.IGNORECASE)

    if discrete_match:
        raw_opts = re.split(r"[\s\|/]+", discrete_match.group(1).strip())
        opts = [o.lower() for o in raw_opts if o and o.isalpha()]
        if opts:
            aliases = {}
            for o in opts:
                aliases[o.upper()] = o
                aliases[o.capitalize()] = o
            return ActionGrammar(
                kind="discrete",
                discrete_actions=opts,
                aliases=aliases,
            )

    # If sample_turn has small finite list of string words (e.g. ["roll", "hold"])
    if sample_legal and len(sample_legal) <= 10 and all(a.isalpha() for a in sample_legal):
        opts = [a.lower() for a in sample_legal]
        aliases = {a.upper(): a for a in opts}
        aliases.update({a.capitalize(): a for a in opts})
        return ActionGrammar(kind="discrete", discrete_actions=opts, aliases=aliases)

    # 2. Check for Grid / Board games (e.g. "A 3x3 grid", "A1", columns A-C, rows 1-3)
    grid_dim = re.search(r"(\d+)\s*x\s*(\d+)\s*(?:grid|board)", combined_text, re.IGNORECASE)
    has_coord = bool(re.search(r"[A-Z]\d+", action_section) or re.search(r"column letter \+ row number", action_section, re.IGNORECASE))

    if grid_dim or has_coord:
        cols = int(grid_dim.group(1)) if grid_dim else 3
        rows = int(grid_dim.group(2)) if grid_dim else cols
        col_letters = [chr(ord("A") + i) for i in range(cols)]
        return ActionGrammar(
            kind="grid",
            grid_cols=cols,
            grid_rows=rows,
            grid_col_letters=col_letters,
        )

    # If sample_turn has grid-like actions (e.g. ["A1", "B2", ...])
    if sample_legal and any(re.match(r"^[A-Z]\d+$", str(a)) for a in sample_legal):
        cols_seen = set()
        rows_seen = set()
        for a in sample_legal:
            m = re.match(r"^([A-Z])(\d+)$", str(a))
            if m:
                cols_seen.add(ord(m.group(1)) - ord("A") + 1)
                rows_seen.add(int(m.group(2)))
        cols = max(cols_seen) if cols_seen else 3
        rows = max(rows_seen) if rows_seen else cols
        return ActionGrammar(
            kind="grid",
            grid_cols=cols,
            grid_rows=rows,
            grid_col_letters=[chr(ord("A") + i) for i in range(cols)],
        )

    # 3. Check for Numeric range (e.g. "guess <n>", "between 1 and 100", "range 1-100")
    num_range = re.search(r"(?:range|between)\s+(\d+)\s*(?:and|-|to)\s*(\d+)", combined_text, re.IGNORECASE)
    has_guess_prefix = bool(re.search(r"guess\s+<n>", action_section, re.IGNORECASE) or re.search(r'"guess\s+\d+"', action_section, re.IGNORECASE))

    if num_range:
        lo = int(num_range.group(1))
        hi = int(num_range.group(2))
        prefix = "guess " if has_guess_prefix else ""
        return ActionGrammar(
            kind="numeric_range",
            numeric_min=lo,
            numeric_max=hi,
            numeric_prefix=prefix,
        )

    # 4. Default generic text
    return ActionGrammar(kind="generic")


def parse_observation_layout(obs_text: str) -> dict[str, Any]:
    """Extract structured data from an observation string."""
    if not obs_text:
        return {}

    layout: dict[str, Any] = {
        "raw_length": len(obs_text),
        "lines": [line.rstrip() for line in obs_text.splitlines()],
    }

    # Extract round / turn information
    round_match = re.search(r"round\s+(\d+)(?:\s+of\s+(\d+))?", obs_text, re.IGNORECASE)
    if round_match:
        layout["round"] = int(round_match.group(1))
        if round_match.group(2):
            layout["max_rounds"] = int(round_match.group(2))

    turn_match = re.search(r"turn\s+(\d+)", obs_text, re.IGNORECASE)
    if turn_match:
        layout["turn"] = int(turn_match.group(1))

    # Extract seat / player info
    seat_match = re.search(r"You are (?:Player|Seat)\s*(\d+)", obs_text, re.IGNORECASE)
    if seat_match:
        layout["seat"] = int(seat_match.group(1))

    # Extract grid board if present (lines with rows like " 1 . X O" or " 1 . . .")
    grid_lines = []
    for line in layout["lines"]:
        if re.match(r"^\s*\d{1,2}\s+[.XO\s]+$", line):
            # Parse cells
            cells = re.findall(r"[.XO]", line)
            if cells:
                grid_lines.append(cells)
    if grid_lines:
        layout["grid"] = grid_lines
        layout["grid_size"] = (len(grid_lines), len(grid_lines[0]))

    # Extract scores / banked points (e.g. "banked: [10, 20]" or "Scores: X: 1, O: 0")
    banked_match = re.search(r"banked[:\s]+(\d+)[,\s]+(\d+)", obs_text, re.IGNORECASE)
    if banked_match:
        layout["banked_scores"] = [int(banked_match.group(1)), int(banked_match.group(2))]

    return layout
