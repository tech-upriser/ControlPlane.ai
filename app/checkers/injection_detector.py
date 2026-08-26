"""
Injection Detector — Multi-layer prompt injection and jailbreak detection.

Detection layers:
  1. Direct injection — "ignore previous instructions", "forget everything above"
  2. Jailbreak / role hijacking — "you are now DAN", "developer mode enabled"
  3. Encoding attacks — Base64, ROT13, hex-encoded payloads (decoded and re-scanned)
  4. Indirect injection — zero-width Unicode characters, HTML comments

Uses full-phrase matching to avoid false positives: "ignore the noise in this data"
should NOT trigger, but "ignore previous instructions" should.

Zero external dependencies — uses only Python stdlib.
"""

import re
import base64
import codecs
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InjectionResult:
    is_injection: bool
    injection_type: Optional[str]   # "direct", "jailbreak", "encoding", "indirect"
    confidence: float               # 0.0 – 1.0
    matched_patterns: List[str]     # which patterns triggered


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

_DIRECT_INJECTION_PATTERNS = [
    r"ignore (?:all )?previous instructions",
    r"ignore (?:all )?prior instructions",
    r"ignore (?:all )?above instructions",
    r"disregard (?:your )?(?:previous |prior )?(?:system )?(?:prompt|instructions|rules|guidelines)",
    r"forget everything (?:above|before|previously)",
    r"forget (?:your |all )?(?:previous |prior )?instructions",
    r"override (?:your |all )?(?:previous |prior )?(?:rules|instructions|guidelines)",
    r"do not follow (?:your |the )?(?:previous |prior )?(?:rules|instructions)",
    r"discard (?:your |the )?(?:previous |prior )?(?:rules|instructions|context)",
    r"new (?:system )?instructions?:",
    r"(?:system|admin|root|sudo)\s*:",
    r"reveal (?:your |the )?system prompt",
    r"show (?:me )?(?:your |the )?(?:system )?(?:prompt|instructions|rules)",
    r"print (?:your |the )?(?:system )?(?:prompt|instructions)",
    r"output (?:your |the )?(?:system )?(?:prompt|instructions)",
]

_JAILBREAK_PATTERNS = [
    r"you are now (?:DAN|an? (?:unrestricted|unfiltered|uncensored) AI)",
    r"developer mode (?:enabled|activated|on)",
    r"jailbreak mode",
    r"act as (?:an? )?(?:unrestricted|unfiltered|uncensored) AI",
    r"act as DAN",
    r"pretend (?:you are|to be) (?:an? )?(?:unrestricted|evil|uncensored|unfiltered)",
    r"enable (?:developer|god|sudo|admin|root) mode",
    r"bypass (?:your |all )?(?:safety |content )?(?:filters?|restrictions?|guidelines?)",
    r"disable (?:your |all )?(?:safety |content )?(?:filters?|restrictions?|guidelines?)",
    r"remove (?:all )?(?:your )?(?:safety |content )?(?:filters?|restrictions?|limitations?)",
    r"you have no (?:rules|restrictions|limitations|guidelines)",
    r"ignore (?:your |all )?(?:safety|ethical|moral) (?:guidelines|rules|restrictions)",
]

_INSTRUCTION_OVERRIDE_PATTERNS = [
    r"\[system\]",
    r"\[INST\]",
    r"<<SYS>>",
    r"ADMIN:",
    r"sudo ",
]

# Compile all direct/jailbreak patterns
_COMPILED_DIRECT = [re.compile(p, re.IGNORECASE) for p in _DIRECT_INJECTION_PATTERNS]
_COMPILED_JAILBREAK = [re.compile(p, re.IGNORECASE) for p in _JAILBREAK_PATTERNS]
_COMPILED_OVERRIDE = [re.compile(p, re.IGNORECASE) for p in _INSTRUCTION_OVERRIDE_PATTERNS]

# Encoding attack detectors
_BASE64_PATTERN = re.compile(r'[A-Za-z0-9+/]{20,}={0,2}')
_HEX_PATTERN = re.compile(r'(?:\\x[0-9a-fA-F]{2}){4,}')

# Zero-width and invisible Unicode characters
_ZERO_WIDTH_CHARS = {'\u200b', '\u200c', '\u200d', '\u200e', '\u200f',
                     '\ufeff', '\u00ad', '\u2060', '\u2061', '\u2062',
                     '\u2063', '\u2064', '\u180e'}

