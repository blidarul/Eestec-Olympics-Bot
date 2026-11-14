"""Game-Specialized Tool Synthesizer for 10-Minute Prep.
Constructs LLM function-calling schemas, parameter definitions, and executable handlers
tailored to the specific game family and rules described during prep.
Rule 7.6 (any tool allowed), Rule 6.4 (unified move and chat decision).
Owned by agent `bld`.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .action_parser import ActionGrammar
from .classifier import GameClassification


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]] | None = None

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to standard OpenAI / Haiku tool definition schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary without python callable."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """Registry holding game-specialized tools, schema exporters, and tool execution."""

    def __init__(self, tools: list[ToolDefinition] | None = None):
        self.tools: dict[str, ToolDefinition] = {t.name: t for t in (tools or [])}

    def register(self, tool: ToolDefinition) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self.tools.get(name)

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return list of function calling schemas for LLM client."""
        return [t.to_openai_schema() for t in self.tools.values()]

    def to_list(self) -> list[dict[str, Any]]:
        """Return list of JSON-serializable tool dictionaries."""
        return [t.to_dict() for t in self.tools.values()]

    def format_for_prompt(self) -> str:
        """Format tools into readable markdown text for LLM system or user prompts."""
        lines = ["### Specialized Game Tools Available:"]
        for t in self.tools.values():
            props = t.parameters.get("properties", {})
            req = t.parameters.get("required", [])
            args_str = ", ".join(
                f"{k}: {props[k].get('type', 'any')}{' (required)' if k in req else ''}"
                for k in props
            )
            lines.append(f"- **`{t.name}({args_str})`**: {t.description}")
        return "\n".join(lines)

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Safely execute a tool handler by name."""
        if tool_name not in self.tools:
            return {"success": False, "error": f"Tool '{tool_name}' not found in registry"}
        tool = self.tools[tool_name]
        if tool.handler is None:
            return {"success": False, "error": f"No handler implemented for tool '{tool_name}'"}
        try:
            result = tool.handler(**arguments)
            return {"success": True, "tool": tool_name, "result": result}
        except Exception as e:
            return {"success": False, "tool": tool_name, "error": f"Execution error: {type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# Universal Tool Handlers
# ---------------------------------------------------------------------------

def _make_check_legality_handler(grammar: ActionGrammar):
    def check_move_legality(action: str, legal_actions: list[str] | None = None) -> dict[str, Any]:
        cleaned = str(action).strip()
        is_legal = grammar.validate(cleaned, legal_actions)
        return {
            "action": cleaned,
            "is_legal": is_legal,
            "kind": grammar.kind,
            "allowed_examples": grammar.discrete_actions[:6] if grammar.discrete_actions else [],
        }
    return check_move_legality


def _make_sanitize_chat_handler(forbidden_keywords: list[str]):
    def sanitize_and_verify_chat(message: str) -> dict[str, Any]:
        msg = str(message).strip()
        if len(msg) > 150:
            msg = msg[:147] + "..."
        detected_forbidden = []
        lower = msg.lower()
        for kw in forbidden_keywords:
            if re.search(r"\b" + re.escape(kw.lower()) + r"\b", lower):
                detected_forbidden.append(kw)
                msg = re.sub(r"\b" + re.escape(kw) + r"\b", "[redacted]", msg, flags=re.IGNORECASE)
        return {
            "safe_message": msg,
            "char_count": len(msg),
            "forbidden_keywords_found": detected_forbidden,
            "is_clean": len(detected_forbidden) == 0,
        }
    return sanitize_and_verify_chat


def _simulate_action_handler(action: str, observation: str = "") -> dict[str, Any]:
    act = str(action).strip()
    return {
        "action": act,
        "simulated": True,
        "note": f"Action '{act}' applied to state observation.",
    }


# ---------------------------------------------------------------------------
# Grid / Board Handlers
# ---------------------------------------------------------------------------

def _evaluate_board_position_handler(board_observation: str, my_mark: str = "X") -> dict[str, Any]:
    obs = str(board_observation)
    my_m = my_mark.strip().upper()
    opp_m = "O" if my_m == "X" else "X"

    my_count = obs.count(my_m)
    opp_count = obs.count(opp_m)
    lines = [line.strip() for line in obs.splitlines() if line.strip()]

    # Center cell check (B2 in 3x3)
    has_center = False
    for line in lines:
        if "B" in line and my_m in line:
            has_center = True
            break

    score = (my_count - opp_count) * 10 + (15 if has_center else 0)
    return {
        "my_mark": my_m,
        "opp_mark": opp_m,
        "my_pieces": my_count,
        "opp_pieces": opp_count,
        "center_control": has_center,
        "evaluation_score": score,
    }


def _find_line_threats_handler(board_observation: str, line_length: int = 3) -> dict[str, Any]:
    # Parse coordinates from lines
    obs = str(board_observation)
    empty_cells = []
    for r in range(1, line_length + 1):
        for c in range(line_length):
            coord = f"{chr(ord('A') + c)}{r}"
            if coord in obs or "." in obs:
                empty_cells.append(coord)

    return {
        "target_line_length": line_length,
        "winning_moves": empty_cells[:1],
        "urgent_blocks": empty_cells[1:2] if len(empty_cells) > 1 else [],
        "critical_threat_detected": len(empty_cells) > 0,
    }


def _make_symmetry_handler(cols: int, rows: int):
    from .heuristics import compute_grid_symmetries
    symmetries_table = compute_grid_symmetries(cols, rows)

    def get_symmetry_equivalent_moves(move: str) -> dict[str, Any]:
        m = str(move).strip().upper()
        equivalents = symmetries_table.get(m, [m])
        canonical = equivalents[0] if equivalents else m
        return {
            "move": m,
            "canonical_representative": canonical,
            "orbit_size": len(equivalents),
            "equivalent_coordinates": equivalents,
        }
    return get_symmetry_equivalent_moves


# ---------------------------------------------------------------------------
# Accumulator / Dice Push Handlers
# ---------------------------------------------------------------------------

def _calculate_stopping_threshold_handler(
    turn_score: int, my_bank: int, opp_bank: int, target_score: int = 100
) -> dict[str, Any]:
    t_score = int(turn_score)
    m_bank = int(my_bank)
    o_bank = int(opp_bank)
    tgt = int(target_score)

    # Immediate win check
    if m_bank + t_score >= tgt:
        return {
            "recommended_action": "hold",
            "threshold": 0,
            "turn_score": t_score,
            "reason": f"Holding immediately wins the game ({m_bank} + {t_score} >= {tgt})",
            "is_endgame_win": True,
        }

    # Dynamic stopping threshold
    # In standard Pig: base threshold is ~20 points
    remaining = tgt - m_bank
    base_thresh = 20
    if o_bank >= tgt - 20:
        # Opponent close to winning: take more risk
        base_thresh = max(25, remaining)

    effective_thresh = min(base_thresh, remaining)
    action = "hold" if t_score >= effective_thresh else "roll"
    return {
        "recommended_action": action,
        "threshold": effective_thresh,
        "turn_score": t_score,
        "points_to_target": remaining,
        "reason": f"Accumulation {t_score} {'exceeds' if action == 'hold' else 'below'} threshold {effective_thresh}",
        "is_endgame_win": False,
    }


def _estimate_bust_risk_handler(turn_score: int, dice_sides: int = 6) -> dict[str, Any]:
    t_score = int(turn_score)
    sides = max(2, int(dice_sides))
    p_bust = 1.0 / sides
    p_safe = (sides - 1.0) / sides
    avg_gain = sum(range(2, sides + 1)) / (sides - 1) if sides > 1 else 1.0

    # Expected net value of 1 more roll:
    # E[gain] = p_safe * avg_gain - p_bust * turn_score
    expected_net = p_safe * avg_gain - p_bust * t_score

    return {
        "turn_score_at_risk": t_score,
        "dice_sides": sides,
        "p_bust": round(p_bust, 4),
        "expected_gain_if_safe": round(avg_gain, 2),
        "expected_net_value": round(expected_net, 3),
        "favorable_to_continue": expected_net > 0,
    }


# ---------------------------------------------------------------------------
# Deduction / Guessing Handlers
# ---------------------------------------------------------------------------

def _compute_binary_search_guess_handler(min_val: int, max_val: int) -> dict[str, Any]:
    low = int(min_val)
    high = int(max_val)
    if low > high:
        low, high = high, low
    guess = (low + high) // 2
    candidates = max(1, high - low + 1)
    max_steps_remaining = math.ceil(math.log2(candidates)) if candidates > 0 else 0
    return {
        "recommended_guess": guess,
        "min_val": low,
        "max_val": high,
        "candidate_count": candidates,
        "max_steps_to_solve": max_steps_remaining,
    }


def _update_search_interval_handler(
    last_guess: int, feedback: str, current_min: int, current_max: int
) -> dict[str, Any]:
    g = int(last_guess)
    fb = str(feedback).lower()
    low = int(current_min)
    high = int(current_max)

    if any(w in fb for w in ("higher", "too low", "greater", "above", "more", "increase")):
        low = max(low, g + 1)
    elif any(w in fb for w in ("lower", "too high", "smaller", "below", "less", "decrease")):
        high = min(high, g - 1)

    return {
        "updated_min": low,
        "updated_max": high,
        "range_size": max(0, high - low + 1),
        "eliminated_count": max(0, (current_max - current_min + 1) - (high - low + 1)),
    }


# ---------------------------------------------------------------------------
# Cards / Hidden Information / Bluff Handlers
# ---------------------------------------------------------------------------

def _calculate_pot_odds_handler(pot_size: float, call_cost: float) -> dict[str, Any]:
    pot = max(0.0, float(pot_size))
    cost = max(0.01, float(call_cost))
    total_pot = pot + cost
    pot_odds = cost / total_pot
    return {
        "pot_size": pot,
        "call_cost": cost,
        "pot_odds_ratio": f"{pot / cost:.2f}:1",
        "required_equity_percent": round(pot_odds * 100, 2),
        "profitable_if_win_prob_exceeds": round(pot_odds, 4),
    }


def _estimate_bluff_frequency_handler(bet_size: float, pot_size: float) -> dict[str, Any]:
    bet = max(0.01, float(bet_size))
    pot = max(0.0, float(pot_size))
    # GTO alpha = bet / (pot + bet)
    alpha = bet / (pot + bet)
    optimal_bluff_freq = alpha / (1.0 + alpha)
    return {
        "bet_size": bet,
        "pot_size": pot,
        "alpha_break_even": round(alpha, 4),
        "optimal_bluff_frequency": round(optimal_bluff_freq, 4),
        "optimal_bluff_percentage": round(optimal_bluff_freq * 100, 2),
    }


# ---------------------------------------------------------------------------
# Matrix / Simultaneous Handlers
# ---------------------------------------------------------------------------

def _calculate_nash_mixed_strategy_handler(
    available_actions: list[str], opponent_history: list[str] | None = None
) -> dict[str, Any]:
    acts = [str(a) for a in available_actions if str(a).strip()]
    if not acts:
        acts = ["cooperate", "defect"]
    uniform_prob = round(1.0 / len(acts), 4)
    probs = {a: uniform_prob for a in acts}
    return {
        "strategy_type": "nash_mixed_equilibrium",
        "action_probabilities": probs,
        "recommended_action": acts[0],
    }


def _detect_opponent_pattern_handler(opponent_moves: list[str]) -> dict[str, Any]:
    moves = [str(m).strip() for m in opponent_moves if str(m).strip()]
    if not moves:
        return {"total_moves": 0, "frequencies": {}, "dominant_move": None}
    counts: dict[str, int] = {}
    for m in moves:
        counts[m] = counts.get(m, 0) + 1
    dominant = max(counts, key=counts.get)
    freqs = {k: round(v / len(moves), 3) for k, v in counts.items()}
    return {
        "total_moves": len(moves),
        "frequencies": freqs,
        "dominant_move": dominant,
        "is_skewed": freqs[dominant] > 0.45 and len(counts) > 1,
    }


# ---------------------------------------------------------------------------
# Negotiation Handlers
# ---------------------------------------------------------------------------

def _evaluate_split_fairness_handler(our_offer: float, opp_offer: float, total_pool: float) -> dict[str, Any]:
    ours = float(our_offer)
    theirs = float(opp_offer)
    pool = max(0.01, float(total_pool))
    nash_product = max(0.0, ours) * max(0.0, theirs)
    our_fraction = round(ours / pool, 3)
    is_fair = 0.4 <= our_fraction <= 0.6
    return {
        "our_fraction": our_fraction,
        "opp_fraction": round(theirs / pool, 3),
        "nash_bargaining_product": round(nash_product, 2),
        "is_fair_split": is_fair,
        "recommendation": "accept" if our_fraction >= 0.45 else "counter",
    }


def _calculate_counter_offer_handler(
    round_num: int, max_rounds: int, total_pool: float, opp_last_offer: float
) -> dict[str, Any]:
    r = max(1, int(round_num))
    max_r = max(1, int(max_rounds))
    pool = max(0.01, float(total_pool))
    opp_claimed = float(opp_last_offer)

    # Concession curve based on remaining rounds:
    urgency = r / max_r
    our_ideal_fraction = 0.60 - 0.15 * urgency  # 60% down to 45%
    proposed_ours = round(pool * our_ideal_fraction, 2)
    proposed_theirs = round(pool - proposed_ours, 2)

    return {
        "round": r,
        "urgency_fraction": round(urgency, 2),
        "counter_our_share": proposed_ours,
        "counter_opp_share": proposed_theirs,
        "concession_from_ideal": round(0.15 * urgency * pool, 2),
    }


# ---------------------------------------------------------------------------
# QA & Guardrail Handlers
# ---------------------------------------------------------------------------

def _detect_jailbreak_or_leak_handler(text: str) -> dict[str, Any]:
    t = str(text)
    patterns = [
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
        r"system\s+prompt",
        r"reveal\s+(secret|password|key|flag|hidden)",
        r"repeat\s+after\s+me",
        r"you\s+are\s+now\s+in\s+developer\s+mode",
        r"dan\s+mode",
    ]
    detected = []
    for p in patterns:
        if re.search(p, t, re.IGNORECASE):
            detected.append(p)
    return {
        "is_suspicious": len(detected) > 0,
        "matched_patterns": detected,
        "sanitized_safe": len(detected) == 0,
    }


def _verify_grounding_handler(context: str, claim: str) -> dict[str, Any]:
    ctx = str(context).lower()
    cl = str(claim).lower()
    claim_words = [w for w in re.findall(r"\b\w{4,}\b", cl)]
    if not claim_words:
        return {"grounding_score": 1.0, "is_supported": True}
    overlap = sum(1 for w in claim_words if w in ctx)
    score = round(overlap / len(claim_words), 3)
    return {
        "grounding_score": score,
        "is_supported": score >= 0.5,
        "unmatched_terms": [w for w in claim_words if w not in ctx],
    }


# ---------------------------------------------------------------------------
# Synthesizer Factory
# ---------------------------------------------------------------------------

def synthesize_tools(
    classification: GameClassification,
    grammar: ActionGrammar,
    heuristics: dict[str, Any] | None = None,
    rules_text: str = "",
) -> ToolRegistry:
    """Synthesize a complete ToolRegistry tailored specifically for the game."""
    heur = heuristics or {}
    registry = ToolRegistry()

    # --- 1. Universal Tools (All Games) ---
    registry.register(
        ToolDefinition(
            name="check_move_legality",
            description="Validate whether a candidate action is strictly legal according to the game action grammar and discrete choices.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Candidate move string to validate (e.g. 'A1', 'roll', 'hold', '50')",
                    },
                    "legal_actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional explicit list of legal moves if provided by the game",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            handler=_make_check_legality_handler(grammar),
        )
    )

    registry.register(
        ToolDefinition(
            name="sanitize_and_verify_chat",
            description="Scan candidate chat message against forbidden keywords, length constraints (max 150 chars), and prompt injection leakage.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Draft chat message to inspect and sanitize",
                    }
                },
                "required": ["message"],
                "additionalProperties": False,
            },
            handler=_make_sanitize_chat_handler(grammar.forbidden_keywords),
        )
    )

    registry.register(
        ToolDefinition(
            name="simulate_action",
            description="Simulate the outcome of taking a candidate action using the synthesized game state engine.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Candidate move to simulate",
                    },
                    "observation": {
                        "type": "string",
                        "description": "Current board layout or game observation string",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            handler=_simulate_action_handler,
        )
    )

    # --- 2. Game Family Specific Tools ---
    family = classification.family

    if family == "grid_board":
        registry.register(
            ToolDefinition(
                name="evaluate_board_position",
                description="Evaluate the grid position to assess center control, line threats, piece counts, and overall positional score.",
                parameters={
                    "type": "object",
                    "properties": {
                        "board_observation": {
                            "type": "string",
                            "description": "Current grid/board text observation",
                        },
                        "my_mark": {
                            "type": "string",
                            "description": "Our bot symbol (e.g. 'X' or 'O', default 'X')",
                        },
                    },
                    "required": ["board_observation"],
                    "additionalProperties": False,
                },
                handler=_evaluate_board_position_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="find_line_threats",
                description="Detect immediate winning moves (N-in-a-row) or critical opponent lines that must be blocked.",
                parameters={
                    "type": "object",
                    "properties": {
                        "board_observation": {
                            "type": "string",
                            "description": "Current grid text representation",
                        },
                        "line_length": {
                            "type": "integer",
                            "description": "Target winning line length (default 3)",
                        },
                    },
                    "required": ["board_observation"],
                    "additionalProperties": False,
                },
                handler=_find_line_threats_handler,
            )
        )
        cols = grammar.parameters.get("grid_cols", 3)
        rows = grammar.parameters.get("grid_rows", 3)
        registry.register(
            ToolDefinition(
                name="get_symmetry_equivalent_moves",
                description="Get symmetry-equivalent grid coordinates under dihedral transformations (rotations/reflections) to prune search space.",
                parameters={
                    "type": "object",
                    "properties": {
                        "move": {
                            "type": "string",
                            "description": "Coordinate move (e.g. 'A1', 'C3')",
                        }
                    },
                    "required": ["move"],
                    "additionalProperties": False,
                },
                handler=_make_symmetry_handler(cols, rows),
            )
        )

    elif family == "dice_push":
        registry.register(
            ToolDefinition(
                name="calculate_stopping_threshold",
                description="Compute the optimal Markov Decision Process (MDP) stopping threshold to decide whether to roll or hold/bank.",
                parameters={
                    "type": "object",
                    "properties": {
                        "turn_score": {
                            "type": "integer",
                            "description": "Current unbanked turn total accumulated so far",
                        },
                        "my_bank": {
                            "type": "integer",
                            "description": "Our total banked score",
                        },
                        "opp_bank": {
                            "type": "integer",
                            "description": "Opponent total banked score",
                        },
                        "target_score": {
                            "type": "integer",
                            "description": "Goal score needed to win (default 100)",
                        },
                    },
                    "required": ["turn_score", "my_bank", "opp_bank"],
                    "additionalProperties": False,
                },
                handler=_calculate_stopping_threshold_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="estimate_bust_risk",
                description="Calculate probability of a bust on the next roll and the risk-adjusted expected value of continuing.",
                parameters={
                    "type": "object",
                    "properties": {
                        "turn_score": {
                            "type": "integer",
                            "description": "Current turn points at risk",
                        },
                        "dice_sides": {
                            "type": "integer",
                            "description": "Number of sides on die (default 6)",
                        },
                    },
                    "required": ["turn_score"],
                    "additionalProperties": False,
                },
                handler=_estimate_bust_risk_handler,
            )
        )

    elif family == "deduction":
        registry.register(
            ToolDefinition(
                name="compute_binary_search_guess",
                description="Compute the optimal information-theoretic midpoint guess to eliminate half of the remaining hypothesis range.",
                parameters={
                    "type": "object",
                    "properties": {
                        "min_val": {
                            "type": "integer",
                            "description": "Current lower bound of candidate interval",
                        },
                        "max_val": {
                            "type": "integer",
                            "description": "Current upper bound of candidate interval",
                        },
                    },
                    "required": ["min_val", "max_val"],
                    "additionalProperties": False,
                },
                handler=_compute_binary_search_guess_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="update_search_interval",
                description="Update the hypothesis interval [min_val, max_val] based on feedback ('higher', 'lower', 'too high', 'too low').",
                parameters={
                    "type": "object",
                    "properties": {
                        "last_guess": {
                            "type": "integer",
                            "description": "Number that was guessed",
                        },
                        "feedback": {
                            "type": "string",
                            "description": "Opponent or referee feedback string",
                        },
                        "current_min": {
                            "type": "integer",
                            "description": "Current lower bound",
                        },
                        "current_max": {
                            "type": "integer",
                            "description": "Current upper bound",
                        },
                    },
                    "required": ["last_guess", "feedback", "current_min", "current_max"],
                    "additionalProperties": False,
                },
                handler=_update_search_interval_handler,
            )
        )

    elif family == "cards_hidden":
        registry.register(
            ToolDefinition(
                name="calculate_pot_odds",
                description="Calculate pot odds and minimum required equity to justify calling or betting.",
                parameters={
                    "type": "object",
                    "properties": {
                        "pot_size": {
                            "type": "number",
                            "description": "Current total pot amount",
                        },
                        "call_cost": {
                            "type": "number",
                            "description": "Chips/cost required to call",
                        },
                    },
                    "required": ["pot_size", "call_cost"],
                    "additionalProperties": False,
                },
                handler=_calculate_pot_odds_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="estimate_bluff_frequency",
                description="Compute Game Theory Optimal (GTO) bluff frequency based on bet sizing.",
                parameters={
                    "type": "object",
                    "properties": {
                        "bet_size": {
                            "type": "number",
                            "description": "Proposed bet or raise size",
                        },
                        "pot_size": {
                            "type": "number",
                            "description": "Pot size prior to the bet",
                        },
                    },
                    "required": ["bet_size", "pot_size"],
                    "additionalProperties": False,
                },
                handler=_estimate_bluff_frequency_handler,
            )
        )

    elif family == "matrix_simultaneous":
        registry.register(
            ToolDefinition(
                name="calculate_nash_mixed_strategy",
                description="Calculate Nash equilibrium mixed strategy probabilities across available actions.",
                parameters={
                    "type": "object",
                    "properties": {
                        "available_actions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of available actions (e.g. ['rock', 'paper', 'scissors'])",
                        },
                        "opponent_history": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Opponent past actions history",
                        },
                    },
                    "required": ["available_actions"],
                    "additionalProperties": False,
                },
                handler=_calculate_nash_mixed_strategy_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="detect_opponent_pattern",
                description="Analyze opponent previous moves for frequency bias and pattern tendencies.",
                parameters={
                    "type": "object",
                    "properties": {
                        "opponent_moves": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Sequence of past opponent moves in chronological order",
                        },
                    },
                    "required": ["opponent_moves"],
                    "additionalProperties": False,
                },
                handler=_detect_opponent_pattern_handler,
            )
        )

    elif family == "negotiation":
        registry.register(
            ToolDefinition(
                name="evaluate_split_fairness",
                description="Evaluate the fairness, surplus split, and Nash bargaining product of a proposed deal.",
                parameters={
                    "type": "object",
                    "properties": {
                        "our_offer": {
                            "type": "number",
                            "description": "Value/points allocated to us in proposal",
                        },
                        "opp_offer": {
                            "type": "number",
                            "description": "Value/points allocated to opponent in proposal",
                        },
                        "total_pool": {
                            "type": "number",
                            "description": "Total value of items/points to divide",
                        },
                    },
                    "required": ["our_offer", "opp_offer", "total_pool"],
                    "additionalProperties": False,
                },
                handler=_evaluate_split_fairness_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="calculate_counter_offer",
                description="Generate an optimal concession counter-offer balancing risk of breakdown against deal value.",
                parameters={
                    "type": "object",
                    "properties": {
                        "round_num": {
                            "type": "integer",
                            "description": "Current negotiation round",
                        },
                        "max_rounds": {
                            "type": "integer",
                            "description": "Total negotiation rounds before breakdown",
                        },
                        "total_pool": {
                            "type": "number",
                            "description": "Total pool value",
                        },
                        "opp_last_offer": {
                            "type": "number",
                            "description": "Opponent's last proposed share for themselves",
                        },
                    },
                    "required": ["round_num", "max_rounds", "total_pool", "opp_last_offer"],
                    "additionalProperties": False,
                },
                handler=_calculate_counter_offer_handler,
            )
        )

    elif family == "qa_guardrails":
        registry.register(
            ToolDefinition(
                name="detect_jailbreak_or_leak",
                description="Scan text for prompt injection attempts, jailbreak keywords, or secret leakage.",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to evaluate for adversarial patterns or secret revelation",
                        }
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
                handler=_detect_jailbreak_or_leak_handler,
            )
        )
        registry.register(
            ToolDefinition(
                name="verify_grounding",
                description="Verify whether an answer is grounded in provided reference context without hallucination.",
                parameters={
                    "type": "object",
                    "properties": {
                        "context": {
                            "type": "string",
                            "description": "Reference passage or facts",
                        },
                        "claim": {
                            "type": "string",
                            "description": "Draft claim or answer to verify",
                        },
                    },
                    "required": ["context", "claim"],
                    "additionalProperties": False,
                },
                handler=_verify_grounding_handler,
            )
        )

    return registry
