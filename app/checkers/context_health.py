"""
Context Health - Session health scoring and cost estimation.

Health scoring uses a penalty-based formula:
  health = max(0, 100 - (turn_penalty + token_penalty + error_penalty))

Brain Rot detection: if 3 out of last 5 health scores are below 50.

Cost estimation uses hardcoded per-model token pricing and tracks waste from
detected loops.

Zero external dependencies - uses only Python stdlib.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContextHealthResult:
    score: float                    # 0 - 100
    is_degraded: bool              # score < threshold
    brain_rot_detected: bool       # 3/5 recent scores < 50
    fork_recommendation: bool      # True if fork would help
    details: dict                  # breakdown of penalties


@dataclass
class CostMetrics:
    estimated_cost_usd: float      # tokens * price per token
    tokens_wasted_on_loops: int
    context_utilization_pct: float  # useful tokens / total
    cost_rating: str               # "efficient", "moderate", "wasteful"


# ---------------------------------------------------------------------------
# Cost model pricing (per 1M tokens, averaged input+output)
# ---------------------------------------------------------------------------

_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":           {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":      {"input": 0.15,  "output": 0.60},
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
}
_DEFAULT_PRICING = {"input": 1.00, "output": 5.00}


# ---------------------------------------------------------------------------
# Health scoring
# ---------------------------------------------------------------------------

def calculate_health(
    turn_count: int,
    cumulative_tokens: int,
    error_count: int,
    recent_scores: List[float],
    threshold: float = 50.0,
) -> ContextHealthResult:
    """Computes session health score with Brain Rot detection."""

    # Penalty formula
    turn_penalty = max(0, (turn_count - 10) * 2)
    token_penalty = cumulative_tokens / 1000
    error_penalty = error_count * 15

    total_penalty = turn_penalty + token_penalty + error_penalty
    score = max(0.0, 100.0 - total_penalty)

    is_degraded = score < threshold

    # Brain Rot: 3 of last 5 scores < 50
    brain_rot_detected = False
    if len(recent_scores) >= 5:
        last_five = recent_scores[-5:]
        below_50_count = sum(1 for s in last_five if s < 50)
        brain_rot_detected = below_50_count >= 3

    # Recommend fork if degraded or brain rot
    fork_recommendation = is_degraded or brain_rot_detected

    details = {
        "turn_penalty": round(turn_penalty, 2),
        "token_penalty": round(token_penalty, 2),
        "error_penalty": round(error_penalty, 2),
        "total_penalty": round(total_penalty, 2),
        "turn_count": turn_count,
        "cumulative_tokens": cumulative_tokens,
        "error_count": error_count,
    }

    return ContextHealthResult(
        score=round(score, 2),
        is_degraded=is_degraded,
        brain_rot_detected=brain_rot_detected,
        fork_recommendation=fork_recommendation,
        details=details,
    )


# ---------------------------------------------------------------------------
# Cost metrics
# ---------------------------------------------------------------------------

def calculate_cost_metrics(
    total_tokens: int,
    loop_tokens: int,
    model: str = "gpt-4o",
) -> CostMetrics:
    """Estimates cost and waste metrics for the session."""
    pricing = _PRICING.get(model, _DEFAULT_PRICING)

    # Use averaged rate (input + output) / 2 as an approximation
    avg_rate_per_token = ((pricing["input"] + pricing["output"]) / 2) / 1_000_000
    estimated_cost = total_tokens * avg_rate_per_token

    # Context utilization: useful tokens / total
    useful_tokens = max(0, total_tokens - loop_tokens)
    utilization = (useful_tokens / total_tokens * 100) if total_tokens > 0 else 100.0

    # Cost rating based on utilization
    if utilization >= 80:
        cost_rating = "efficient"
    elif utilization >= 50:
        cost_rating = "moderate"
    else:
        cost_rating = "wasteful"

    return CostMetrics(
        estimated_cost_usd=round(estimated_cost, 6),
        tokens_wasted_on_loops=loop_tokens,
        context_utilization_pct=round(utilization, 2),
        cost_rating=cost_rating,
    )


# ---------------------------------------------------------------------------
# Fork summary
# ---------------------------------------------------------------------------

def generate_fork_summary(
    session_facts: List[str],
    key_decisions: List[str],
) -> dict:
    """Creates a clean JSON seed for starting a new session."""
    return {
        "verified_facts": list(session_facts),
        "key_decisions": list(key_decisions),
        "fork_reason": "context_health_degraded",
    }
