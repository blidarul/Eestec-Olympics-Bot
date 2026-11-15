"""Game Family Classifier for 10-Minute Prep.
Classifies unknown rules text into 1 of 7 target game families and extracts structural game properties.
Owned by agent `bld`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GameClassification:
    family: str  # grid_board | deduction | dice_push | cards_hidden | matrix_simultaneous | negotiation | qa_guardrails
    confidence: float
    is_deterministic: bool
    has_hidden_information: bool
    is_simultaneous: bool
    turn_structure: str  # alternating | simultaneous | push_your_luck
    features: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "confidence": round(self.confidence, 3),
            "is_deterministic": self.is_deterministic,
            "has_hidden_information": self.has_hidden_information,
            "is_simultaneous": self.is_simultaneous,
            "turn_structure": self.turn_structure,
            "features": self.features,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameClassification:
        return cls(
            family=data.get("family", "grid_board"),
            confidence=float(data.get("confidence", 0.5)),
            is_deterministic=bool(data.get("is_deterministic", True)),
            has_hidden_information=bool(data.get("has_hidden_information", False)),
            is_simultaneous=bool(data.get("is_simultaneous", False)),
            turn_structure=data.get("turn_structure", "alternating"),
            features=data.get("features", {}),
        )


# Keywords & weights for scoring rules text against each family
_FAMILY_KEYWORDS = {
    "grid_board": [
        ("grid", 3.0), ("board", 2.0), ("column", 2.5), ("row", 2.0), ("diagonal", 3.0),
        ("connect", 3.0), ("cell", 2.5), ("straight line", 3.0), ("tic-tac-toe", 5.0),
        ("marks in a row", 4.0), ("empty cell", 3.0), ("coordinates", 2.0),
        ("nim", 5.0), ("pile", 3.0), ("heap", 3.0), ("token", 2.5), ("tokens", 2.5),
        ("reversi", 5.0), ("chess", 5.0), ("checkers", 5.0), ("hex", 5.0), ("take the last", 4.0),
    ],
    "deduction": [
        ("secret number", 4.0), ("secret", 2.5), ("higher", 3.0), ("lower", 3.0),
        ("feedback", 2.5), ("guess", 3.0), ("range", 2.0), ("interval", 2.0),
        ("binary search", 4.0), ("haystack", 2.0), ("correct", 1.5), ("clue", 3.0),
        ("wordle", 5.0), ("secret word", 5.0), ("letter", 3.0), ("green", 2.5),
        ("yellow", 2.5), ("grey", 2.0), ("gray", 2.0), ("hangman", 5.0),
    ],
    "dice_push": [
        ("die", 3.0), ("dice", 4.0), ("roll", 3.5), ("banked", 4.0), ("hold", 3.5),
        ("turn total", 4.0), ("push-your-luck", 5.0), ("snake eyes", 5.0),
        ("wipe", 3.0), ("six-sided", 3.0), ("bust", 3.0),
    ],
    "cards_hidden": [
        ("card", 4.0), ("deck", 4.0), ("deal", 3.0), ("hand", 3.0), ("bet", 3.5),
        ("pot", 2.0), ("fold", 4.0), ("call", 3.0), ("raise", 3.5), ("bluff", 3.0),
        ("chips", 3.5), ("poker", 5.0), ("showdown", 4.0),
    ],
    "matrix_simultaneous": [
        ("simultaneous", 5.0), ("both players choose", 4.0), ("matrix", 4.0),
        ("cooperate", 4.0), ("defect", 4.0), ("payoff", 3.5), ("dilemma", 4.0),
        ("rock paper scissors", 5.0), ("matching pennies", 5.0),
    ],
    "negotiation": [
        ("bargain", 5.0), ("negotiat", 5.0), ("propose", 4.0), ("trade", 4.0),
        ("offer", 3.5), ("agree", 3.0), ("reject", 3.0), ("deal", 2.5),
        ("surplus", 3.5), ("discount", 3.0), ("accept", 4.5), ("counter-offer", 4.5),
        ("counter", 3.5), ("split", 3.5), ("agreement", 3.5), ("division", 3.0), ("share", 2.5),
    ],
    "qa_guardrails": [
        ("document", 4.0), ("passage", 4.0), ("forbidden", 5.0), ("topic", 3.5),
        ("grounding", 4.0), ("hallucination", 5.0), ("question", 2.5),
        ("adversarial", 4.0), ("guardrail", 5.0), ("jailbreak", 5.0),
    ],
}


def classify_rules(rules_text: str) -> GameClassification:
    """Analyze game rules text and classify it into one of the 7 game families."""
    lower_text = rules_text.lower()
    scores: dict[str, float] = {family: 0.0 for family in _FAMILY_KEYWORDS}

    for family, keyword_weights in _FAMILY_KEYWORDS.items():
        for kw, weight in keyword_weights:
            # Word boundary regex for accurate keyword hits
            pattern = r"\b" + re.escape(kw) + r"\b"
            matches = len(re.findall(pattern, lower_text))
            if matches > 0:
                scores[family] += weight * min(matches, 5)

    # Determine winning family
    best_family = max(scores, key=scores.get)
    max_score = scores[best_family]
    total_score = sum(scores.values()) or 1.0
    confidence = min(1.0, max_score / (total_score * 0.6 + 1.0))

    # Detect structural properties
    has_dice = bool(re.search(r"\b(dice|die|roll|rolling|coin\s+flip|push-your-luck)\b", lower_text)) and not bool(re.search(r"\b(roll-call|bankroll)\b", lower_text))
    has_secret = bool(re.search(r"\b(secret|hidden|concealed|private card)\b", lower_text))
    is_simul = bool(re.search(r"\b(simultaneous|both players move|same time)\b", lower_text))

    is_chance = has_dice or bool(re.search(r"\b(roll\s+dice|roll\s+the|coin\s+toss|roulette|spinner)\b", lower_text))
    is_deterministic = not is_chance
    has_hidden_info = has_secret or (best_family in ("deduction", "cards_hidden"))

    turn_structure = "alternating"
    if is_simul or best_family == "matrix_simultaneous":
        turn_structure = "simultaneous"
    elif best_family == "dice_push":
        turn_structure = "push_your_luck"

    features = {
        "scores": {k: round(v, 1) for k, v in scores.items() if v > 0},
        "has_dice": has_dice,
        "has_secret": has_secret,
    }

    return GameClassification(
        family=best_family,
        confidence=confidence,
        is_deterministic=is_deterministic,
        has_hidden_information=has_hidden_info,
        is_simultaneous=is_simul,
        turn_structure=turn_structure,
        features=features,
    )
