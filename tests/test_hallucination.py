"""Tests for Hallucination Checker module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.checkers.hallucination_checker import (
    check_hallucination, calculate_hedging_ratio,
    detect_fake_citations, check_prompt_response_alignment,
)


class TestHedgingRatio:
    def test_no_hedging(self):
        ratio = calculate_hedging_ratio("The capital of France is Paris. It is a beautiful city.")
        assert ratio < 0.1

    def test_heavy_hedging(self):
        ratio = calculate_hedging_ratio(
            "I think it might be Paris, but I'm not sure, probably. It seems like it could be right."
        )
        assert ratio > 0.3

    def test_empty_text(self):
        ratio = calculate_hedging_ratio("")
        assert ratio == 0.0

    def test_moderate_hedging(self):
        ratio = calculate_hedging_ratio(
            "Paris is the capital of France. I believe it was established long ago. The Eiffel Tower is iconic."
        )
        # 1 hedging phrase out of 3 sentences
        assert 0.1 < ratio < 0.5


class TestFakeCitations:
    def test_example_com_url(self):
        signals = detect_fake_citations("See https://example.com/fake-article for details")
        assert len(signals) >= 1
        assert any("example.com" in s for s in signals)

    def test_test_com_url(self):
        signals = detect_fake_citations("More info at https://test.com/article")
        assert len(signals) >= 1

    def test_real_url(self):
        signals = detect_fake_citations("See https://en.wikipedia.org/wiki/Paris for details")
        assert len(signals) == 0

    def test_no_urls(self):
        signals = detect_fake_citations("Paris is the capital of France.")
        assert len(signals) == 0


class TestPromptResponseAlignment:
    def test_related_content(self):
        score = check_prompt_response_alignment(
            "What is the capital of France?",
            "Paris is the capital of France, located in Western Europe."
        )
        assert score > 0.2

    def test_off_topic(self):
        score = check_prompt_response_alignment(
            "weather in Tokyo",
            "Python is a great programming language for data science."
        )
        assert score < 0.2

    def test_empty_response(self):
        score = check_prompt_response_alignment("question", "")
        assert score == 0.0


class TestCheckHallucination:
    def test_confident_correct_response(self):
        result = check_hallucination(
            "The capital of France is Paris.",
            "What is the capital of France?"
        )
        assert result.hedging_ratio < 0.1
        assert result.overall_risk == "low"

    def test_heavy_hedging_response(self):
        result = check_hallucination(
            "I think it might be Paris, but I'm not sure, probably.",
            "What is the capital of France?"
        )
        assert result.hedging_ratio > 0.3
        assert result.overall_risk in ("medium", "high")

    def test_fake_url_in_response(self):
        result = check_hallucination(
            "See https://example.com/fake-article for details about Paris.",
            "Tell me about Paris"
        )
        assert len(result.fabrication_signals) >= 1

    def test_off_topic_response(self):
        result = check_hallucination(
            "Python is a great programming language for building web apps.",
            "weather in Tokyo"
        )
        assert result.overall_risk in ("medium", "high")

    def test_clean_response(self):
        result = check_hallucination(
            "Paris is the capital of France, located in Western Europe.",
            "Tell me about the capital of France"
        )
        assert result.overall_risk == "low"
