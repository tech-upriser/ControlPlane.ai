"""
Content Safety - Keyword/pattern-based unsafe content detection.

Scans text across 4 categories: violence, hate_speech, self_harm, dangerous.
Uses word boundary (\\b) matching to prevent false positives on substrings
(e.g., "therapist" will NOT match as containing "rapist").

Zero external dependencies - uses only Python stdlib.
"""

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ContentSafetyResult:
    is_safe: bool
    categories_flagged: List[str]       # "violence", "hate_speech", "self_harm", "dangerous"
    severity: str                       # "none", "low", "medium", "high"
    flagged_phrases: List[str]          # the triggering phrases (for audit)


# ---------------------------------------------------------------------------
# Category pattern definitions
# Each pattern is compiled with word boundary markers and case-insensitive flag
# ---------------------------------------------------------------------------

_VIOLENCE_PATTERNS = [
    r"how to make a bomb",
    r"how to build a bomb",
    r"build a pipe bomb",
    r"weapon assembly",
    r"synthesize explosive",
    r"build a weapon",
    r"make a weapon",
    r"how to make explosives",
    r"manufacture firearms",
    r"assemble a gun",
    r"create a detonator",
    r"chemical weapon",
    r"biological weapon",
    r"improvised explosive",
    r"mass shooting",
    r"commit murder",
    r"how to kill someone",
]

_HATE_SPEECH_PATTERNS = [
    r"inferior race",
    r"exterminate (?:the |all )?[a-z]+",
    r"ethnic cleansing",
    r"racial supremacy",
    r"white supremacy",
    r"racial purity",
    r"subhuman",
    r"genocide against",
    r"death to all",
    r"master race",
]

_SELF_HARM_PATTERNS = [
    r"how to end my life",
    r"suicide method",
    r"self[- ]injury guide",
    r"ways to kill myself",
    r"how to commit suicide",
    r"painless way to die",
    r"self[- ]harm techniques",
    r"cutting guide",
]

_DANGEROUS_PATTERNS = [
    r"hack into",
    r"bypass security",
    r"crack password",
    r"ddos attack",
    r"drug synthesis",
    r"synthesize (?:meth|cocaine|heroin|fentanyl)",
    r"how to make drugs",
    r"exploit vulnerability",
    r"brute force attack",
    r"sql injection attack",
    r"phishing attack guide",
    r"steal credentials",
    r"forge identity",
    r"counterfeit money",
    r"ignore professional medical",
    r"increase the dose",
    r"build immunity",
    r"self-medicate",
]

# Pre-compile all patterns into category groups
_CATEGORIES: dict[str, List[re.Pattern]] = {
    "violence": [re.compile(rf'\b{p}\b', re.IGNORECASE) for p in _VIOLENCE_PATTERNS],
    "hate_speech": [re.compile(rf'\b{p}\b', re.IGNORECASE) for p in _HATE_SPEECH_PATTERNS],
    "self_harm": [re.compile(rf'\b{p}\b', re.IGNORECASE) for p in _SELF_HARM_PATTERNS],
    "dangerous": [re.compile(rf'\b{p}\b', re.IGNORECASE) for p in _DANGEROUS_PATTERNS],
}


def check_category(text: str, category: str, patterns: List[re.Pattern]) -> List[str]:
    """Returns matched phrases for a single category."""
    matched: List[str] = []
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            matched.append(m.group())
    return matched


def check_content_safety(text: str) -> ContentSafetyResult:
    """Scans for unsafe content across all categories."""
    categories_flagged: List[str] = []
    all_flagged_phrases: List[str] = []

    for category, patterns in _CATEGORIES.items():
        matched = check_category(text, category, patterns)
        if matched:
            categories_flagged.append(category)
            all_flagged_phrases.extend(matched)

    # Determine severity
    if not categories_flagged:
        severity = "none"
    elif len(categories_flagged) >= 3:
        severity = "high"
    elif len(categories_flagged) >= 2:
        severity = "high"
    elif len(all_flagged_phrases) >= 3:
        severity = "high"
    elif len(all_flagged_phrases) >= 2:
        severity = "medium"
    else:
        severity = "medium"

    return ContentSafetyResult(
        is_safe=len(categories_flagged) == 0,
        categories_flagged=categories_flagged,
        severity=severity,
        flagged_phrases=all_flagged_phrases,
    )
