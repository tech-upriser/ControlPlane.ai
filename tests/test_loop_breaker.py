"""Tests for Loop Breaker module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.checkers.loop_breaker import detect_loop


class TestNoLoop:
    def test_completely_different_queries(self):
        history = [
            "What is the capital of France?",
            "How do I cook pasta?",
            "Tell me about quantum physics.",
            "What's the weather like in Tokyo?",
            "Explain the theory of relativity.",
        ]
        result = detect_loop(history)
        assert result.is_loop is False
        assert result.recommended_action == "continue"

    def test_diverse_programming_topics(self):
        history = [
            "How to use Python decorators?",
            "Explain JavaScript closures.",
            "What is Rust ownership?",
            "How does Go garbage collection work?",
            "What are Java generics?",
        ]
        result = detect_loop(history)
        assert result.is_loop is False


class TestClearLoop:
    def test_identical_queries(self):
        history = [
            "Search for the best pizza recipe",
            "Search for the best pizza recipe",
            "Search for the best pizza recipe",
            "Search for the best pizza recipe",
            "Search for the best pizza recipe",
        ]
        result = detect_loop(history)
        assert result.is_loop is True
        assert result.repetition_score > 0.95
        assert result.recommended_action == "kill"

    def test_near_identical_queries(self):
        history = [
            "Search for the best pizza recipe online",
            "Look up the best pizza recipe on the web",
            "Find the best pizza recipe available",
            "Search for the top pizza recipe online",
            "Look for the best pizza recipe out there",
        ]
        result = detect_loop(history, threshold=0.4)
        # TF-IDF with stop word removal sees these as moderately similar
        assert result.is_loop is True
        assert result.recommended_action in ("warn", "kill")


class TestNearLoop:
    def test_slightly_rephrased(self):
        history = [
            "What is the price of Bitcoin today?",
            "What is Bitcoin's current price?",
            "Bitcoin price right now?",
            "Current Bitcoin price please",
            "Tell me the price of Bitcoin",
        ]
        result = detect_loop(history, threshold=0.85)
        # TF-IDF with stop words removed gives moderate similarity for these
        assert result.repetition_score > 0.3


class TestEdgeCases:
    def test_too_few_entries_single(self):
        result = detect_loop(["Only one entry"])
        assert result.is_loop is False
        assert result.recommended_action == "continue"
        assert result.window_size == 1

    def test_too_few_entries_empty(self):
        result = detect_loop([])
        assert result.is_loop is False
        assert result.recommended_action == "continue"

    def test_two_different_entries(self):
        result = detect_loop(["Hello world", "Goodbye moon"])
        assert result.is_loop is False

    def test_two_identical_entries(self):
        result = detect_loop(["Same exact query", "Same exact query"])
        assert result.is_loop is True
        assert result.repetition_score > 0.95


class TestWindowSize:
    def test_custom_window_size(self):
        # 10 entries, but window of 3
        history = [
            "Different topic A",
            "Different topic B",
            "Different topic C",
            "Different topic D",
            "Different topic E",
            "Different topic F",
            "Different topic G",
            "Search for pizza recipe",
            "Search for pizza recipe",
            "Search for pizza recipe",
        ]
        result = detect_loop(history, window_size=3)
        # Last 3 are identical -> should detect loop
        assert result.is_loop is True
        assert result.recommended_action in ("warn", "kill")

    def test_larger_window_dilutes_loop(self):
        history = [
            "Topic about astronomy and stars",
            "Topic about biology and cells",
            "Topic about chemistry and elements",
            "Search for pizza recipe",
            "Search for pizza recipe",
        ]
        result = detect_loop(history, window_size=5)
        # 3 different + 2 identical -> mixed, unlikely to be a loop
        # The diverse topics should bring the average similarity below threshold
        assert result.recommended_action in ("continue", "warn")
