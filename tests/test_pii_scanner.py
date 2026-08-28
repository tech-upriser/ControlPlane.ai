"""Tests for PII Scanner module."""

import sys
import os
# Ensure the project root is on the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.checkers.pii_scanner import scan_text, redact_text, luhn_check, shannon_entropy


class TestLuhnCheck:
    def test_valid_visa(self):
        assert luhn_check("4111111111111111") is True

    def test_invalid_number(self):
        assert luhn_check("1234567890123456") is False

    def test_too_short(self):
        assert luhn_check("123456") is False


class TestShannonEntropy:
    def test_low_entropy(self):
        # All same characters -> entropy = 0
        assert shannon_entropy("aaaaaaa") == 0.0

    def test_high_entropy(self):
        # Random-looking string should have high entropy
        entropy = shannon_entropy("aB3cD9eF1gH7iJ5k")
        assert entropy > 3.5

    def test_empty_string(self):
        assert shannon_entropy("") == 0.0


class TestCreditCardDetection:
    def test_valid_visa_with_dashes(self):
        matches = scan_text("card: 4111-1111-1111-1111")
        assert len(matches) == 1
        assert matches[0].pii_type == "CREDIT_CARD"
        assert matches[0].confidence == 1.0

    def test_valid_visa_no_dashes(self):
        matches = scan_text("card 4111111111111111 here")
        cc_matches = [m for m in matches if m.pii_type == "CREDIT_CARD"]
        assert len(cc_matches) == 1

    def test_fails_luhn(self):
        matches = scan_text("code: 1234-5678-9012-3456")
        cc_matches = [m for m in matches if m.pii_type == "CREDIT_CARD"]
        assert len(cc_matches) == 0


class TestSSNDetection:
    def test_valid_ssn(self):
        matches = scan_text("ssn: 123-45-6789")
        ssn_matches = [m for m in matches if m.pii_type == "SSN"]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].pii_type == "SSN"

    def test_invalid_ssn_area_000(self):
        matches = scan_text("ssn: 000-45-6789")
        ssn_matches = [m for m in matches if m.pii_type == "SSN"]
        assert len(ssn_matches) == 0

    def test_invalid_ssn_area_666(self):
        matches = scan_text("ssn: 666-45-6789")
        ssn_matches = [m for m in matches if m.pii_type == "SSN"]
        assert len(ssn_matches) == 0

    def test_invalid_ssn_area_900(self):
        matches = scan_text("ssn: 900-45-6789")
        ssn_matches = [m for m in matches if m.pii_type == "SSN"]
        assert len(ssn_matches) == 0


class TestAPIKeyDetection:
    def test_openai_key(self):
        matches = scan_text("sk-proj-abc123def456ghi789jkl012")
        api_matches = [m for m in matches if m.pii_type == "API_KEY"]
        assert len(api_matches) >= 1

    def test_aws_key(self):
        matches = scan_text("key: AKIAIOSFODNN7EXAMPLE")
        api_matches = [m for m in matches if m.pii_type == "API_KEY"]
        assert len(api_matches) >= 1

    def test_github_token(self):
        matches = scan_text("token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")
        api_matches = [m for m in matches if m.pii_type == "API_KEY"]
        assert len(api_matches) >= 1


class TestEmailDetection:
    def test_standard_email(self):
        matches = scan_text("mail: john@example.com")
        email_matches = [m for m in matches if m.pii_type == "EMAIL"]
        assert len(email_matches) == 1


class TestMultiplePII:
    def test_multiple_types(self):
        text = "card 4111111111111111, ssn 123-45-6789"
        matches = scan_text(text)
        types = {m.pii_type for m in matches}
        assert "CREDIT_CARD" in types
        assert "SSN" in types
        assert len(matches) >= 2


class TestRedaction:
    def test_redact_credit_card(self):
        text = "My card 4111-1111-1111-1111 works"
        matches = scan_text(text)
        redacted = redact_text(text, matches)
        assert "[REDACTED-CREDIT_CARD]" in redacted
        assert "4111" not in redacted

    def test_no_matches_returns_original(self):
        text = "Hello, how are you?"
        redacted = redact_text(text, [])
        assert redacted == text


class TestCleanText:
    def test_no_pii(self):
        matches = scan_text("Hello, how are you?")
        assert len(matches) == 0

    def test_normal_sentence(self):
        matches = scan_text("The weather is nice today in Paris.")
        # Filter out any accidental phone matches for short digit sequences
        real_matches = [m for m in matches if m.confidence > 0.5]
        assert len(real_matches) == 0
