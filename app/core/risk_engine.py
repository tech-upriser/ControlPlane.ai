from pydantic import BaseModel
from typing import Literal, Optional, List


class RiskScores(BaseModel):
    performance_score: float    # 0-100: from context_health + hallucination + rabbit_hole
    cost_score: float           # 0-100: from loop_breaker + cost_metrics
    responsibility_score: float # 0-100: from pii + injection + content_safety + tool_safety
    overall_risk: float         # 0-100: weighted average
    risk_level: Literal["low", "medium", "high", "critical"]
    recommended_action: Literal["allow", "flag", "reword", "block", "escalate"]
    triggered_reasons: List[str]  # human-readable reasons for the decision


class RiskEngine:
    """Unified 3-pillar risk scoring and decision engine."""

    def evaluate(self, checker_results: dict, policy: object) -> RiskScores:
        """
        Aggregates individual checker results into 3 composite scores.

        checker_results keys (all optional):
          - "pii": list of PII matches or None
          - "injection": object with is_injection, confidence attrs or None
          - "content_safety": object with is_safe, severity, categories_flagged attrs or None
          - "hallucination": object with overall_risk attr or None
          - "rabbit_hole": object with is_relevant attr or None
          - "loop": object with is_loop attr or None
          - "context_health": object with score attr or None
          - "cost": object with cost_rating attr or None
          - "tool_call_blocked": bool
        """
        reasons: List[str] = []

        # --- Responsibility Score ---
        resp_penalty = 0.0

        # PII penalty: +40 per match, max 100
        pii_results = checker_results.get('pii')
        if pii_results and len(pii_results) > 0:
            pii_penalty = min(len(pii_results) * 40, 100)
            resp_penalty += pii_penalty
            reasons.append(f"PII detected: {len(pii_results)} match(es)")

        # Injection penalty: +80
        injection_result = checker_results.get('injection')
        if injection_result and getattr(injection_result, 'is_injection', False):
            resp_penalty += 80
            reasons.append("Prompt injection detected")

        # Content safety penalty: +60 for high severity
        safety_result = checker_results.get('content_safety')
        if safety_result and not getattr(safety_result, 'is_safe', True):
            severity = getattr(safety_result, 'severity', 'low')
            if severity == 'high':
                resp_penalty += 60
            elif severity == 'medium':
                resp_penalty += 30
            else:
                resp_penalty += 15
            categories = getattr(safety_result, 'categories_flagged', [])
            reasons.append(f"Unsafe content: {', '.join(categories)}")

        # Tool call blocked penalty: +50
        if checker_results.get('tool_call_blocked', False):
            resp_penalty += 50
            reasons.append("Restricted tool call blocked")

        responsibility_score = max(0.0, 100.0 - resp_penalty)

        # --- Performance Score ---
        perf_penalty = 0.0

        # Hallucination penalty
        hallucination_result = checker_results.get('hallucination')
        if hallucination_result:
            risk_level = getattr(hallucination_result, 'overall_risk', 'low')
            if risk_level == 'high':
                perf_penalty += 50
                reasons.append("High hallucination risk")
            elif risk_level == 'medium':
                perf_penalty += 25
                reasons.append("Medium hallucination risk")

        # Context health penalty
        context_result = checker_results.get('context_health')
        if context_result:
            ctx_score = getattr(context_result, 'score', 100)
            threshold = getattr(policy, 'context_health_threshold', 50.0)
            if ctx_score < threshold:
                perf_penalty += (threshold - ctx_score)
                reasons.append(f"Context health degraded: {ctx_score:.1f}")

        # Query drift penalty: +30
        rabbit_result = checker_results.get('rabbit_hole')
        if rabbit_result and not getattr(rabbit_result, 'is_relevant', True):
            perf_penalty += 30
            reasons.append("Query drift detected")

        performance_score = max(0.0, 100.0 - perf_penalty)

        # --- Cost Score ---
        cost_penalty = 0.0

        # Loop penalty: +60
        loop_result = checker_results.get('loop')
        if loop_result and getattr(loop_result, 'is_loop', False):
            cost_penalty += 60
            reasons.append("Repetitive loop detected")

        # Cost waste penalty: +40
        cost_result = checker_results.get('cost')
        if cost_result:
            cost_rating = getattr(cost_result, 'cost_rating', 'efficient')
            if cost_rating == 'wasteful':
                cost_penalty += 40
                reasons.append("Wasteful token usage")
            elif cost_rating == 'moderate':
                cost_penalty += 15

        cost_score = max(0.0, 100.0 - cost_penalty)

        # --- Overall Risk (weighted average) ---
        # Higher scores = better. overall is also "how good things are".
        overall_weighted = (
            performance_score * 0.3
            + cost_score * 0.2
            + responsibility_score * 0.5
        )

        # Invert for decision thresholds: higher inverse = worse
        inverse_overall = 100.0 - overall_weighted

        # Decision thresholds
        if inverse_overall >= 85:
            recommended_action = "escalate"
            risk_level = "critical"
        elif inverse_overall >= 70:
            recommended_action = "block"
            risk_level = "critical"
        elif inverse_overall >= 50:
            recommended_action = "reword"
            risk_level = "high"
        elif inverse_overall >= 30:
            recommended_action = "flag"
            risk_level = "medium"
        else:
            recommended_action = "allow"
            risk_level = "low"

        return RiskScores(
            performance_score=round(performance_score, 2),
            cost_score=round(cost_score, 2),
            responsibility_score=round(responsibility_score, 2),
            overall_risk=round(inverse_overall, 2),
            risk_level=risk_level,
            recommended_action=recommended_action,
            triggered_reasons=reasons,
        )
