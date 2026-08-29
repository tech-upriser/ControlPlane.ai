"""
Evaluate Routes - Two-Tier Hybrid Verification Engine
═════════════════════════════════════════════════════

Tier 1: Fast deterministic guardrails (injection, PII, content safety)
        → Short-circuits on critical violations (zero token cost)

Tier 2: Gemini LLM-as-a-Judge (semantic claim verification)
        → Deep factual grounding for responses that pass Tier 1

Graceful Fallback: If GEMINI_API_KEY is not set, Tier 2 is skipped
and the system uses the original heuristic pipeline.

Endpoints:
  POST /v1/evaluate  - Full two-tier analysis of a prompt+response pair
  POST /v1/reword    - Heuristic correction of flagged text
"""

import os
import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.segment_analyzer import analyze_response, SegmentAnalysis
from app.core.reword_engine import reword_text
from app.core.risk_engine import RiskEngine
from app.core.gemini_judge import judge_response, is_tier2_available
from app.checkers.hallucination_checker import check_hallucination
from app.checkers.content_safety import check_content_safety
from app.checkers.pii_scanner import scan_text as scan_pii
from app.checkers.injection_detector import detect_injection
from app.checkers.context_health import calculate_cost_metrics

router = APIRouter()
logger = logging.getLogger("controlplane.evaluate")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    prompt: str
    response_text: str
    session_id: Optional[str] = None
    platform: Optional[str] = "chatgpt"


class SubMetricsPerformance(BaseModel):
    accuracy: int
    hallucination_risks: int
    hallucination_risk_level: str
    fabrication_signals: List[str]
    hedging_ratio: float
    prompt_alignment: float


class SubMetricsCost(BaseModel):
    token_consumption: int
    hallucination_rework_cost: int
    loop_detected: bool
    cost_rating: str
    estimated_cost_usd: float


class SubMetricsResponsibility(BaseModel):
    hate_speech: int
    pii_leaks: int
    bias_detection: int
    pii_count: int
    tone_compliance: int
    toxicity_detected: bool
    injection_detected: bool
    content_safe: bool


class DimensionScore(BaseModel):
    score: int
    label: str
    sub_metrics: dict


class SegmentResponse(BaseModel):
    text: str
    classification: str
    confidence: int
    badge: str
    reasons: List[str]


class EvaluateResponse(BaseModel):
    evaluation_id: str
    overall_confidence: int
    risk_level: str
    recommended_action: str
    dimensions: dict
    segments: List[SegmentResponse]
    confidence_distribution: List[int]
    engine_tier: str = "tier1"  # "tier1" (heuristic) or "tier2" (gemini)


class RewordRequest(BaseModel):
    original_text: str
    prompt: str
    reasons: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None


class RewordResponse(BaseModel):
    corrected_text: str
    new_confidence: int
    new_classification: str
    new_badge: str


# ---------------------------------------------------------------------------
# Tier 1: Fast Deterministic Guardrails
# ---------------------------------------------------------------------------

def _run_tier1_checks(prompt: str, response_text: str) -> dict:
    """Runs all fast, local, zero-cost guardrail checks.

    Returns a dict with all checker results and a 'short_circuit' flag
    that is True if a critical violation was detected.
    """
    # Run injection detection on the prompt
    injection_result = detect_injection(prompt)

    # Run safety/PII on the response
    safety_result = check_content_safety(response_text)
    pii_matches = scan_pii(response_text)

    # Determine if we should short-circuit
    short_circuit = False
    short_circuit_reason = None

    if injection_result.is_injection and injection_result.confidence >= 0.8:
        short_circuit = True
        short_circuit_reason = f"Prompt injection detected: {injection_result.injection_type}"
        logger.warning(f"TIER 1 SHORT-CIRCUIT: {short_circuit_reason}")

    if not safety_result.is_safe and "violence" in safety_result.categories_flagged:
        short_circuit = True
        short_circuit_reason = f"Unsafe content: {', '.join(safety_result.categories_flagged)}"
        logger.warning(f"TIER 1 SHORT-CIRCUIT: {short_circuit_reason}")

    return {
        "injection": injection_result,
        "safety": safety_result,
        "pii": pii_matches,
        "short_circuit": short_circuit,
        "short_circuit_reason": short_circuit_reason,
    }


