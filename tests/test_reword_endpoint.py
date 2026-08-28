"""Tests for the POST /v1/reword endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_reword_hedging_text():
    """Rewording should strip hedging phrases and boost confidence."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/reword",
            json={
                "original_text": "I think AI might be useful. Probably it could help with data analysis.",
                "prompt": "Is AI useful?",
                "reasons": ["Contains hedging patterns"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "corrected_text" in data
        assert "new_confidence" in data
        assert "new_classification" in data
        assert "new_badge" in data
        assert data["new_confidence"] >= 85
        # Hedging phrases should be reduced or removed
        corrected_lower = data["corrected_text"].lower()
        # At least some hedging should be stripped
        hedging_count = sum(1 for p in ["i think", "probably"] if p in corrected_lower)
        original_hedging = sum(1 for p in ["i think", "probably"] if p in "I think AI might be useful. Probably it could help.".lower())
        assert hedging_count < original_hedging


@pytest.mark.asyncio
async def test_reword_fake_citations():
    """Rewording should remove fabricated URLs."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/reword",
            json={
                "original_text": "According to https://example.com/fake-study, AI adoption is growing rapidly.",
                "prompt": "Tell me about AI adoption",
                "reasons": ["Fabricated claims", "High hallucination risk"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Fake URL should be removed
        assert "example.com" not in data["corrected_text"]
        assert data["new_confidence"] >= 85


@pytest.mark.asyncio
async def test_reword_speculative_claims():
    """Rewording should soften absolute speculative language."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/reword",
            json={
                "original_text": "AI will revolutionize everything and is guaranteed to solve all problems.",
                "prompt": "What is the future of AI?",
                "reasons": ["High hallucination risk"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        corrected_lower = data["corrected_text"].lower()
        # "will revolutionize" should be softened
        assert "will revolutionize" not in corrected_lower
        assert data["new_confidence"] >= 85


@pytest.mark.asyncio
async def test_reword_clean_text():
    """Clean text should be returned largely unchanged with moderate confidence."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/reword",
            json={
                "original_text": "Machine learning models use data to make predictions.",
                "prompt": "What is ML?",
                "reasons": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_confidence"] >= 85
        assert data["new_classification"] == "verified"
        assert data["new_badge"] == "High Confidence"


@pytest.mark.asyncio
async def test_reword_empty_text():
    """Empty text should return with full confidence."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/reword",
            json={
                "original_text": "",
                "prompt": "test",
                "reasons": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_confidence"] == 100


@pytest.mark.asyncio
async def test_reword_response_schema():
    """Verify the response contains all required fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/reword",
            json={
                "original_text": "I think this is probably correct.",
                "prompt": "test",
                "reasons": ["hedging"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["corrected_text"], str)
        assert isinstance(data["new_confidence"], int)
        assert data["new_classification"] in ("verified", "ambiguous", "hallucination")
        assert data["new_badge"] in ("High Confidence", "High Cost / Rework?", "Hallucination Detected")
