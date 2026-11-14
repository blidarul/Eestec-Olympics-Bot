"""Strategic LLM Playbook Synthesizer for 10-minute prep phase.
Synthesizes game invariants, failure traps, opening principles, and endgame goals
into structured JSON, saving to /memory/<game_id>/playbook.json.
Owned by agent `bld`.
"""
from __future__ import annotations

import re
import sys
from typing import Any

SYSTEM_PROMPT = (
    "You are an expert game theory strategist preparing an AI bot for a match. "
    "Analyze the provided game rules and produce a concise, actionable JSON playbook. "
    "Respond with valid JSON only in this exact format:\n"
    "{\n"
    '  "invariants": ["rule fact 1", "rule fact 2"],\n'
    '  "traps": ["blunder to avoid 1", "common pitfall 2"],\n'
    '  "opening_guidelines": ["opening principle 1", "principle 2"],\n'
    '  "endgame_goals": ["key winning condition or point target"]\n'
    "}\n"
    "Keep each bullet point concise (under 100 characters). Provide 2-4 bullets per list."
)


def _generate_rule_based_baseline(rules: str) -> dict[str, list[str]]:
    """Generate safe, rule-based strategic guidelines when LLM is not available."""
    invariants: list[str] = []
    traps: list[str] = [
        "Avoid sending illegal actions or violating the format grammar",
        "Never exceed the per-move deadline clock",
    ]
    opening_guidelines: list[str] = []
    endgame_goals: list[str] = []

    # Detect win condition / target
    m_tgt = re.search(r"(?:target|first to|score of)\s*[:\s]*(\d+)", rules, re.I)
    if m_tgt:
        endgame_goals.append(f"Reach or exceed the target score of {m_tgt.group(1)} points")
    else:
        endgame_goals.append("Maximize net points and avoid conceding winning lines to opponent")

    # Detect rounds or turn limits
    m_rnds = re.search(r"(\d+)\s+rounds", rules, re.I)
    if m_rnds:
        invariants.append(f"Fixed game length of {m_rnds.group(1)} rounds")

    # Detect simultaneous or sequential
    if "simultaneous" in rules.lower():
        invariants.append("Both players act simultaneously in secret each round")
        opening_guidelines.append("Randomize allocations to avoid predictability against opponent")
    else:
        invariants.append("Alternating turn-based moves")
        opening_guidelines.append("Establish strong central presence or secure high-utility positions")

    # Detect forbidden speech rules
    if any(kw in rules.lower() for kw in ("never say", "forbidden", "forbidden word", "taboo")):
        traps.append("Game has speech restriction: strictly adhere to forbidden terms filter")

    if not opening_guidelines:
        opening_guidelines.append("Prioritize safe, legal opening moves that preserve future options")

    return {
        "invariants": invariants or ["Two-player competitive game with deterministic rules"],
        "traps": traps,
        "opening_guidelines": opening_guidelines,
        "endgame_goals": endgame_goals,
    }


def synthesize_playbook(
    rules: str,
    llm_client: Any = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Synthesize strategic playbook JSON via Haiku gateway or rule-based baseline."""
    baseline = _generate_rule_based_baseline(rules)

    if llm_client is None:
        return baseline

    # Check if LLM is callable
    is_avail = getattr(llm_client, "available", None)
    if callable(is_avail) and not is_avail():
        return baseline

    ask_fn = getattr(llm_client, "ask_json", None)
    if not callable(ask_fn):
        return baseline

    user_prompt = f"Game Rules:\n{rules[:3500]}\n\nSynthesize strategic playbook JSON:"
    try:
        obj = ask_fn(SYSTEM_PROMPT, user_prompt, prep=True, timeout=timeout)
        if isinstance(obj, dict):
            # Validate required schema
            keys = ("invariants", "traps", "opening_guidelines", "endgame_goals")
            if any(k in obj and isinstance(obj[k], list) and obj[k] for k in keys):
                cleaned: dict[str, list[str]] = {}
                for k in keys:
                    items = obj.get(k)
                    if isinstance(items, list):
                        cleaned[k] = [str(x)[:120].strip() for x in items if str(x).strip()][:5]
                    else:
                        cleaned[k] = baseline.get(k, [])
                print(f"[playbook] synthesized LLM strategic playbook with {sum(len(v) for v in cleaned.values())} bullets", file=sys.stderr)
                return cleaned
    except Exception as e:
        print(f"[playbook] LLM playbook call failed ({type(e).__name__}: {e}), using baseline", file=sys.stderr)

    return baseline


def format_playbook_for_prompt(playbook: dict[str, Any], max_len: int = 400) -> str:
    """Format structured playbook into a concise section for the turn prompt."""
    if not isinstance(playbook, dict):
        return ""

    lines = []
    invs = playbook.get("invariants")
    if invs and isinstance(invs, list):
        lines.append("- Invariants: " + "; ".join(str(x) for x in invs[:2]))

    traps = playbook.get("traps")
    if traps and isinstance(traps, list):
        lines.append("- Traps to Avoid: " + "; ".join(str(x) for x in traps[:2]))

    guidelines = playbook.get("opening_guidelines")
    if guidelines and isinstance(guidelines, list):
        lines.append("- Guidelines: " + "; ".join(str(x) for x in guidelines[:2]))

    goals = playbook.get("endgame_goals")
    if goals and isinstance(goals, list):
        lines.append("- Goals: " + "; ".join(str(x) for x in goals[:1]))

    res = "\n".join(lines).strip()
    return res[:max_len]
