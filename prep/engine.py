"""Prep Engine Coordinator.
Coordinates classification, grammar parsing, heuristic precomputation, and memory serialization.
Owned by agent `bld`.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from typing import Any

from optimization.serializer import (
    atomic_save_json,
    game_memory_dir,
)
from .action_parser import parse_action_grammar, parse_observation_layout
from .classifier import classify_rules
from .heuristics import compute_heuristics
from .synthesis import save_synthesized_simulator


def compute_fingerprint(variants: list[dict[str, Any]]) -> str:
    """Compute deterministic fingerprint from variant rules texts."""
    text = "\n".join(v.get("label", "") + "\n" + v.get("rules", "") for v in variants)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class PrepEngine:
    def __init__(self, memory_dir: str = "/memory"):
        self.memory_dir = memory_dir

    def run_prep(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Execute the 10-minute prep phase for the provided game message."""
        start_time = time.time()
        game_id = msg.get("game_id", "unknown_game")
        game_name = msg.get("game_name", game_id)
        variants = msg.get("variants") or []
        budget_seconds = float(msg.get("seconds", 600.0))

        dest_dir = game_memory_dir(self.memory_dir, game_id)
        fp = compute_fingerprint(variants)

        print(
            f"[prep/engine] starting prep for {game_name} ({game_id}) with {len(variants)} variant(s), "
            f"budget {budget_seconds:.0f}s",
            file=sys.stderr,
        )

        variants_data = []
        overall_classification = None

        for idx, variant in enumerate(variants):
            label = variant.get("label", f"variant_{idx}")
            rules = variant.get("rules", "")
            sample_turn = variant.get("sample_turn")

            # 1. Classification
            classification = classify_rules(rules)
            if overall_classification is None:
                overall_classification = classification

            # 2. Grammar & observation layout parsing
            grammar = parse_action_grammar(rules, sample_turn)
            obs_layout = parse_observation_layout(sample_turn.get("observation", "") if sample_turn else "")

            # 3. Precomputed heuristics
            heuristics = compute_heuristics(classification, grammar, rules)

            # 4. Validate grammar against sample turn
            sample_validation_passed = True
            if sample_turn and sample_turn.get("legal_actions"):
                for action in sample_turn["legal_actions"]:
                    if not grammar.validate(action, sample_turn["legal_actions"]):
                        sample_validation_passed = False
                        break

            variants_data.append({
                "label": label,
                "classification": classification.to_dict(),
                "grammar": grammar.to_dict(),
                "obs_layout": obs_layout,
                "heuristics": heuristics,
                "sample_validation_passed": sample_validation_passed,
            })

        # Save prep artifacts atomically to /memory/<game_id>/
        manifest = {
            "game_id": game_id,
            "game_name": game_name,
            "fingerprint": fp,
            "family": overall_classification.family if overall_classification else "generic",
            "variants": variants_data,
            "prepped_at": time.time(),
            "elapsed_seconds": round(time.time() - start_time, 3),
        }

        atomic_save_json(os.path.join(dest_dir, "manifest.json"), manifest)
        if overall_classification:
            atomic_save_json(os.path.join(dest_dir, "classification.json"), overall_classification.to_dict())
            if variants_data:
                first_grammar = parse_action_grammar(variants[0].get("rules", ""), variants[0].get("sample_turn"))
                save_synthesized_simulator(dest_dir, overall_classification, first_grammar, game_id)

        # Save raw samples
        samples = {v.get("label", ""): v["sample_turn"] for v in variants if v.get("sample_turn")}
        if samples:
            atomic_save_json(os.path.join(dest_dir, "samples.json"), {"game_id": game_id, "samples": samples})

        elapsed = time.time() - start_time
        print(f"[prep/engine] finished prep for {game_id} in {elapsed:.2f}s", file=sys.stderr)

        return {
            "type": "ready",
            "game_id": game_id,
            "fingerprint": fp,
            "family": overall_classification.family if overall_classification else "generic",
            "elapsed_seconds": elapsed,
            "manifest_path": os.path.join(dest_dir, "manifest.json"),
        }
