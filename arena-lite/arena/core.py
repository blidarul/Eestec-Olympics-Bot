"""Game base class shared by every tournament and practice game.

See docs/ARCHITECTURE.md section 3 for the contract. Games are pure Python,
stdlib only, deterministic given (variant, seed).
"""
from __future__ import annotations

import random
from typing import Any

CATEGORIES = ("bluff", "deals", "read", "guess", "think", "truth", "guard", "practice")
MAX_LEGAL_LIST = 50  # above this, legal_actions() returns None


class Game:
    """Two-player text game. Subclass it once per module."""

    id: str = ""
    name: str = ""
    category: str = ""
    blurb: str = ""  # one sentence for the audience: what makes this game fun
    howto: str = ""  # one or two plain sentences for the audience: how the game is played and won
    duplicate_safe: bool = False
    """Round robin (duplicate boards, docs/ARCHITECTURE.md 5.2): may the second game of a board replay
    the first game's exact deal (same seed) with the seats swapped? True ONLY when the deal holds
    nothing hidden from either player (no private information of any kind) and no hidden future
    randomness (nothing drawn or rolled later), so a container that played the first game learns nothing from it
    that its opponent did not see. Otherwise (the default) the second game gets a FRESH deal: same game
    and variant, seats swapped, a different seed. Every registered game sets this explicitly in its own
    class body (arena/tests/test_roundrobin.py enforces it), so a new game cannot forget to decide."""

    def __init__(self, variant: dict, seed: int):
        self.variant = dict(variant)
        self.seed = seed
        self.rng = random.Random(seed)

    # ---- metadata -------------------------------------------------------
    @classmethod
    def variants(cls) -> list[dict]:
        """At least two variants; each dict has a short "label"."""
        raise NotImplementedError

    def rules(self) -> str:
        """Complete rules for this variant, including the exact action format."""
        raise NotImplementedError

    # ---- turn structure -------------------------------------------------
    def to_move(self) -> list[int]:
        """Seats that must act now: [0], [1] or [0, 1]; [] when the game is over."""
        raise NotImplementedError

    def observation(self, seat: int) -> str:
        raise NotImplementedError

    def legal_actions(self, seat: int) -> list[str] | None:
        """Full list when it has at most MAX_LEGAL_LIST entries, else None."""
        raise NotImplementedError

    def normalize(self, seat: int, action: str) -> str | None:
        """Canonical form of a legal action, or None when illegal."""
        raise NotImplementedError

    def apply(self, actions: dict[int, str]) -> None:
        """Apply normalized actions for every seat in to_move()."""
        raise NotImplementedError

    def is_over(self) -> bool:
        raise NotImplementedError

    def result(self) -> dict:
        """{"winner": 0 | 1 | None, "scores": [s0, s1], "reason": str}"""
        raise NotImplementedError

    def frame(self) -> dict:
        """Full-information spectator view for the renderer (JSON-serializable)."""
        raise NotImplementedError

    # ---- the match chat (optional) ---------------------------------------
    def said(self, seat: int, action: str) -> str | None:
        """Talk games only (where talking IS the game move): the words this accepted, normalized move
        says to the opponent, or None. The arena adds them to the match chat as a "move" line, so the
        whole conversation reads in one place (the board then shows the game state, not a second chat).
        Default: game moves say nothing."""
        return None

    def on_chat(self, seat: int, text: str) -> None:
        """Speech rules only. The chat is not part of any game: it is the match's own channel
        (arena/chat.py), read by both bots in every message and stored once per match. A game whose
        rules restrict what a player may SAY (e.g. a forbidden word) overrides this to check every
        accepted chat line of `seat`; the arena calls it before that step's moves are applied, and
        the game may end itself here. Never copy chat lines into the game's own state or frame:
        record only the verdict (what was said that broke the rule). Default: chat has no effect."""
        return None

    # ---- helpers for subclasses ----------------------------------------
    @staticmethod
    def clean(action: Any) -> str:
        """Lower-case, trimmed, single-spaced string form of a raw action."""
        if not isinstance(action, str):
            return ""
        return " ".join(action.strip().lower().split())

    @staticmethod
    def cap_list(actions: list[str]) -> list[str] | None:
        return actions if len(actions) <= MAX_LEGAL_LIST else None

    @classmethod
    def info(cls) -> dict:
        return {
            "id": cls.id,
            "name": cls.name,
            "category": cls.category,
            "blurb": cls.blurb,
            "howto": cls.howto,
            "variants": [v.get("label", "") for v in cls.variants()],
        }
