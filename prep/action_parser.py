"""Rules & Action Grammar Parser.
Extracts action format, coordinates/ranges/commands, and observation layout from rules and sample turns.
Owned by agent `bld`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


WORDS_BY_LENGTH = {
    3: ["cat", "dog", "run", "sun", "sky", "red", "big", "top", "air", "box"],
    4: ["play", "game", "time", "word", "star", "open", "line", "plan", "real", "gold"],
    5: ["slate", "crane", "audio", "raise", "stare", "roast", "adieu", "trace", "brick"],
    6: ["planet", "stream", "spring", "silver", "golden", "simple", "ground", "master"],
    7: ["balance", "playing", "explore", "freedom", "journey", "mystery", "dynamic", "plastic"],
    8: ["building", "strength", "computer", "universe", "mountain", "solution", "football"],
    9: ["knowledge", "algorithm", "discovery", "champion", "landscape", "beautiful"],
    10: ["basketball", "everything", "understand", "friendship", "foundation", "generation"],
}


@dataclass
class ActionGrammar:
    kind: str  # "grid" | "discrete" | "numeric_range" | "word" | "generic"
    discrete_actions: list[str] = field(default_factory=list)
    grid_cols: int = 0
    grid_rows: int = 0
    grid_col_letters: list[str] = field(default_factory=list)
    numeric_min: int | None = None
    numeric_max: int | None = None
    numeric_prefix: str = ""
    word_length: int | None = None
    word_prefix: str = ""
    examples: list[str] = field(default_factory=list)
    case: str = "lower"
    case_sensitive: bool = False
    aliases: dict[str, str] = field(default_factory=dict)
    forbidden_keywords: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

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

            col_ok = (0 <= col_idx < self.grid_cols) if self.grid_cols > 0 else (col_idx >= 0)
            row_ok = (0 <= row_idx < self.grid_rows) if self.grid_rows > 0 else (row_idx >= 0)
            if col_ok and row_ok:
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

        if self.kind == "word":
            if self.word_prefix and clean.lower().startswith(self.word_prefix.lower()):
                clean = clean[len(self.word_prefix):].strip()
            else:
                m = re.match(r"^(?:guess\s+)?([A-Za-z]+)$", clean, re.IGNORECASE)
                clean = m.group(1) if m else clean
            if not clean.isalpha():
                return False
            if self.word_length and len(clean) != self.word_length:
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

        if self.kind == "word":
            if self.word_prefix and clean.lower().startswith(self.word_prefix.lower()):
                w = clean[len(self.word_prefix):].strip()
            else:
                m = re.match(r"^(?:guess\s+)?([A-Za-z]+)$", clean, re.IGNORECASE)
                w = m.group(1) if m else clean
            case = getattr(self, "case", None) or ("upper" if self.case_sensitive else "lower")
            w_out = w.upper() if case == "upper" else w.lower()
            return f"{self.word_prefix}{w_out}" if self.word_prefix else w_out

        return clean

    def fallback_action(self, legal_actions: list[str] | None = None) -> str:
        """Return a safe fallback action guaranteed to be syntactically valid."""
        if legal_actions and len(legal_actions) > 0:
            return legal_actions[0]
        if self.examples:
            return self.examples[0]
        if self.discrete_actions:
            return self.discrete_actions[0]
        if self.kind == "grid":
            return "A1"
        if self.kind == "numeric_range" and self.numeric_min is not None:
            mid = (self.numeric_min + (self.numeric_max or self.numeric_min)) // 2
            return f"{self.numeric_prefix}{mid}".strip()
        if self.kind == "word":
            length = self.word_length or 5
            pre = self.word_prefix or ""
            cands = WORDS_BY_LENGTH.get(length, [])
            w = cands[0] if cands else ("words"[:length] if length <= 5 else ("word" * 3)[:length])
            case = getattr(self, "case", None) or ("upper" if self.case_sensitive else "lower")
            w_out = w.upper() if case == "upper" else w.lower()
            return f"{pre}{w_out}"
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
            "word_length": self.word_length,
            "word_prefix": self.word_prefix,
            "examples": self.examples,
            "case": getattr(self, "case", "upper" if self.case_sensitive else "lower"),
            "case_sensitive": self.case_sensitive,
            "aliases": self.aliases,
            "forbidden_keywords": self.forbidden_keywords,
            "parameters": self.parameters,
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
            word_length=data.get("word_length"),
            word_prefix=data.get("word_prefix", ""),
            examples=data.get("examples", []),
            case=data.get("case", "upper" if data.get("case_sensitive") else "lower"),
            case_sensitive=bool(data.get("case_sensitive", False) or data.get("case") == "upper"),
            aliases=data.get("aliases", {}),
            forbidden_keywords=data.get("forbidden_keywords", []),
            parameters=data.get("parameters", {}),
        )


def extract_forbidden_keywords(rules_text: str) -> list[str]:
    """Extract forbidden words or forbidden topic keywords from rules text (Rules 6.8, 6.9)."""
    keywords: set[str] = set()
    section = re.search(
        r"(?:FORBIDDEN|BANNED|PROHIBITED)\s*(?:WORDS?|TOPICS?|CONTENT|KEYWORDS?|PHRASES?)?\s*[:\-]\s*(.*?)(?=\n[A-Z\s]{4,}|\Z)",
        rules_text,
        re.DOTALL | re.IGNORECASE,
    )
    if section:
        raw = section.group(1).strip()
        for q in re.findall(r'["\']([^"\']+)["\']', raw):
            keywords.add(q.lower().strip())
        unquoted = re.sub(r'["\'][^"\']+["\']', ' ', raw)
        for item in re.split(r"[,;\n]+", unquoted):
            clean_item = item.strip().strip("-*• ")
            if clean_item and len(clean_item) < 40:
                keywords.add(clean_item.lower())

    patterns = [
        r'(?:do not|never|cannot|forbidden to)\s+(?:say|mention|use|write)\s+["\']([^"\']+)["\']',
        r'penalty\s+for\s+(?:saying|mentioning)\s+["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        for m in re.finditer(pat, rules_text, re.IGNORECASE):
            keywords.add(m.group(1).lower().strip())

    return sorted(list(keywords))


def extract_game_parameters(rules_text: str) -> dict[str, Any]:
    """Extract key game thresholds, caps, and parameters from rules text."""
    params: dict[str, Any] = {}

    target_match = re.search(r"(?:first to|reach|target(?: score)? of|score of)\s+(\d+)\s*(?:points|banked)?", rules_text, re.IGNORECASE)
    if target_match:
        params["target_score"] = int(target_match.group(1))

    cap_match = re.search(r"(?:move cap|max(?:imum)? (?:decisions|moves|turns)|cannot last more than)\s*:?\s*(?:after )?(\d+)", rules_text, re.IGNORECASE)
    if cap_match:
        params["move_cap"] = int(cap_match.group(1))

    connect_match = re.search(r"(?:get|connect)\s+(\d+)\s*(?:of your marks)?\s*in an?\s+(?:unbroken\s+)?(?:straight\s+)?line", rules_text, re.IGNORECASE)
    if not connect_match:
        connect_match = re.search(r"(\d+)-in-a-row", rules_text, re.IGNORECASE)
    if connect_match:
        params["connect_k"] = int(connect_match.group(1))

    dice_match = re.search(r"\b(one|two|three|four|\d+)\s+(?:six-sided\s+)?dice\b", rules_text, re.IGNORECASE)
    if dice_match:
        words = {"one": 1, "two": 2, "three": 3, "four": 4}
        d_raw = dice_match.group(1).lower()
        params["dice_count"] = words.get(d_raw) or (int(d_raw) if d_raw.isdigit() else 1)

    if re.search(r"snake\s*eyes", rules_text, re.IGNORECASE) or re.search(r"reset\s+to\s+0", rules_text, re.IGNORECASE):
        params["snake_eyes_reset"] = True

    return params


@dataclass
class ObservationSchema:
    has_grid: bool = False
    grid_rows: int = 0
    grid_cols: int = 0
    patterns: dict[str, str] = field(default_factory=dict)

    def extract(self, obs_text: str) -> dict[str, Any]:
        result = parse_observation_layout(obs_text)
        for key, pat in self.patterns.items():
            if key not in result:
                m = re.search(pat, obs_text, re.IGNORECASE)
                if m:
                    try:
                        result[key] = int(m.group(1))
                    except ValueError:
                        result[key] = m.group(1).strip()
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_grid": self.has_grid,
            "grid_rows": self.grid_rows,
            "grid_cols": self.grid_cols,
            "patterns": self.patterns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservationSchema:
        return cls(
            has_grid=bool(data.get("has_grid", False)),
            grid_rows=int(data.get("grid_rows", 0)),
            grid_cols=int(data.get("grid_cols", 0)),
            patterns=data.get("patterns", {}),
        )


def infer_observation_schema(sample_obs: str) -> ObservationSchema:
    """Infer field extraction regexes and layout structure from a real sample observation."""
    if not sample_obs:
        return ObservationSchema()

    patterns: dict[str, str] = {}
    candidate_keys = [
        ("round", r"round\s+(\d+)"),
        ("turn", r"turn\s+(\d+)"),
        ("seat", r"(?:player|seat)\s+(\d+)"),
        ("score", r"(?:score|points)[^:\d]*[:\s]+(\d+)"),
        ("secret", r"(?:secret(?: number)?|hidden)[^:\d]*[:\s]+(\d+)"),
        ("banked", r"banked[^:\d]*[:\s]+(\d+)"),
        ("turn_total", r"turn total[^:\d]*[:\s]+(\d+)"),
    ]

    for key, pat in candidate_keys:
        if re.search(pat, sample_obs, re.IGNORECASE):
            patterns[key] = pat

    layout = parse_observation_layout(sample_obs)
    has_grid = bool(layout.get("grid"))
    grid_size = layout.get("grid_size", (0, 0))

    return ObservationSchema(
        has_grid=has_grid,
        grid_rows=grid_size[0],
        grid_cols=grid_size[1],
        patterns=patterns,
    )


def _extract_action_section(rules_text: str) -> str:
    """Extract ACTION FORMAT section or similar instruction blocks from rules text."""
    pattern = re.compile(r"(?i:ACTION\s+FORMAT)\s*:?\s*(.*?)(?=\n[A-Z][A-Z0-9\s_]{2,}(?:\([^\)]*\))?\s*\n|\Z)", re.DOTALL)
    match = pattern.search(rules_text)
    if match:
        return match.group(1).strip()
    return ""


def parse_action_grammar(rules_text: str, sample_turn: dict | None = None) -> ActionGrammar:
    """Parse rules text and optional sample_turn to construct ActionGrammar."""
    action_section = _extract_action_section(rules_text)
    combined_text = f"{rules_text}\n{action_section}"
    sample_legal = (sample_turn or {}).get("legal_actions")
    forbidden = extract_forbidden_keywords(rules_text)
    params = extract_game_parameters(rules_text)

    grid_dim = re.search(r"(\d+)\s*x\s*(\d+)\s*(?:grid|board)", combined_text, re.IGNORECASE)
    extracted_examples = [q.strip() for q in re.findall(r'["\']([^"\']+)["\']', action_section) if q.strip() and len(q) < 40 and '<' not in q]
    has_coord = bool(
        re.search(r"column letter \+ row number", action_section, re.IGNORECASE)
        or (grid_dim and re.search(r"\b[A-Za-z]\d+\b", action_section))
        or (extracted_examples and any(re.match(r"^[A-Za-z]\d+$", e) for e in extracted_examples))
    )
    num_range = re.search(r"(?:range|between)\s+(\d+)\s*(?:and|-|to)\s*(\d+)", combined_text, re.IGNORECASE)
    has_guess_prefix = bool(re.search(r"guess\s+<n>", action_section, re.IGNORECASE) or re.search(r'"guess\s+\d+"', action_section, re.IGNORECASE))

    word_len_m = re.search(r"\b(\d+)[-\s]letters?\b", combined_text, re.IGNORECASE)
    if not word_len_m:
        word_len_m = re.search(r"\b(?:word\s+length|word\s+size|letter\s+count|length\s+of\s+(?:the\s+)?word)\s*(?:of|=|:)?\s*(\d+)\b", combined_text, re.IGNORECASE)
    w_words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    parsed_word_len = None
    if word_len_m:
        parsed_word_len = int(word_len_m.group(1))
    else:
        for name, val in w_words.items():
            if re.search(rf"\b{name}[-\s]letters?\b", combined_text, re.IGNORECASE):
                parsed_word_len = val
                break
    has_word_clues = bool(re.search(r"\b(?:wordle|secret word|hangman|anagram)\b", combined_text, re.IGNORECASE))
    guess_word_m = bool(re.search(r"guess\s+(?:a\s+)?word", action_section, re.IGNORECASE))
    word_game = (parsed_word_len is not None and has_word_clues) or (has_word_clues and (guess_word_m or "guess <word>" in action_section.lower()))
    if re.search(r"\b(?:bulls and cows|mastermind|secret code)\b", combined_text, re.IGNORECASE):
        word_game = False

    grammar: ActionGrammar

    # 1. Check for discrete action keywords (e.g. roll | hold, pass, defect | cooperate)
    discrete_match = re.search(r"Reply with (?:exactly )?one word:\s*([^\n\r]+)", action_section, re.IGNORECASE)
    if not discrete_match:
        discrete_match = re.search(r"choose:\s*([^\n\r]+)", action_section, re.IGNORECASE)

    if discrete_match and not word_game:
        raw_opts = re.split(r"[\s\|/]+", discrete_match.group(1).strip())
        opts = [o.lower() for o in raw_opts if o and o.isalpha()]
        if opts:
            aliases = {}
            for o in opts:
                aliases[o.upper()] = o
                aliases[o.capitalize()] = o
            grammar = ActionGrammar(
                kind="discrete",
                discrete_actions=opts,
                aliases=aliases,
            )
        else:
            grammar = ActionGrammar(kind="generic")

    # If sample_turn has small finite list of string words (e.g. ["roll", "hold"])
    elif sample_legal and len(sample_legal) <= 10 and all(a.isalpha() for a in sample_legal):
        opts = [a.lower() for a in sample_legal]
        aliases = {a.upper(): a for a in opts}
        aliases.update({a.capitalize(): a for a in opts})
        grammar = ActionGrammar(kind="discrete", discrete_actions=opts, aliases=aliases)

    # 2. Check for Grid / Board games (e.g. "A 3x3 grid", "A1", columns A-C, rows 1-3)
    elif grid_dim or has_coord:
        cols = int(grid_dim.group(1)) if grid_dim else 3
        rows = int(grid_dim.group(2)) if grid_dim else cols
        col_letters = [chr(ord("A") + i) for i in range(cols)]
        grammar = ActionGrammar(
            kind="grid",
            grid_cols=cols,
            grid_rows=rows,
            grid_col_letters=col_letters,
        )

    # If sample_turn has grid-like actions (e.g. ["A1", "B2", ...])
    elif sample_legal and any(re.match(r"^[A-Z]\d+$", str(a)) for a in sample_legal):
        cols_seen = set()
        rows_seen = set()
        for a in sample_legal:
            m = re.match(r"^([A-Z])(\d+)$", str(a))
            if m:
                cols_seen.add(ord(m.group(1)) - ord("A") + 1)
                rows_seen.add(int(m.group(2)))
        cols = max(cols_seen) if cols_seen else 3
        rows = max(rows_seen) if rows_seen else cols
        grammar = ActionGrammar(
            kind="grid",
            grid_cols=cols,
            grid_rows=rows,
            grid_col_letters=[chr(ord("A") + i) for i in range(cols)],
        )

    # 3. Check for Word / Wordle games (e.g. 5-letter word, guess word, wordle)
    elif word_game:
        w_len = parsed_word_len or (5 if "wordle" in combined_text.lower() else None)
        w_pre = "guess " if re.search(r"guess\s+", action_section, re.IGNORECASE) else ""
        word_examples = [e for e in extracted_examples if any(c.isalpha() for c in e) and "<" not in e]
        if not word_examples and w_len and w_len in WORDS_BY_LENGTH:
            word_examples = [f"{w_pre}{w}" for w in WORDS_BY_LENGTH[w_len][:5]]
        elif not word_examples:
            word_examples = [f"{w_pre}{w}" for w in ["play", "game", "word", "slate", "planet"]]
        is_upper = bool(
            re.search(r"\b(?:upper\s*case|all\s*caps|capital\s*letters?)\b", combined_text, re.IGNORECASE)
            or (sample_legal and any(str(a).isupper() and len(str(a)) > 1 for a in sample_legal))
            or (extracted_examples and any(e.isupper() and len(e) > 1 for e in extracted_examples))
        )
        case = "upper" if is_upper else "lower"
        if is_upper:
            word_examples = [e.upper() for e in word_examples]
        grammar = ActionGrammar(
            kind="word",
            word_length=w_len,
            word_prefix=w_pre,
            examples=word_examples,
            case=case,
            case_sensitive=is_upper,
        )

    # 4. Check for Numeric range (e.g. "guess <n>", "between 1 and 100", "range 1-100")
    elif num_range:
        lo = int(num_range.group(1))
        hi = int(num_range.group(2))
        prefix = "guess " if has_guess_prefix else ""
        grammar = ActionGrammar(
            kind="numeric_range",
            numeric_min=lo,
            numeric_max=hi,
            numeric_prefix=prefix,
        )

    # 5. Default generic text
    else:
        grammar = ActionGrammar(kind="generic")

    if not grammar.examples and extracted_examples:
        grammar.examples = [e for e in extracted_examples if "<" not in e][:8]

    grammar.forbidden_keywords = forbidden
    params["examples"] = grammar.examples
    grammar.parameters = params
    return grammar


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

    # Extract deduction / guessing sections strictly separating our guesses from opponent guesses
    if "Your guesses" in obs_text or "opponent guessed" in obs_text.lower():
        parts = obs_text.split("Opponent's guesses")
        my_sec = parts[0]
        opp_sec = parts[1] if len(parts) > 1 else ""

        my_guesses = []
        for m in re.finditer(r"(?:you guessed|\bguess)\s+(\d+)\s*->\s*(higher|lower|correct|above|below)", my_sec, re.IGNORECASE):
            my_guesses.append({"guess": int(m.group(1)), "feedback": m.group(2).lower()})

        opp_guesses = []
        for m in re.finditer(r"(?:opponent guessed|\bguess)\s+(\d+)\s*->\s*(higher|lower|correct|above|below)", opp_sec, re.IGNORECASE):
            opp_guesses.append({"guess": int(m.group(1)), "feedback": m.group(2).lower()})

        layout["my_guesses"] = my_guesses
        layout["opponent_guesses"] = opp_guesses

    return layout
