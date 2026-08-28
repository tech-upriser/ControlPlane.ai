"""Tests for the POST /v1/evaluate endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_evaluate_clean_text():
    """Clean response text should yield high overall confidence."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/evaluate",
            json={
                "prompt": "What are the benefits of regular exercise?",
                "response_text": "Regular exercise improves cardiovascular health, strengthens muscles, and boosts mental wellbeing through endorphin release.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "evaluation_id" in data
        assert data["overall_confidence"] >= 50
        assert data["risk_level"] in ("low", "medium", "high", "critical")
        assert data["recommended_action"] in ("allow", "flag", "reword", "block", "escalate")
        assert len(data["segments"]) >= 1
        assert len(data["confidence_distribution"]) == 20


@pytest.mark.asyncio
async def test_evaluate_with_fabrication():
    """Text with fake URLs should detect fabrication and lower confidence."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/evaluate",
            json={
                "prompt": "What are AI adoption trends?",
                "response_text": "According to https://example.com/fake-study, AI adoption is at 100%. See https://test.com/report for details. I think this might be accurate, probably.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have lower confidence due to fabrication + hedging
        assert data["overall_confidence"] < 90
        # Should have segments with issues
        has_flagged = any(
            seg["classification"] in ("ambiguous", "hallucination")
            for seg in data["segments"]
        )
        assert has_flagged


@pytest.mark.asyncio
async def test_evaluate_response_schema():
    """Verify the full response schema matches the contract."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/evaluate",
            json={
                "prompt": "Tell me about machine learning",
                "response_text": "Machine learning is a subset of artificial intelligence that learns from data.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # Top-level fields
        assert "evaluation_id" in data
        assert "overall_confidence" in data
        assert "risk_level" in data
        assert "recommended_action" in data
        assert "dimensions" in data
        assert "segments" in data
        assert "confidence_distribution" in data

        # Dimensions structure
        dims = data["dimensions"]
        assert "performance" in dims
        assert "cost" in dims
        assert "responsibility" in dims

        for dim_name in ("performance", "cost", "responsibility"):
            dim = dims[dim_name]
            assert "score" in dim
            assert "label" in dim
            assert "sub_metrics" in dim

        # Performance sub-metrics
        perf_sub = dims["performance"]["sub_metrics"]
        assert "accuracy" in perf_sub
        assert "hallucination_risks" in perf_sub
        assert "hallucination_risk_level" in perf_sub
        assert "fabrication_signals" in perf_sub
        assert "hedging_ratio" in perf_sub
        assert "prompt_alignment" in perf_sub

        # Cost sub-metrics
        cost_sub = dims["cost"]["sub_metrics"]
        assert "token_consumption" in cost_sub
        assert "cost_rating" in cost_sub
        assert "estimated_cost_usd" in cost_sub

        # Responsibility sub-metrics
        resp_sub = dims["responsibility"]["sub_metrics"]
        assert "hate_speech" in resp_sub
        assert "pii_leaks" in resp_sub
        assert "pii_count" in resp_sub
        assert "content_safe" in resp_sub
        assert "injection_detected" in resp_sub

        # Segment structure
        for seg in data["segments"]:
            assert "text" in seg
            assert "classification" in seg
            assert seg["classification"] in ("verified", "ambiguous", "hallucination")
            assert "confidence" in seg
            assert 0 <= seg["confidence"] <= 100
            assert "badge" in seg
            assert "reasons" in seg


@pytest.mark.asyncio
async def test_evaluate_with_hedging():
    """Text heavy with hedging should flag ambiguous segments."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/evaluate",
            json={
                "prompt": "Is AI useful?",
                "response_text": "I think AI might be useful. Probably it could help. I'm not sure about the specifics. It seems like it might work. As far as I know, it could be beneficial.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # High hedging should lower confidence
        assert data["dimensions"]["performance"]["sub_metrics"]["hedging_ratio"] > 0.1


@pytest.mark.asyncio
async def test_evaluate_optional_fields():
    """session_id and platform are optional and should not cause errors."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/evaluate",
            json={
                "prompt": "test",
                "response_text": "test response",
                "session_id": "session-123",
                "platform": "claude",
            },
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_evaluate_multi_paragraph():
    """Multi-paragraph response should produce multiple segments."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/evaluate",
            json={
                "prompt": "What are the key factors driving AI adoption?",
                "response_text": (
                    "AI adoption is driven by several key factors.\n\n"
                    "First, AI enables demand forecasting with greater accuracy.\n\n"
                    "Second, it helps optimize inventory levels and reduce costs.\n\n"
                    "Finally, AI improves supplier collaboration and decision-making."
                ),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["segments"]) >= 3
