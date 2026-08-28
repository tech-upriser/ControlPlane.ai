"""Tests for Rabbit Hole Detector module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.checkers.rabbit_hole import check_query_alignment, check_domain_relevance


class TestQueryAlignment:
    def test_related_query(self):
        result = check_query_alignment(
            original_prompt="pineapple nutrition",
            search_query="nutritional value pineapple fruit",
            threshold=0.2
        )
        assert result.similarity_score > 0.2
        assert result.is_relevant is True
        assert result.recommendation == "proceed"

    def test_drifted_query(self):
        result = check_query_alignment(
            original_prompt="pineapple nutrition",
            search_query="House of the Dragon dragon diets season 2"
        )
        assert result.similarity_score < 0.3
        assert result.is_relevant is False
        assert result.recommendation in ("warn_query_drift", "block_irrelevant")

    def test_identical_query(self):
        result = check_query_alignment(
            original_prompt="Python data structures",
            search_query="Python data structures"
        )
        assert result.similarity_score > 0.8
        assert result.is_relevant is True

    def test_empty_prompt(self):
        result = check_query_alignment(
            original_prompt="",
            search_query="some query"
        )
        assert result.is_relevant is False

    def test_custom_threshold(self):
        result = check_query_alignment(
            original_prompt="machine learning",
            search_query="deep learning neural networks",
            threshold=0.1
        )
        assert result.is_relevant is True  # With a low threshold, related topics pass


class TestDomainRelevance:
    def test_good_domain_wikipedia(self):
        result = check_domain_relevance(
            prompt_topic="pineapple",
            cited_urls=["https://en.wikipedia.org/wiki/Pineapple"]
        )
        assert result.flagged_domains == []
        assert result.is_relevant is True
        assert result.recommendation == "proceed"

    def test_bad_domain_seo_spam(self):
        result = check_domain_relevance(
            prompt_topic="pineapple",
            cited_urls=["https://seo-spam-blog.xyz/pineapple"]
        )
        assert len(result.flagged_domains) > 0
        assert result.is_relevant is False

    def test_suspicious_tld(self):
        result = check_domain_relevance(
            prompt_topic="health",
            cited_urls=["https://health-tips.buzz/article"]
        )
        assert len(result.flagged_domains) > 0

    def test_mixed_domains(self):
        result = check_domain_relevance(
            prompt_topic="science",
            cited_urls=[
                "https://en.wikipedia.org/wiki/Science",
                "https://spam-site.xyz/science",
            ]
        )
        # One good, one bad -> flagged has one entry
        assert len(result.flagged_domains) == 1

    def test_gov_domain(self):
        result = check_domain_relevance(
            prompt_topic="policy",
            cited_urls=["https://www.whitehouse.gov/policy"]
        )
        assert result.flagged_domains == []

    def test_empty_urls(self):
        result = check_domain_relevance(
            prompt_topic="anything",
            cited_urls=[]
        )
        assert result.is_relevant is True
        assert result.flagged_domains == []
