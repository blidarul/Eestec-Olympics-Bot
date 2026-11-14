"""The match chat: one conversation between the two bots, independent of the games.

Every answer a bot sends has two parts:
  - the GAME MOVE (`action`, or the `ready` itself): defined by each game's rules;
  - the CHAT MOVE (`chat`, optional, at most CHAT_MAX characters): the same in every game.

Each line has a `kind`: "chat" (a chat move) or "move". In the games where talking IS the game move
(a message, an offer), the words of each accepted move are added
to the chat as a "move" line (`Game.said(seat, action)`), so the whole conversation of a match reads
in one place. Move lines are not speech-checked again (the game judged the move itself).

The chat belongs to the match, not to a game. It runs across all the games of a match (and sudden
death), every line is tagged with the phase it was said in (which game, before the game or during
play, which turn), and both bots read the WHOLE conversation in every message they receive
(`start`, `turn`, `end`). The results file stores it once, at match level (`doc["chat"]`); the game
records (timeline, study) never copy chat lines.

Games don't own the chat. A game whose rules also apply to what is said in the chat
listens to it through the optional `Game.on_chat(seat, text)` hook, which the match runner calls for
every accepted line before that step's moves are applied.
"""
from __future__ import annotations

from typing import Any

from . import config


def chat_text(msg: dict | None) -> str | None:
    """The chat move of a reply: `chat` (or the legacy `comment` alias) as one line of at most
    CHAT_MAX characters, or None. Anything that isn't a non-empty string is ignored."""
    if not msg:
        return None
    for key in ("chat", "comment"):
        c = msg.get(key)
        if isinstance(c, str) and c.strip():
            return " ".join(c.split())[: config.CHAT_MAX]
    return None


class MatchChat:
    """The shared chat of one match. `lines` is the stored log, oldest first."""

    def __init__(self, echo=None):
        self.lines: list[dict[str, Any]] = []
        self.echo = echo or (lambda s: None)

    def say(self, *, game: int, game_id: str, game_name: str, step: int, seat: int, team: str,
            text: str, kind: str = "chat") -> dict:
        """Record one line. kind "chat": an accepted chat move (step 0 = said with `ready`, before the
        game's first move); kind "move": the words of an accepted game move in a talk game."""
        line = {"n": len(self.lines) + 1, "game": game, "game_id": game_id, "game_name": game_name,
                "step": step, "phase": "study" if step == 0 else "play", "kind": kind, "seat": seat,
                "team": team, "text": text}
        self.lines.append(line)
        self.echo(f"  {team} {'says' if kind == 'chat' else 'moves, saying'}: {text}")
        return line

    def view(self, team: str) -> list[dict]:
        """The whole conversation as `team` reads it, oldest first."""
        return [{"from": "you" if c["team"] == team else "opponent", "game": c["game"],
                 "game_name": c.get("game_name"), "phase": c.get("phase") or ("study" if not c["step"] else "play"),
                 "turn": c["step"], "kind": c.get("kind", "chat"), "text": c["text"]} for c in self.lines]
