"""Discovers Game subclasses in arena/games (tournament) and arena/practice."""
from __future__ import annotations

import importlib
import pkgutil

from .core import Game

_cache: dict[str, dict[str, type[Game]]] = {}


def _discover(package: str) -> dict[str, type[Game]]:
    if package in _cache:
        return _cache[package]
    found: dict[str, type[Game]] = {}
    pkg = importlib.import_module(f"arena.{package}")
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        module = importlib.import_module(f"arena.{package}.{mod.name}")
        for obj in vars(module).values():
            if isinstance(obj, type) and issubclass(obj, Game) and obj is not Game and obj.id:
                found[obj.id] = obj
    _cache[package] = dict(sorted(found.items()))
    return _cache[package]


def tournament_games() -> dict[str, type[Game]]:
    return _discover("games")


def practice_games() -> dict[str, type[Game]]:
    return _discover("practice")


def all_games() -> dict[str, type[Game]]:
    return {**tournament_games(), **practice_games()}


def get(game_id: str) -> type[Game]:
    games = all_games()
    if game_id not in games:
        raise KeyError(f"unknown game {game_id!r}")
    return games[game_id]