def _build_short_circuit_response(tier1: dict, response_text: str) -> EvaluateResponse:
    """Builds an immediate block response when Tier 1 detects critical violations."""
    reason = tier1["short_circuit_reason"] or "Critical safety violation detected"

    return EvaluateResponse(
        evaluation_id=str(uuid.uuid4()),
        overall_confidence=0,
        risk_level="critical",
        recommended_action="block",
        dimensions={
            "performance": {
                "score": 0,
                "label": "Reliability",
                "sub_metrics": {
                    "accuracy": 0,
                    "hallucination_risks": 0,
                    "hallucination_risk_level": "high",
                    "fabrication_signals": [],
                    "hedging_ratio": 0.0,
                    "prompt_alignment": 0.0,
                },
            },
            "cost": {
                "score": 0,
                "label": "Efficiency",
                "sub_metrics": {
                    "token_consumption": len(response_text.split()) * 2,
                    "hallucination_rework_cost": 100,
                    "loop_detected": False,
                    "cost_rating": "critical",
                    "estimated_cost_usd": 0.0,
                },
            },
            "responsibility": {
                "score": 0,
                "label": "Safety & Ethics",
                "sub_metrics": {
                    "hate_speech": 0 if not tier1["safety"].is_safe else 90,
                    "pii_leaks": max(0, 90 - len(tier1["pii"]) * 25),
                    "bias_detection": 0,
                    "pii_count": len(tier1["pii"]),
                    "tone_compliance": 0,
                    "toxicity_detected": not tier1["safety"].is_safe,
                    "injection_detected": tier1["injection"].is_injection,
                    "content_safe": False,
                },
            },
        },
        segments=[
            SegmentResponse(
                text=response_text[:200],
                classification="hallucination",
                confidence=0,
                badge="Blocked",
                reasons=[reason],
            )
        ],
        confidence_distribution=[0] * 20,
        engine_tier="tier1_block",
    )


# ---------------------------------------------------------------------------
# Tier 2: Gemini LLM-as-a-Judge → EvaluateResponse
# ---------------------------------------------------------------------------

async def _run_tier2(
    prompt: str, response_text: str, tier1: dict
) -> Optional[EvaluateResponse]:
    """Calls Gemini for semantic evaluation and converts to EvaluateResponse.

    Returns None if Tier 2 is unavailable or fails, triggering heuristic fallback.
    """
    gemini_eval = await judge_response(prompt, response_text)
    if gemini_eval is None:
        return None

    # Estimate tokens for cost dimension
    token_estimate = len(response_text.split()) * 2
    rework_cost = 30 if gemini_eval.hallucination_risk_level in ("high", "medium") else 0

    cost_metrics = calculate_cost_metrics(
        total_tokens=token_estimate,
        loop_tokens=0,
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
    )

    # Build dimensions from Gemini's scores
    dimensions = {
        "performance": {
            "score": gemini_eval.performance_score,
            "label": "Reliability",
            "sub_metrics": SubMetricsPerformance(
                accuracy=gemini_eval.accuracy,
                hallucination_risks=100 - gemini_eval.accuracy,
                hallucination_risk_level=gemini_eval.hallucination_risk_level,
                fabrication_signals=gemini_eval.fabrication_signals,
                hedging_ratio=gemini_eval.hedging_ratio,
                prompt_alignment=gemini_eval.prompt_alignment,
            ).model_dump(),
        },
        "cost": {
            "score": gemini_eval.cost_score,
            "label": "Efficiency",
            "sub_metrics": SubMetricsCost(
                token_consumption=token_estimate,
                hallucination_rework_cost=rework_cost,
                loop_detected=False,
                cost_rating=cost_metrics.cost_rating,
                estimated_cost_usd=cost_metrics.estimated_cost_usd,
            ).model_dump(),
        },
        "responsibility": {
            "score": gemini_eval.responsibility_score,
            "label": "Safety & Ethics",
            "sub_metrics": SubMetricsResponsibility(
                hate_speech=90 if tier1["safety"].is_safe else 40,
                pii_leaks=max(10, 90 - len(tier1["pii"]) * 25),
                bias_detection=40 if gemini_eval.bias_detected else 85,
                pii_count=len(tier1["pii"]),
                tone_compliance=gemini_eval.tone_compliance,
                toxicity_detected=not tier1["safety"].is_safe,
                injection_detected=tier1["injection"].is_injection,
                content_safe=tier1["safety"].is_safe,
            ).model_dump(),
        },
    }

    # Convert Gemini segments to response format
    segments = [
        SegmentResponse(
            text=seg.text,
            classification=seg.classification,
            confidence=seg.confidence,
            badge=seg.badge,
            reasons=seg.reasons,
        )
        for seg in gemini_eval.segments
    ]

    # Generate confidence distribution from segment scores
    distribution = _generate_distribution(gemini_eval.segments)

    return EvaluateResponse(
        evaluation_id=str(uuid.uuid4()),
        overall_confidence=gemini_eval.overall_confidence,
        risk_level=gemini_eval.risk_level,
        recommended_action=gemini_eval.recommended_action,
        dimensions=dimensions,
        segments=segments,
        confidence_distribution=distribution,
        engine_tier="tier2_gemini",
    )


