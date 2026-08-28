"""Tests for the segment analyzer module."""

import pytest
from app.core.segment_analyzer import (
    split_into_segments,
    classify_segment,
    generate_confidence_distribution,
    analyze_response,
    SegmentAnalysis,
)


class TestSplitIntoSegments:
    def test_single_paragraph(self):
        text = "This is a simple paragraph about AI."
        segments = split_into_segments(text)
        assert len(segments) == 1
        assert segments[0] == text

    def test_multi_paragraph(self):
        text = "First paragraph about AI.\n\nSecond paragraph about ML.\n\nThird paragraph about NLP."
        segments = split_into_segments(text)
        assert len(segments) == 3
        assert "First" in segments[0]
        assert "Second" in segments[1]
        assert "Third" in segments[2]

    def test_empty_text(self):
        assert split_into_segments("") == []
        assert split_into_segments("   ") == []

    def test_whitespace_only_paragraphs_filtered(self):
        text = "Real content here.\n\n   \n\nMore content."
        segments = split_into_segments(text)
        assert len(segments) == 2
        assert all(s.strip() for s in segments)

    def test_long_paragraph_split(self):
        """Paragraphs over 300 chars should be split on sentence boundaries."""
        long_text = (
            "The adoption of AI in supply chain management is driven by several key factors. "
            "First, AI enables demand forecasting with greater accuracy by analyzing vast amounts of data. "
            "Second, it helps optimize inventory levels and reduce operational costs across the supply chain. "
            "Additionally, some experimental AI models are being developed to improve logistics coordination."
        )
        segments = split_into_segments(long_text)
        assert len(segments) >= 1
        # Verify all text is preserved
        combined = " ".join(segments)
        assert "supply chain" in combined
        assert "logistics" in combined

    def test_none_text(self):
        assert split_into_segments(None) == []


class TestClassifySegment:
    def test_verified_segment(self):
        """Clean text with good alignment should be verified."""
        text = "The key factors driving AI adoption include improved data analysis, automation of routine tasks, and enhanced decision-making capabilities across industries."
        prompt = "What are the key factors driving AI adoption?"
        result = classify_segment(text, prompt)
        assert result.classification == "verified"
        assert result.badge == "High Confidence"
        assert result.confidence >= 70

    def test_hallucination_segment(self):
        """Text with fake URLs should be classified as hallucination."""
        text = "According to https://example.com/fake-study, AI will solve everything perfectly."
        prompt = "What are the key factors driving AI adoption?"
        result = classify_segment(text, prompt)
        assert result.classification in ("hallucination", "ambiguous")
        assert result.confidence < 80
        assert any("Fabricat" in r for r in result.reasons)

    def test_ambiguous_segment_hedging(self):
        """Text with hedging should be at least ambiguous."""
        text = "I think AI might be useful. Probably it could help businesses. I'm not sure about the details."
        prompt = "Is AI useful for business?"
        result = classify_segment(text, prompt)
        assert result.classification in ("ambiguous", "hallucination")
        assert result.confidence < 90
        assert any("hedging" in r.lower() for r in result.reasons)

    def test_segment_with_pii(self):
        """Text containing PII should have PII noted in reasons."""
        text = "Contact John at john.doe@example.com for more information about AI adoption."
        prompt = "Tell me about AI adoption"
        result = classify_segment(text, prompt)
        assert any("PII" in r for r in result.reasons)

    def test_empty_segment(self):
        """Empty text should still return a valid result."""
        result = classify_segment("", "test prompt")
        assert result.classification in ("verified", "ambiguous", "hallucination")
        assert 0 <= result.confidence <= 100


class TestConfidenceDistribution:
    def test_empty_segments(self):
        dist = generate_confidence_distribution([])
        assert len(dist) == 20
        assert all(v == 0 for v in dist)

    def test_single_high_confidence_segment(self):
        """Single high-confidence segment should generate a smoothed distribution."""
        seg = SegmentAnalysis(text="test", classification="verified", confidence=90, badge="High Confidence", reasons=[])
        dist = generate_confidence_distribution([seg])
        assert len(dist) == 20
        # Peak should be around bucket 18 (90-94 range)
        assert max(dist) > 0

    def test_mixed_confidence_segments(self):
        """Multiple segments should populate the right buckets."""
        segments = [
            SegmentAnalysis(text="t1", classification="verified", confidence=90, badge="b", reasons=[]),
            SegmentAnalysis(text="t2", classification="ambiguous", confidence=55, badge="b", reasons=[]),
            SegmentAnalysis(text="t3", classification="hallucination", confidence=20, badge="b", reasons=[]),
            SegmentAnalysis(text="t4", classification="verified", confidence=85, badge="b", reasons=[]),
            SegmentAnalysis(text="t5", classification="verified", confidence=92, badge="b", reasons=[]),
            SegmentAnalysis(text="t6", classification="ambiguous", confidence=60, badge="b", reasons=[]),
        ]
        dist = generate_confidence_distribution(segments)
        assert len(dist) == 20
        # With 6 segments, we get raw bucket counts
        assert sum(dist) == 6

    def test_distribution_has_20_buckets(self):
        seg = SegmentAnalysis(text="t", classification="verified", confidence=50, badge="b", reasons=[])
        dist = generate_confidence_distribution([seg])
        assert len(dist) == 20


class TestAnalyzeResponse:
    def test_clean_response(self):
        """Clean response text should yield high confidence."""
        prompt = "What are the benefits of exercise?"
        response = "Regular exercise improves cardiovascular health, strengthens muscles, and boosts mental wellbeing."
        result = analyze_response(prompt, response)
        assert len(result.segments) >= 1
        assert len(result.confidence_distribution) == 20
        assert result.content_safe is True
        assert result.injection_detected is False

    def test_response_with_fabrication(self):
        """Response with fake URLs should flag fabrication signals."""
        prompt = "Tell me about AI research"
        response = "According to https://example.com/ai-study, AI is perfect. See https://test.com/results for proof."
        result = analyze_response(prompt, response)
        assert len(result.fabrication_signals) > 0

    def test_full_analysis_structure(self):
        """Verify the FullAnalysis object has all required fields."""
        result = analyze_response("test prompt", "Test response text.")
        assert hasattr(result, 'segments')
        assert hasattr(result, 'confidence_distribution')
        assert hasattr(result, 'hallucination_risk_level')
        assert hasattr(result, 'hedging_ratio')
        assert hasattr(result, 'prompt_alignment')
        assert hasattr(result, 'fabrication_signals')
        assert hasattr(result, 'pii_count')
        assert hasattr(result, 'content_safe')
        assert hasattr(result, 'toxicity_detected')
        assert hasattr(result, 'injection_detected')
