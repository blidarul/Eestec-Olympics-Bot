"""Seeded randomness for pools, game picks and variants.

Every value is a pure function of its inputs (sha256-derived seeds, independent
of PYTHONHASHSEED, platform and call order):
- pick_pool(tournament_seed, n, game_ids)            -> sorted list of n game ids
- pick_game(tournament_seed, match_id, index, pool)  -> game id + variant + game seed

Within one match the games are drawn from the pool without replacement (a fresh
seeded shuffle per cycle), so a best-of-3 from a pool of 4 shows 3 different
games; the draw for game k is still determined by (seed, match id, k, pool).
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field


def derive_seed(*parts) -> int:
    text = "|".join(str(p) for p in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def rng_for(*parts) -> random.Random:
    return random.Random(derive_seed(*parts))


def new_seed() -> int:
    return random.SystemRandom().randrange(1, 1_000_000_000)


def pick_pool(tournament_seed: int, n: int, game_ids) -> list[str]:
    ids = sorted(game_ids)
    if n >= len(ids):
        return ids
    return sorted(rng_for("pool", tournament_seed).sample(ids, n))


@dataclass
class Pick:
    game_id: str
    variant_index: int
    variant: dict = field(default_factory=dict)
    game_seed: int = 0


def pick_game_id(tournament_seed: int, match_id: str, game_index: int, pool) -> str:
    ids = sorted(pool)
    if not ids:
        raise ValueError("empty game pool")
    cycle, pos = divmod(game_index - 1, len(ids))
    order = ids[:]
    rng_for("order", tournament_seed, match_id, cycle).shuffle(order)
    return order[pos]


def pick_game(tournament_seed: int, match_id: str, game_index: int, pool, registry=None) -> Pick:
    """Game + variant + per-game seed for game `game_index` (1-based) of a match.

    `registry` maps game id -> Game class (default: arena.registry.all_games()).
    """
    if registry is None:
        from . import registry as reg
        registry = reg.all_games()
    game_id = pick_game_id(tournament_seed, match_id, game_index, pool)
    return pick_variant(tournament_seed, match_id, game_index, registry[game_id])


def pick_variant(tournament_seed: int, match_id: str, game_index: int, game_cls) -> Pick:
    variants = game_cls.variants()
    rng = rng_for("variant", tournament_seed, match_id, game_index, game_cls.id)
    vi = rng.randrange(len(variants))
    gseed = derive_seed("game", tournament_seed, match_id, game_index) % 2_147_483_647
    return Pick(game_cls.id, vi, dict(variants[vi]), gseed)