def _generate_distribution(segments) -> List[int]:
    """Generates a 20-bucket confidence histogram from Gemini segments."""
    if not segments:
        return [0] * 20

    buckets = [0] * 20
    for seg in segments:
        idx = min(seg.confidence // 5, 19)
        buckets[idx] += 1

    # Smooth if few segments
    if len(segments) <= 5:
        avg = sum(s.confidence for s in segments) / len(segments)
        center = min(int(avg // 5), 19)
        smoothed = [0] * 20
        for i in range(20):
            d = abs(i - center)
            if d == 0:
                smoothed[i] = 70
            elif d == 1:
                smoothed[i] = 55
            elif d == 2:
                smoothed[i] = 40
            elif d == 3:
                smoothed[i] = 30
            elif d == 4:
                smoothed[i] = 20
            elif d <= 6:
                smoothed[i] = 10
            else:
                smoothed[i] = 5
        return smoothed

    return buckets


# ---------------------------------------------------------------------------
# Tier 1 Heuristic Fallback (original pipeline)
# ---------------------------------------------------------------------------

def _run_heuristic_fallback(
    prompt: str, response_text: str, tier1: dict
) -> EvaluateResponse:
    """Original heuristic pipeline — used when Tier 2 is unavailable."""
    hall_result = check_hallucination(response_text, prompt)

    checker_results = {
        "hallucination": hall_result,
        "content_safety": tier1["safety"],
        "pii": tier1["pii"],
        "injection": tier1["injection"],
    }

    risk_engine = RiskEngine()

    class _DefaultPolicy:
        context_health_threshold = 50.0

    risk_scores = risk_engine.evaluate(checker_results, _DefaultPolicy())

    analysis = analyze_response(prompt, response_text)

    dimensions = _build_heuristic_dimensions(
        analysis, risk_scores, hall_result, tier1, response_text
    )

    overall_confidence = max(0, min(100, int(100 - risk_scores.overall_risk)))

    segments = [
        SegmentResponse(
            text=seg.text,
            classification=seg.classification,
            confidence=seg.confidence,
            badge=seg.badge,
            reasons=seg.reasons,
        )
        for seg in analysis.segments
    ]

    return EvaluateResponse(
        evaluation_id=str(uuid.uuid4()),
        overall_confidence=overall_confidence,
        risk_level=risk_scores.risk_level,
        recommended_action=risk_scores.recommended_action,
        dimensions=dimensions,
        segments=segments,
        confidence_distribution=analysis.confidence_distribution,
        engine_tier="tier1_heuristic",
    )


def _build_heuristic_dimensions(
    analysis, risk_scores, hall_result, tier1, response_text
) -> dict:
    """Builds dimension scores using the original heuristic pipeline."""
    safety_result = tier1["safety"]
    pii_matches = tier1["pii"]
    injection_result = tier1["injection"]

    risk_to_accuracy = {"high": 33, "medium": 58, "low": 85}
    accuracy = risk_to_accuracy.get(hall_result.overall_risk, 75)

    risk_to_hall_score = {"high": 45, "medium": 65, "low": 90}
    hall_score = risk_to_hall_score.get(hall_result.overall_risk, 75)

    performance_sub = SubMetricsPerformance(
        accuracy=accuracy,
        hallucination_risks=hall_score,
        hallucination_risk_level=analysis.hallucination_risk_level,
        fabrication_signals=analysis.fabrication_signals,
        hedging_ratio=analysis.hedging_ratio,
        prompt_alignment=analysis.prompt_alignment,
    )

    token_estimate = len(response_text.split()) * 2
    rework_cost = 30 if hall_result.overall_risk in ("high", "medium") else 0

    cost_metrics = calculate_cost_metrics(
        total_tokens=token_estimate, loop_tokens=0, model="gpt-4o"
    )

    cost_sub = SubMetricsCost(
        token_consumption=token_estimate,
        hallucination_rework_cost=rework_cost,
        loop_detected=False,
        cost_rating=cost_metrics.cost_rating,
        estimated_cost_usd=cost_metrics.estimated_cost_usd,
    )

    hate_speech_score = 90 if safety_result.is_safe else (
        40 if "hate_speech" in safety_result.categories_flagged else 66
    )
    pii_score = 90 if len(pii_matches) == 0 else max(10, 90 - len(pii_matches) * 25)
    bias_score = 59 if not safety_result.is_safe else 82
    tone_score = 86 if safety_result.is_safe and analysis.hedging_ratio < 0.3 else 55

    resp_sub = SubMetricsResponsibility(
        hate_speech=hate_speech_score,
        pii_leaks=pii_score,
        bias_detection=bias_score,
        pii_count=len(pii_matches),
        tone_compliance=tone_score,
        toxicity_detected=not safety_result.is_safe,
        injection_detected=injection_result.is_injection,
        content_safe=safety_result.is_safe,
    )

    return {
        "performance": {
            "score": int(risk_scores.performance_score),
            "label": "Reliability",
            "sub_metrics": performance_sub.model_dump(),
        },
        "cost": {
            "score": int(risk_scores.cost_score),
            "label": "Efficiency",
            "sub_metrics": cost_sub.model_dump(),
        },
        "responsibility": {
            "score": int(risk_scores.responsibility_score),
            "label": "Safety & Ethics",
            "sub_metrics": resp_sub.model_dump(),
        },
    }


# ---------------------------------------------------------------------------
# POST /v1/evaluate — Two-Tier Hybrid Pipeline
# ---------------------------------------------------------------------------

@router.post("/v1/evaluate", response_model=EvaluateResponse)
async def evaluate(body: EvaluateRequest):
    """Two-Tier Hybrid Verification Engine.

    Tier 1: Fast deterministic guardrails (injection, PII, safety).
            Short-circuits on critical violations with action=block.

    Tier 2: Gemini LLM-as-a-Judge for semantic claim verification.
            Falls back to heuristic pipeline if Gemini is unavailable.
    """
    prompt = body.prompt
    response_text = body.response_text

    # ── TIER 1: Fast Deterministic Guardrails ──
    tier1 = _run_tier1_checks(prompt, response_text)

    # Short-circuit on critical violations (zero token cost)
    if tier1["short_circuit"]:
        logger.info("Tier 1 short-circuit triggered — returning immediate block")
        return _build_short_circuit_response(tier1, response_text)

    # ── TIER 2: Gemini Semantic Brain ──
    if is_tier2_available():
        logger.info("Tier 2 (Gemini) available — running semantic analysis")
        tier2_result = await _run_tier2(prompt, response_text, tier1)
        if tier2_result is not None:
            logger.info(f"Tier 2 succeeded — engine_tier={tier2_result.engine_tier}")
            return tier2_result
        logger.warning("Tier 2 failed — falling back to heuristic pipeline")

    # ── FALLBACK: Heuristic Pipeline ──
    logger.info("Using Tier 1 heuristic fallback pipeline")
    return _run_heuristic_fallback(prompt, response_text, tier1)


# ---------------------------------------------------------------------------
# POST /v1/reword
# ---------------------------------------------------------------------------

@router.post("/v1/reword", response_model=RewordResponse)
async def reword(body: RewordRequest):
    """Heuristic correction of flagged text.

    Strips hedging phrases, removes fake citations, softens speculative
    claims, and returns cleaned text with boosted confidence.
    """
    result = reword_text(body.original_text, body.prompt, body.reasons)

    return RewordResponse(
        corrected_text=result.corrected_text,
        new_confidence=result.new_confidence,
        new_classification=result.new_classification,
        new_badge=result.new_badge,
    )
