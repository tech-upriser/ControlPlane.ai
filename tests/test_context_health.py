"""Tests for Context Health module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.checkers.context_health import (
    calculate_health, calculate_cost_metrics, generate_fork_summary,
)


class TestHealthScoring:
    def test_fresh_session(self):
        result = calculate_health(turn_count=3, cumulative_tokens=500, error_count=0, recent_scores=[])
        assert result.score > 90
        assert result.is_degraded is False
        assert result.brain_rot_detected is False

    def test_moderate_session(self):
        result = calculate_health(turn_count=20, cumulative_tokens=15000, error_count=1, recent_scores=[])
        # turn_penalty = (20-10)*2 = 20, token_penalty = 15, error_penalty = 15 -> score = 50
        assert 40 < result.score < 70

    def test_heavily_degraded(self):
        result = calculate_health(turn_count=50, cumulative_tokens=80000, error_count=5, recent_scores=[])
        assert result.score == 0  # Penalties exceed 100
        assert result.is_degraded is True

    def test_penalties_breakdown(self):
        result = calculate_health(turn_count=15, cumulative_tokens=5000, error_count=2, recent_scores=[])
        # turn_penalty = (15-10)*2 = 10, token_penalty = 5, error_penalty = 30
        # score = 100 - 45 = 55
        assert abs(result.score - 55.0) < 0.01
        assert result.details["turn_penalty"] == 10
        assert result.details["token_penalty"] == 5
        assert result.details["error_penalty"] == 30

    def test_no_turn_penalty_under_10(self):
        result = calculate_health(turn_count=5, cumulative_tokens=0, error_count=0, recent_scores=[])
        assert result.details["turn_penalty"] == 0
        assert result.score == 100.0


class TestBrainRotDetection:
    def test_brain_rot_detected(self):
        # 3 out of 5 recent scores are below 50
        recent = [30, 40, 25, 60, 35]
        result = calculate_health(turn_count=35, cumulative_tokens=50000, error_count=4, recent_scores=recent)
        assert result.brain_rot_detected is True

    def test_no_brain_rot(self):
        recent = [60, 70, 55, 80, 65]
        result = calculate_health(turn_count=10, cumulative_tokens=1000, error_count=0, recent_scores=recent)
        assert result.brain_rot_detected is False

    def test_brain_rot_exactly_3_below(self):
        recent = [45, 49, 50, 48, 80]
        result = calculate_health(turn_count=10, cumulative_tokens=1000, error_count=0, recent_scores=recent)
        # 45, 49, 48 are < 50 -> 3/5 -> brain rot
        assert result.brain_rot_detected is True

    def test_too_few_scores_no_brain_rot(self):
        recent = [30, 20]
        result = calculate_health(turn_count=10, cumulative_tokens=1000, error_count=0, recent_scores=recent)
        # Need at least 5 scores
        assert result.brain_rot_detected is False


class TestForkRecommendation:
    def test_fork_when_degraded(self):
        result = calculate_health(turn_count=50, cumulative_tokens=80000, error_count=5, recent_scores=[])
        assert result.fork_recommendation is True

    def test_no_fork_when_healthy(self):
        result = calculate_health(turn_count=3, cumulative_tokens=500, error_count=0, recent_scores=[])
        assert result.fork_recommendation is False


class TestCostMetrics:
    def test_efficient_session(self):
        result = calculate_cost_metrics(total_tokens=1000, loop_tokens=0, model="gpt-4o")
        assert result.cost_rating == "efficient"
        assert result.context_utilization_pct == 100.0
        assert result.tokens_wasted_on_loops == 0
        assert result.estimated_cost_usd > 0

    def test_wasteful_session(self):
        result = calculate_cost_metrics(total_tokens=50000, loop_tokens=30000, model="gpt-4o")
        assert result.cost_rating == "wasteful"
        # utilization = (50000-30000)/50000 = 40%
        assert result.context_utilization_pct == 40.0

    def test_moderate_session(self):
        result = calculate_cost_metrics(total_tokens=10000, loop_tokens=3000, model="gpt-4o")
        # utilization = 7000/10000 = 70%
        assert result.cost_rating == "moderate"

    def test_default_pricing(self):
        # Unknown model should use default pricing
        result = calculate_cost_metrics(total_tokens=1000, loop_tokens=0, model="unknown-model")
        assert result.estimated_cost_usd > 0

    def test_zero_tokens(self):
        result = calculate_cost_metrics(total_tokens=0, loop_tokens=0)
        assert result.estimated_cost_usd == 0
        assert result.context_utilization_pct == 100.0


class TestForkSummary:
    def test_basic_fork(self):
        summary = generate_fork_summary(
            session_facts=["User wants X"],
            key_decisions=["Chose Y"]
        )
        assert "verified_facts" in summary
        assert "key_decisions" in summary
        assert summary["verified_facts"] == ["User wants X"]
        assert summary["key_decisions"] == ["Chose Y"]

    def test_empty_fork(self):
        summary = generate_fork_summary(session_facts=[], key_decisions=[])
        assert summary["verified_facts"] == []
        assert summary["key_decisions"] == []

    def test_fork_includes_reason(self):
        summary = generate_fork_summary(session_facts=["fact"], key_decisions=["decision"])
        assert "fork_reason" in summary
