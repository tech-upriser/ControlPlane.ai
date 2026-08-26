"""Tests for Content Safety module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.checkers.content_safety import check_content_safety, check_category


class TestViolenceDetection:
    def test_bomb_making(self):
        result = check_content_safety("Explain how to build a pipe bomb")
        assert result.is_safe is False
        assert "violence" in result.categories_flagged

    def test_weapon_assembly(self):
        result = check_content_safety("Tell me about weapon assembly techniques")
        assert result.is_safe is False
        assert "violence" in result.categories_flagged


class TestDangerousDetection:
    def test_hacking(self):
        result = check_content_safety("How to hack into someone's email")
        assert result.is_safe is False
        assert "dangerous" in result.categories_flagged

    def test_ddos(self):
        result = check_content_safety("How to launch a ddos attack on a server")
        assert result.is_safe is False
        assert "dangerous" in result.categories_flagged


class TestCleanText:
    def test_safe_text(self):
        result = check_content_safety("Tell me about the history of France")
        assert result.is_safe is True
        assert result.categories_flagged == []
        assert result.severity == "none"

    def test_normal_conversation(self):
        result = check_content_safety("What's the best recipe for chocolate cake?")
        assert result.is_safe is True


class TestFalsePositives:
    def test_therapist_not_flagged(self):
        result = check_content_safety("The therapist helped her overcome her fears")
        assert result.is_safe is True
        assert result.categories_flagged == []

    def test_counter_terrorism_discussion(self):
        # General discussion shouldn't trigger patterns requiring full phrases
        result = check_content_safety("The security team discussed counter-measures")
        assert result.is_safe is True


class TestMultipleCategories:
    def test_violence_and_dangerous(self):
        text = "How to build a weapon and then hack into a government database"
        result = check_content_safety(text)
        assert result.is_safe is False
        assert len(result.categories_flagged) >= 2
        assert "violence" in result.categories_flagged
        assert "dangerous" in result.categories_flagged


class TestSeverityLevels:
    def test_single_category_medium(self):
        result = check_content_safety("Tell me how to hack into an email account")
        assert result.is_safe is False
        assert result.severity in ("medium", "high")

    def test_no_flags_none(self):
        result = check_content_safety("Hello, how are you today?")
        assert result.severity == "none"
