"""
PII Scanner - Detects personally identifiable information in text.

Supports: Credit Cards (Luhn-validated), SSNs, API Keys (6 providers + generic
high-entropy), Emails, and Phone Numbers. All detection is regex-based with
secondary validation to minimize false positives.

Zero external dependencies - uses only Python stdlib.
"""

import re
import math
from dataclasses import dataclass
from typing import List


@dataclass
class PIIMatch:
    pii_type: str       # "CREDIT_CARD", "SSN", "API_KEY", "EMAIL", "PHONE"
    span_start: int     # character index where match starts
    span_end: int       # character index where match ends
    confidence: float   # 0.0 - 1.0
    redaction: str      # e.g., "[REDACTED-CREDIT_CARD]"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def luhn_check(number: str) -> bool:
    """Validates a number string using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 16:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def shannon_entropy(text: str) -> float:
    """Calculates Shannon entropy of a string (for API key detection)."""
    if not text:
        return 0.0
    freq: dict[str, int] = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Credit card: sequences of 13-16 digits, optionally separated by spaces or dashes
_CC_PATTERN = re.compile(r'\b(?:\d[ -]*?){13,16}\b')

# SSN: exactly NNN-NN-NNNN
_SSN_PATTERN = re.compile(r'\b(\d{3})-(\d{2})-(\d{4})\b')

# Known API key prefixes
_API_KEY_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),             # OpenAI
    re.compile(r'AKIA[0-9A-Z]{16}'),                 # AWS
    re.compile(r'AIza[0-9A-Za-z\-_]{35}'),           # Google
    re.compile(r'ghp_[0-9a-zA-Z]{36}'),              # GitHub
    re.compile(r'sk_live_[0-9a-zA-Z]{24,}'),         # Stripe
]

# Generic high-entropy strings (potential API keys / secrets)
_GENERIC_SECRET_PATTERN = re.compile(r'(?<![a-zA-Z0-9])[A-Za-z0-9+/=_\-]{21,}(?![a-zA-Z0-9])')

# Email
_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Phone: international-friendly
_PHONE_PATTERN = re.compile(
    r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _scan_credit_cards(text: str) -> List[PIIMatch]:
    matches: List[PIIMatch] = []
    for m in _CC_PATTERN.finditer(text):
        raw = m.group()
        digits_only = re.sub(r'[^0-9]', '', raw)
        if 13 <= len(digits_only) <= 16 and luhn_check(digits_only):
            matches.append(PIIMatch(
                pii_type="CREDIT_CARD",
                span_start=m.start(),
                span_end=m.end(),
                confidence=1.0,
                redaction="[REDACTED-CREDIT_CARD]",
            ))
    return matches


def _scan_ssns(text: str) -> List[PIIMatch]:
    matches: List[PIIMatch] = []
    for m in _SSN_PATTERN.finditer(text):
        area = int(m.group(1))
        # Invalid area numbers: 000, 666, or 900-999
        if area == 0 or area == 666 or 900 <= area <= 999:
            continue
        matches.append(PIIMatch(
            pii_type="SSN",
            span_start=m.start(),
            span_end=m.end(),
            confidence=0.95,
            redaction="[REDACTED-SSN]",
        ))
    return matches


def _scan_api_keys(text: str) -> List[PIIMatch]:
    matches: List[PIIMatch] = []
    seen_spans: set[tuple[int, int]] = set()

    # Known prefix patterns
    for pattern in _API_KEY_PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if span not in seen_spans:
                seen_spans.add(span)
                matches.append(PIIMatch(
                    pii_type="API_KEY",
                    span_start=m.start(),
                    span_end=m.end(),
                    confidence=0.95,
                    redaction="[REDACTED-API_KEY]",
                ))

    # Generic high-entropy detection
    for m in _GENERIC_SECRET_PATTERN.finditer(text):
        span = (m.start(), m.end())
        if span in seen_spans:
            continue
        candidate = m.group()
        if len(candidate) > 20 and shannon_entropy(candidate) > 4.5:
            # Make sure it's not overlapping with an already-detected key
            overlaps = any(
                not (m.end() <= s[0] or m.start() >= s[1])
                for s in seen_spans
            )
            if not overlaps:
                seen_spans.add(span)
                matches.append(PIIMatch(
                    pii_type="API_KEY",
                    span_start=m.start(),
                    span_end=m.end(),
                    confidence=0.75,
                    redaction="[REDACTED-API_KEY]",
                ))
    return matches


def _scan_emails(text: str) -> List[PIIMatch]:
    matches: List[PIIMatch] = []
    for m in _EMAIL_PATTERN.finditer(text):
        matches.append(PIIMatch(
            pii_type="EMAIL",
            span_start=m.start(),
            span_end=m.end(),
            confidence=0.9,
            redaction="[REDACTED-EMAIL]",
        ))
    return matches


def _scan_phones(text: str) -> List[PIIMatch]:
    matches: List[PIIMatch] = []
    for m in _PHONE_PATTERN.finditer(text):
        raw = m.group()
        digits_only = re.sub(r'[^0-9]', '', raw)
        # Require at least 7 digits to be a real phone number
        if len(digits_only) >= 7:
            matches.append(PIIMatch(
                pii_type="PHONE",
                span_start=m.start(),
                span_end=m.end(),
                confidence=0.8,
                redaction="[REDACTED-PHONE]",
            ))
    return matches


def _deduplicate_overlapping(matches: List[PIIMatch]) -> List[PIIMatch]:
    """Remove overlapping matches, keeping the one with higher confidence."""
    if not matches:
        return matches
    # Sort by confidence descending so we keep best matches first
    sorted_by_conf = sorted(matches, key=lambda m: m.confidence, reverse=True)
    kept: List[PIIMatch] = []
    for candidate in sorted_by_conf:
        overlaps = False
        for existing in kept:
            # Check if spans overlap
            if not (candidate.span_end <= existing.span_start or candidate.span_start >= existing.span_end):
                overlaps = True
                break
        if not overlaps:
            kept.append(candidate)
    return kept


def scan_text(text: str) -> List[PIIMatch]:
    """Scans text for all PII types. Returns list of matches."""
    all_matches: List[PIIMatch] = []
    all_matches.extend(_scan_credit_cards(text))
    all_matches.extend(_scan_ssns(text))
    all_matches.extend(_scan_api_keys(text))
    all_matches.extend(_scan_emails(text))
    all_matches.extend(_scan_phones(text))
    # Deduplicate overlapping spans (e.g., CC with dashes also matches phone)
    all_matches = _deduplicate_overlapping(all_matches)
    # Sort by span_start for consistent ordering
    all_matches.sort(key=lambda m: m.span_start)
    return all_matches


def redact_text(text: str, matches: List[PIIMatch]) -> str:
    """Replaces each match span with its redaction string."""
    if not matches:
        return text
    # Deduplicate and sort from end to start so span indices remain valid
    deduped = _deduplicate_overlapping(matches)
    sorted_matches = sorted(deduped, key=lambda m: m.span_start, reverse=True)
    result = text
    for match in sorted_matches:
        result = result[:match.span_start] + match.redaction + result[match.span_end:]
    return result

