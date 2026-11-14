"""Prep Engine Coordinator.
Coordinates classification, grammar parsing, heuristic precomputation, and memory serialization.
Owned by agent `bld`.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
import re
from typing import Any

from optimization.serializer import (
    atomic_save_json,
    game_memory_dir,
)
from .action_parser import (
    infer_observation_schema,
    parse_action_grammar,
    parse_observation_layout,
)
from .classifier import classify_rules
from .heuristics import compute_heuristics
from .synthesis import save_synthesized_simulator
from .tools import synthesize_tools


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

        llm = None
        if msg.get("llm"):
            from core.llm import LLM
            llm = LLM(msg["llm"])
        elif hasattr(self, "llm") and self.llm:
            llm = self.llm

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

            # 2. Grammar & observation layout/schema parsing
            grammar = parse_action_grammar(rules, sample_turn)
            sample_obs = sample_turn.get("observation", "") if sample_turn else ""
            obs_layout = parse_observation_layout(sample_obs)
            obs_schema = infer_observation_schema(sample_obs)

            # 3. Precomputed heuristics
            heuristics = compute_heuristics(classification, grammar, rules)

            # 4. Validate grammar against sample turn
            sample_validation_passed = True
            if sample_turn and sample_turn.get("legal_actions"):
                for action in sample_turn["legal_actions"]:
                    if not grammar.validate(action, sample_turn["legal_actions"]):
                        sample_validation_passed = False
                        break

            # 5. Synthesize game-specialized LLM tools with schemas and handlers
            tools_registry = synthesize_tools(classification, grammar, heuristics, rules)
            tool_schemas = tools_registry.get_schemas()

            # 6. Synthesize per-variant simulator (Issue #26)
            sim_path = None
            sim_calib = {}
            if classification.family in ("grid_board", "dice_push", "deduction"):
                sim_filename = f"simulator_{idx}.py"
                sim_path, sim_calib = save_synthesized_simulator(
                    dest_dir, classification, grammar, f"{game_id}_{idx}", filename=sim_filename
                )
                if idx == 0:
                    import shutil
                    shutil.copyfile(sim_path, os.path.join(dest_dir, "simulator.py"))

            # 7. Word games vocabulary and Connect Four pre-warming (Issue #39)
            if grammar.kind == "word" or classification.family in ("word", "wordle", "hangman", "deduction"):
                w_len = grammar.word_length or 5
                from optimization.words import get_words
                words_list = get_words(w_len)
                if words_list:
                    atomic_save_json(os.path.join(dest_dir, f"words_{w_len}.json"), words_list)
                    if idx == 0:
                        atomic_save_json(os.path.join(dest_dir, "words.json"), words_list)

            # 8. Dynamic programming exact policy for dice games (Pig DP)
            pig_thresh = None
            if classification.family in ("dice_push", "chance") or "pig" in rules.lower() or "bank" in rules.lower():
                from optimization.pig_dp import compute_pig_thresholds
                target = 50
                m_target = re.search(r"(?:first to|target:?)\s*(\d+)", rules, re.I)
                if m_target:
                    target = int(m_target.group(1))
                num_dice = 2 if ("two dice" in rules.lower() or "2 dice" in rules.lower()) else 1
                snake_eyes = "snake eyes" in rules.lower()
                try:
                    pig_thresh = compute_pig_thresholds(target_score=target, num_dice=num_dice, snake_eyes_reset=snake_eyes)
                    atomic_save_json(os.path.join(dest_dir, f"pig_dp_{idx}.json"), pig_thresh)
                    if idx == 0 or not os.path.exists(os.path.join(dest_dir, "pig_dp.json")):
                        atomic_save_json(os.path.join(dest_dir, "pig_dp.json"), pig_thresh)
                except Exception as e:
                    print(f"[prep/engine] pig_dp precompute failed: {e}", file=sys.stderr)

            # 9. Connect Four opening book precomputation
            c4_book = None
            if classification.family in ("grid_board", "tic_tac_toe") and (
                grammar.parameters.get("gravity") or "connect" in rules.lower() or "drop" in rules.lower()
            ):
                from optimization.connect_four_book import precompute_connect_four_book
                try:
                    c4_book = precompute_connect_four_book(
                        rows=grammar.grid_rows or 6,
                        cols=grammar.grid_cols or 7,
                        connect_k=grammar.parameters.get("connect_k", 4),
                        time_limit_sec=min(2.5, budget_seconds / 4.0),
                    )
                    atomic_save_json(os.path.join(dest_dir, f"opening_book_{idx}.json"), c4_book)
                    if idx == 0 or not os.path.exists(os.path.join(dest_dir, "opening_book.json")):
                        atomic_save_json(os.path.join(dest_dir, "opening_book.json"), c4_book)
                except Exception as e:
                    print(f"[prep/engine] c4_book precompute failed: {e}", file=sys.stderr)

            # 10. Colonel Blotto game-theoretic allocation portfolio
            blotto_book = None
            if "blotto" in rules.lower() or "battlefield" in rules.lower():
                from optimization.blotto_solver import generate_blotto_allocations
                try:
                    soldiers = 100
                    m_sold = re.search(r"(\d+)\s+soldiers", rules, re.I)
                    if m_sold:
                        soldiers = int(m_sold.group(1))
                    fields = 5
                    m_f = re.search(r"(\d+)\s+(?:battlefields|fields)", rules, re.I)
                    if m_f:
                        fields = int(m_f.group(1))
                    values = None
                    m_val = re.search(r"values:\s*([^\.\n]+)", rules, re.I)
                    if m_val:
                        val_pairs = re.findall(r"F\d+=(\d+)", m_val.group(1))
                        if val_pairs and len(val_pairs) == fields:
                            values = [int(x) for x in val_pairs]
                    blotto_book = generate_blotto_allocations(soldiers=soldiers, fields=fields, values=values, count=30)
                    atomic_save_json(os.path.join(dest_dir, f"blotto_book_{idx}.json"), blotto_book)
                    if idx == 0 or not os.path.exists(os.path.join(dest_dir, "blotto_book.json")):
                        atomic_save_json(os.path.join(dest_dir, "blotto_book.json"), blotto_book)
                except Exception as e:
                    print(f"[prep/engine] blotto_book precompute failed: {e}", file=sys.stderr)

            # 11. Strategic Playbook synthesis (Issue #47)
            playbook_path = os.path.join(dest_dir, f"playbook_{idx}.json")
            playbook_default = os.path.join(dest_dir, "playbook.json")
            playbook_data = None
            if os.path.exists(playbook_default) and idx == 0:
                from optimization.serializer import load_json
                playbook_data = load_json(playbook_default)
            elif os.path.exists(playbook_path):
                from optimization.serializer import load_json
                playbook_data = load_json(playbook_path)

            if not playbook_data:
                from .playbook import synthesize_playbook
                call_llm = llm if (budget_seconds >= 3.0 and llm and llm.available() and not llm.over_budget()) else None
                playbook_data = synthesize_playbook(rules, call_llm, timeout=min(12.0, budget_seconds / 2.0))
                atomic_save_json(playbook_path, playbook_data)
                if idx == 0 or not os.path.exists(playbook_default):
                    atomic_save_json(playbook_default, playbook_data)

            variants_data.append({
                "label": label,
                "classification": classification.to_dict(),
                "grammar": grammar.to_dict(),
                "obs_layout": obs_layout,
                "obs_schema": obs_schema.to_dict(),
                "heuristics": heuristics,
                "tools": tool_schemas,
                "tools_prompt": tools_registry.format_for_prompt(),
                "simulator_path": sim_path,
                "simulator_calibration": sim_calib,
                "sample_validation_passed": sample_validation_passed,
                "pig_dp": pig_thresh,
                "opening_book": c4_book,
                "blotto_book": blotto_book,
                "playbook_structured": playbook_data,
            })

        if variants_data:
            if variants[0].get("sample_turn"):
                first_schema = infer_observation_schema(variants[0]["sample_turn"].get("observation", ""))
                atomic_save_json(os.path.join(dest_dir, "observation_schema.json"), first_schema.to_dict())

            first_tools = variants_data[0].get("tools", [])
            atomic_save_json(os.path.join(dest_dir, "tools.json"), first_tools)

        # Save prep artifacts atomically to /memory/<game_id>/
        manifest = {
            "game_id": game_id,
            "game_name": game_name,
            "fingerprint": fp,
            "family": overall_classification.family if overall_classification else "generic",
            "simulator_calibration": variants_data[0].get("simulator_calibration", {}) if variants_data else {},
            "simulator_path": variants_data[0].get("simulator_path") if variants_data else None,
            "tools": variants_data[0].get("tools", []) if variants_data else [],
            "playbook_structured": variants_data[0].get("playbook_structured") if variants_data else None,
            "variants": variants_data,
            "prepped_at": time.time(),
            "elapsed_seconds": round(time.time() - start_time, 3),
        }

        atomic_save_json(os.path.join(dest_dir, "manifest.json"), manifest)
        if overall_classification:
            atomic_save_json(os.path.join(dest_dir, "classification.json"), overall_classification.to_dict())

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
