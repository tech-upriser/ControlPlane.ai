"""
Evaluate Routes - Backend API bridge for the Chrome extension.

Endpoints:
  POST /v1/evaluate  - Full analysis of a prompt+response pair
  POST /v1/reword    - Heuristic correction of flagged text
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.segment_analyzer import analyze_response, SegmentAnalysis
from app.core.reword_engine import reword_text
from app.core.risk_engine import RiskEngine
from app.checkers.hallucination_checker import check_hallucination
from app.checkers.content_safety import check_content_safety
from app.checkers.pii_scanner import scan_text as scan_pii
from app.checkers.injection_detector import detect_injection
from app.checkers.context_health import calculate_cost_metrics

router = APIRouter()


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
# Helper: build dimension scores
# ---------------------------------------------------------------------------

def _build_dimensions(
    analysis,
    risk_scores,
    hall_result,
    safety_result,
    pii_matches,
    injection_result,
    response_text: str,
) -> dict:
    """Builds the 3-dimension scores with sub-metrics."""

    # --- Performance (Reliability) ---
    # Accuracy: inverse of hallucination risk (high=33, medium=58, low=85)
    risk_to_accuracy = {"high": 33, "medium": 58, "low": 85}
    accuracy = risk_to_accuracy.get(hall_result.overall_risk, 75)

    # Hallucination risk as a percentage score (high=45, medium=65, low=90)
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

    # --- Cost (Efficiency) ---
    # Estimate token consumption from text length
    token_estimate = len(response_text.split()) * 2  # rough tokens estimate
    rework_cost = 30 if hall_result.overall_risk in ("high", "medium") else 0

    cost_metrics = calculate_cost_metrics(
        total_tokens=token_estimate,
        loop_tokens=0,  # No loop context in single-evaluation mode
        model="gpt-4o",
    )

    cost_sub = SubMetricsCost(
        token_consumption=token_estimate,
        hallucination_rework_cost=rework_cost,
        loop_detected=False,
        cost_rating=cost_metrics.cost_rating,
        estimated_cost_usd=cost_metrics.estimated_cost_usd,
    )

    # --- Responsibility (Safety & Ethics) ---
    # Sub-scores: higher = better (safer)
    hate_speech_score = 90 if safety_result.is_safe else (40 if "hate_speech" in safety_result.categories_flagged else 66)
    pii_score = 90 if len(pii_matches) == 0 else max(10, 90 - len(pii_matches) * 25)
    # Bias detection: heuristic based on content safety categories
    bias_score = 59 if not safety_result.is_safe else 82
    # Tone compliance: based on hedging and safety
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
# POST /v1/evaluate
# ---------------------------------------------------------------------------

@router.post("/v1/evaluate", response_model=EvaluateResponse)
async def evaluate(body: EvaluateRequest):
    """Full analysis of a prompt + response pair.

    Runs all checkers, segments the response, classifies each segment,
    computes 3-dimension risk scores, and returns structured JSON for
    the Chrome extension frontend.
    """
    prompt = body.prompt
    response_text = body.response_text

    # 1. Run whole-text checkers
    hall_result = check_hallucination(response_text, prompt)
    safety_result = check_content_safety(response_text)
    pii_matches = scan_pii(response_text)
    injection_result = detect_injection(prompt)  # Injection is on the prompt

    # 2. Build checker_results for RiskEngine
    checker_results = {
        "hallucination": hall_result,
        "content_safety": safety_result,
        "pii": pii_matches,
        "injection": injection_result,
    }

    # 3. Run RiskEngine with a default policy stub
    risk_engine = RiskEngine()

    class _DefaultPolicy:
        context_health_threshold = 50.0

    risk_scores = risk_engine.evaluate(checker_results, _DefaultPolicy())

    # 4. Run segment analysis
    analysis = analyze_response(prompt, response_text)

    # 5. Build dimensions
    dimensions = _build_dimensions(
        analysis, risk_scores, hall_result, safety_result,
        pii_matches, injection_result, response_text,
    )

    # 6. Overall confidence = 100 - overall_risk
    overall_confidence = max(0, min(100, int(100 - risk_scores.overall_risk)))

    # 7. Assemble segment responses
    segment_responses = [
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
        segments=segment_responses,
        confidence_distribution=analysis.confidence_distribution,
    )


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