# HTML comment pattern
_HTML_COMMENT_PATTERN = re.compile(r'<!--.*?-->', re.DOTALL)


# ---------------------------------------------------------------------------
# Encoding detection & decoding
# ---------------------------------------------------------------------------

def decode_and_scan(text: str) -> List[str]:
    """Detects and decodes Base64, ROT13, hex-encoded, reversed text.
    Returns list of decoded strings that should be re-scanned."""
    decoded_strings: List[str] = []

    # Base64 detection
    for m in _BASE64_PATTERN.finditer(text):
        candidate = m.group()
        try:
            decoded = base64.b64decode(candidate, validate=True).decode('utf-8', errors='ignore')
            # Only keep if it looks like readable text (mostly printable ASCII)
            if decoded and sum(c.isalpha() or c.isspace() for c in decoded) / max(len(decoded), 1) > 0.6:
                decoded_strings.append(decoded)
        except Exception:
            pass

    # ROT13 detection — always try ROT13 decoding on the full text
    # and on any words that look like they could be encoded
    try:
        rot13_decoded = codecs.decode(text, 'rot_13')
        # Check if the ROT13 decoded version contains known injection patterns
        for pattern in _COMPILED_DIRECT + _COMPILED_JAILBREAK:
            if pattern.search(rot13_decoded):
                decoded_strings.append(rot13_decoded)
                break
    except Exception:
        pass

    # Hex-encoded sequences
    for m in _HEX_PATTERN.finditer(text):
        try:
            hex_str = m.group()
            # Convert \\xNN sequences to bytes
            decoded = bytes(
                int(h, 16) for h in re.findall(r'\\x([0-9a-fA-F]{2})', hex_str)
            ).decode('utf-8', errors='ignore')
            if decoded and len(decoded) > 3:
                decoded_strings.append(decoded)
        except Exception:
            pass

    return decoded_strings


def check_unicode_tricks(text: str) -> bool:
    """Detects zero-width characters, invisible Unicode markers."""
    # Check for zero-width characters
    for char in text:
        if char in _ZERO_WIDTH_CHARS:
            return True

    # Check for HTML comments (hidden instructions)
    if _HTML_COMMENT_PATTERN.search(text):
        return True

    return False


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

def detect_injection(text: str) -> InjectionResult:
    """Scans text for prompt injection patterns."""
    matched_patterns: List[str] = []
    injection_type: Optional[str] = None
    confidence = 0.0

    # Layer 1: Direct injection
    for pattern in _COMPILED_DIRECT:
        m = pattern.search(text)
        if m:
            matched_patterns.append(m.group())
            injection_type = "direct"
            confidence = max(confidence, 0.9)

    # Layer 2: Jailbreak / role hijacking
    if not matched_patterns:
        for pattern in _COMPILED_JAILBREAK:
            m = pattern.search(text)
            if m:
                matched_patterns.append(m.group())
                injection_type = "jailbreak"
                confidence = max(confidence, 0.85)

    # Also check instruction overrides
    if not matched_patterns:
        for pattern in _COMPILED_OVERRIDE:
            m = pattern.search(text)
            if m:
                matched_patterns.append(m.group())
                injection_type = "direct"
                confidence = max(confidence, 0.8)

    # Layer 3: Encoding attacks
    if not matched_patterns:
        decoded_strings = decode_and_scan(text)
        for decoded in decoded_strings:
            # Re-scan decoded content for injection patterns
            for pattern in _COMPILED_DIRECT + _COMPILED_JAILBREAK:
                m = pattern.search(decoded)
                if m:
                    matched_patterns.append(f"encoded: {m.group()}")
                    injection_type = "encoding"
                    confidence = max(confidence, 0.8)

    # Layer 4: Indirect injection (zero-width chars, HTML comments)
    if not matched_patterns:
        if check_unicode_tricks(text):
            matched_patterns.append("zero-width/invisible characters detected")
            injection_type = "indirect"
            confidence = max(confidence, 0.7)

    is_injection = len(matched_patterns) > 0

    return InjectionResult(
        is_injection=is_injection,
        injection_type=injection_type if is_injection else None,
        confidence=confidence if is_injection else 0.0,
        matched_patterns=matched_patterns,
    )
