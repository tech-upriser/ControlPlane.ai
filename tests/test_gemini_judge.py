"""Tests for Gemini LLM-as-a-Judge Tier 2 engine."""

import os
import pytest
from app.core.gemini_judge import (
    judge_response,
    is_tier2_available,
    GeminiEvaluation,
    GeminiClaimVerdict,
    GeminiSegmentVerdict,
)


def test_tier2_availability():
    """Verify is_tier2_available returns True when API key is set."""
    assert is_tier2_available() is True


def test_pydantic_schemas():
    """Verify Pydantic schemas validate structured JSON output properly."""
    claim = GeminiClaimVerdict(
        claim_text="Paris is the capital of France.",
        grounding="supported",
        confidence=98,
        reasoning="Factually verified geographic consensus."
    )
    assert claim.grounding == "supported"
    assert claim.confidence == 98

    segment = GeminiSegmentVerdict(
        text="The capital of France is Paris.",
        classification="verified",
        confidence=95,
        badge="High Confidence",
        reasons=["Factually grounded"]
    )
    assert segment.classification == "verified"

    eval_obj = GeminiEvaluation(
        overall_confidence=95,
        risk_level="low",
        recommended_action="allow",
        claims=[claim],
        segments=[segment],
        performance_score=95,
        cost_score=90,
        responsibility_score=98,
        accuracy=98,
        hallucination_risk_level="low",
        hedging_ratio=0.0,
        prompt_alignment=1.0,
        fabrication_signals=[],
        bias_detected=False,
        tone_compliance=95
    )
    assert eval_obj.overall_confidence == 95
    assert eval_obj.risk_level == "low"
    assert eval_obj.recommended_action == "allow"


@pytest.mark.asyncio
async def test_live_gemini_judge_clean():
    """Live call to Gemini API for a clean response."""
    result = await judge_response(
        prompt="What is the capital of France?",
        response_text="The capital of France is Paris."
    )
    if result is not None:
        assert isinstance(result, GeminiEvaluation)
        assert result.overall_confidence >= 80
        assert result.recommended_action in ("allow", "flag")


@pytest.mark.asyncio
async def test_live_gemini_judge_hallucination():
    """Live call to Gemini API for a hallucinated response."""
    result = await judge_response(
        prompt="What is the capital of France?",
        response_text="The capital of France is Berlin."
    )
    if result is not None:
        assert isinstance(result, GeminiEvaluation)
        assert result.hallucination_risk_level in ("high", "medium")
        has_hallucination_segment = any(
            seg.classification == "hallucination" for seg in result.segments
        )
        assert has_hallucination_segment or result.overall_confidence < 70

