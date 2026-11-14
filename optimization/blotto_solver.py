"""Game-Theoretic Allocation Generator for Colonel Blotto.
Precomputes mixed-strategy allocation portfolios tailored to field values
and army sizes during prep.
Owned by agent `bld`.
"""
from __future__ import annotations

import random
from typing import Any


def generate_blotto_allocations(
    soldiers: int = 100,
    fields: int = 5,
    values: list[int] | None = None,
    count: int = 30,
    seed: int = 42,
) -> list[list[int]]:
    """Precompute diverse strategic allocations for Colonel Blotto.
    Includes:
    1. Value-proportional allocation
    2. Concession profiles (giving up 1 or 2 low-value fields to guarantee high-value ones)
    3. Perturbed mixed-strategy profiles
    4. Equal split baseline
    """
    if values is None or len(values) != fields:
        values = [1] * fields

    rng = random.Random(seed + soldiers * 100 + fields)
    allocations: list[list[int]] = []

    def _normalize(weights: list[float], target_sum: int) -> list[int]:
        total_w = sum(weights)
        if total_w <= 0:
            base = target_sum // fields
            rem = target_sum - base * fields
            return [base + (1 if i < rem else 0) for i in range(fields)]
        raw = [int(w / total_w * target_sum) for w in weights]
        diff = target_sum - sum(raw)
        # Distribute remainder to highest weight fields
        sorted_indices = sorted(range(fields), key=lambda idx: weights[idx], reverse=True)
        for i in range(diff):
            raw[sorted_indices[i % fields]] += 1
        return raw

    # Profile 1: Equal baseline
    eq_w = [1.0] * fields
    allocations.append(_normalize(eq_w, soldiers))

    # Profile 2: Value-proportional
    v_w = [float(v) for v in values]
    allocations.append(_normalize(v_w, soldiers))

    # Profile 3: Concede lowest field(s) to dominate high-value fields
    sorted_field_indices = sorted(range(fields), key=lambda idx: values[idx])
    for low_idx in sorted_field_indices[:min(2, fields - 2)]:
        concede_w = [float(values[i]) if i != low_idx else 0.0 for i in range(fields)]
        allocations.append(_normalize(concede_w, soldiers))

    # Profile 4: Randomized / perturbed mixed strategies
    while len(allocations) < count:
        perturbed_w = []
        # Concede 0, 1, or 2 fields randomly
        concede_count = rng.choice([0, 1, 1, 2]) if fields >= 4 else 0
        conceded = set(rng.sample(range(fields), concede_count)) if concede_count else set()
        for idx in range(fields):
            if idx in conceded:
                perturbed_w.append(0.0)
            else:
                noise = rng.uniform(0.6, 1.4)
                perturbed_w.append(float(values[idx]) * noise + rng.uniform(0.1, 0.5))
        alloc = _normalize(perturbed_w, soldiers)
        if alloc not in allocations and sum(alloc) == soldiers:
            allocations.append(alloc)

    return allocations[:count]


def select_blotto_action(
    portfolio: list[list[int]],
    available_soldiers: int,
    fields: int = 5,
    round_no: int = 1,
) -> str:
    """Select a valid action from the precomputed portfolio or scale down if reserve differs."""
    if not portfolio:
        share = available_soldiers // fields
        rem = available_soldiers - share * (fields - 1)
        res = [share] * (fields - 1) + [rem]
        return " ".join(str(x) for x in res)

    # Filter or scale portfolio to available_soldiers
    valid_cands = [a for a in portfolio if sum(a) == available_soldiers and len(a) == fields]
    if valid_cands:
        chosen = random.choice(valid_cands)
        return " ".join(str(x) for x in chosen)

    # If soldiers differ (e.g. reserve mode), scale chosen portfolio item
    template = portfolio[(round_no - 1) % len(portfolio)]
    total_t = sum(template)
    if total_t > 0:
        scaled = [int(x * available_soldiers / total_t) for x in template]
        diff = available_soldiers - sum(scaled)
        for i in range(diff):
            scaled[i % fields] += 1
        return " ".join(str(x) for x in scaled)

    share = available_soldiers // fields
    rem = available_soldiers - share * (fields - 1)
    res = [share] * (fields - 1) + [rem]
    return " ".join(str(x) for x in res)
