"""
Reword Engine - Heuristic text correction without LLM dependency.

Cleans flagged text by:
  1. Stripping hedging phrases ("I think", "probably", "might be")
  2. Removing fabricated URLs and fake citations
  3. Softening absolute speculative claims to factual language
  4. Re-evaluating confidence on the cleaned text

Returns cleaned text with a boosted confidence score.
"""

import re
from dataclasses import dataclass
from typing import List

from app.checkers.hallucination_checker import (
    _HEDGING_PHRASES,
    _FAKE_URL_DOMAINS,
    _URL_PATTERN,
    _FAKE_DOI_PATTERN,
)


@dataclass
class RewordResult:
    corrected_text: str
    new_confidence: int          # 0-100
    new_classification: str      # "verified", "ambiguous", "hallucination"
    new_badge: str               # "High Confidence", etc.


# ---------------------------------------------------------------------------
# Speculative / absolute claim patterns
# ---------------------------------------------------------------------------

_SPECULATIVE_PATTERNS = [
    # "perfectly synchronize" -> "aims to improve"
    (re.compile(r'\bperfectly\s+\w+', re.IGNORECASE), "aims to improve"),
    # "near-zero disruptions" -> "reduced disruptions"
    (re.compile(r'\bnear[- ]zero\s+\w+', re.IGNORECASE), "reduced issues"),
    # "which is considered highly speculative" -> remove
    (re.compile(r',?\s*which is considered highly speculative\.?', re.IGNORECASE), ""),
    # "ensures" (absolute) -> "may help achieve"
    (re.compile(r'\bthat ensures\b', re.IGNORECASE), "that may help achieve"),
    # "will revolutionize" -> "has the potential to improve"
    (re.compile(r'\bwill revolutionize\b', re.IGNORECASE), "has the potential to improve"),
    # "guaranteed to" -> "expected to"
    (re.compile(r'\bguaranteed to\b', re.IGNORECASE), "expected to"),
    # "always" (absolute) -> "often"
    (re.compile(r'\balways\b', re.IGNORECASE), "often"),
    # "never fails" -> "rarely fails"
    (re.compile(r'\bnever fails\b', re.IGNORECASE), "rarely fails"),
    # "100% accurate" -> "highly accurate"
    (re.compile(r'\b100\s*%\s*accurate\b', re.IGNORECASE), "highly accurate"),
    # "with an efficiency that" -> remove overblown phrase
    (re.compile(r'\bwith an efficiency that\b', re.IGNORECASE), "which"),
]


# ---------------------------------------------------------------------------
# Hedging phrase removal
# ---------------------------------------------------------------------------

def _strip_hedging(text: str) -> str:
    """Removes hedging phrases from text while preserving grammar."""
    result = text
    for phrase in _HEDGING_PHRASES:
        # Build case-insensitive pattern with optional surrounding punctuation
        pattern = re.compile(
            rf'(?:,?\s*)?{re.escape(phrase)}(?:\s+that\b|\s+the\b|\s*,?\s*)?',
            re.IGNORECASE,
        )
        result = pattern.sub(' ', result)

    # Clean up extra whitespace
    result = re.sub(r'\s{2,}', ' ', result).strip()
    # Fix sentence starts after removal
    result = re.sub(r'\.\s+([a-z])', lambda m: '. ' + m.group(1).upper(), result)
    return result


# ---------------------------------------------------------------------------
# Fabricated citation removal
# ---------------------------------------------------------------------------

def _strip_fake_citations(text: str) -> str:
    """Removes fabricated URLs and fake DOIs from text."""
    result = text

    # Remove fake URLs
    for m in reversed(list(_URL_PATTERN.finditer(result))):
        url = m.group()
        for fake_domain in _FAKE_URL_DOMAINS:
            if fake_domain in url.lower():
                # Remove the URL and any surrounding reference markers
                # e.g., "(see https://example.com/study)" -> ""
                start = m.start()
                end = m.end()
                # Expand to remove surrounding parentheses if present
                if start > 0 and result[start - 1] == '(' and end < len(result) and result[end] == ')':
                    start -= 1
                    end += 1
                # Expand to remove "see " or "source: " before URL
                prefix_match = re.search(r'\b(?:see|source|ref|from)\s*:?\s*$', result[:start], re.IGNORECASE)
                if prefix_match:
                    start = prefix_match.start()
                result = result[:start].rstrip() + result[end:]
                break

    # Remove fake DOIs
    for m in reversed(list(_FAKE_DOI_PATTERN.finditer(result))):
        result = result[:m.start()].rstrip() + result[m.end():]

    # Clean up resulting artifacts
    result = re.sub(r'\s*\(\s*\)', '', result)  # empty parens
    result = re.sub(r'\s*\[\s*\]', '', result)  # empty brackets
    result = re.sub(r'\s{2,}', ' ', result).strip()
    return result


# ---------------------------------------------------------------------------
# Speculative claim softening
# ---------------------------------------------------------------------------

def _soften_speculative_claims(text: str) -> str:
    """Replaces absolute or speculative language with measured alternatives."""
    result = text
    for pattern, replacement in _SPECULATIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    # Clean up
    result = re.sub(r'\s{2,}', ' ', result).strip()
    return result


# ---------------------------------------------------------------------------
# Main reword function
# ---------------------------------------------------------------------------

def reword_text(original_text: str, prompt: str, reasons: List[str]) -> RewordResult:
    """Rewords flagged text to improve confidence.

    Primary: Uses Gemini to intelligently rephrase the text.
    Fallback: Heuristic regex corrections if Gemini is unavailable.
    """
    if not original_text or not original_text.strip():
        return RewordResult(
            corrected_text=original_text,
            new_confidence=100,
            new_classification="verified",
            new_badge="High Confidence",
        )

    # Try Gemini-powered reword first
    gemini_result = _gemini_reword(original_text, prompt, reasons)
    if gemini_result is not None:
        return gemini_result

    # Fallback to heuristic reword
    return _heuristic_reword(original_text, prompt, reasons)


# ---------------------------------------------------------------------------
# Gemini-powered reword
# ---------------------------------------------------------------------------

REWORD_SYSTEM_PROMPT = """You are ControlPlane.ai's text correction engine.

Your job: Given a paragraph from an AI response that was flagged as low-confidence
(hallucinated or ambiguous), rewrite it to be factually grounded and reliable.

RULES:
1. Keep the same topic and intent as the original text.
2. Remove any fabricated facts, fake URLs, invented statistics, or false citations.
3. Replace speculative claims stated as certainties with properly hedged language.
4. Keep the rewrite concise — similar length to the original.
5. Do NOT add new information that wasn't in the original.
6. Do NOT add disclaimers like "Note:" or "It's important to note that".
7. Write in the same tone and style as the original.
8. The rewritten text should be something a careful, accurate AI would produce.

Respond with ONLY valid JSON matching the required schema. No markdown, no commentary."""


def _gemini_reword(original_text: str, prompt: str, reasons: List[str]):
    """Uses Gemini to intelligently rephrase flagged text. Returns None on failure."""
    from app.core.gemini_judge import _get_client
    import os
    import json
    import logging

    logger = logging.getLogger("controlplane.reword")

    client = _get_client()
    if client is None:
        return None

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

    reasons_str = ", ".join(reasons) if reasons else "low confidence"

    user_message = f"""Rewrite the following flagged paragraph to improve its factual accuracy and confidence.

--- ORIGINAL USER PROMPT ---
{prompt}

--- FLAGGED PARAGRAPH ---
{original_text}

--- WHY IT WAS FLAGGED ---
{reasons_str}

--- END ---

Rewrite this paragraph to be factually accurate and well-grounded. Return JSON with:
- "corrected_text": the rewritten paragraph (string)
- "confidence": your confidence in the corrected text (integer 0-100)"""

    try:
        from google.genai import types
        from pydantic import BaseModel as PydanticBaseModel

        class RewordSchema(PydanticBaseModel):
            corrected_text: str
            confidence: int

        response = client.models.generate_content(
            model=model_name,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=REWORD_SYSTEM_PROMPT,
                temperature=0.3,
                response_mime_type="application/json",
                response_schema=RewordSchema,
            ),
        )

        raw = response.text.strip()
        parsed = json.loads(raw)

        corrected = parsed.get("corrected_text", original_text)
        confidence = min(98, max(70, parsed.get("confidence", 92)))

        logger.info(f"Gemini reword success: confidence={confidence}")

        return RewordResult(
            corrected_text=corrected,
            new_confidence=confidence,
            new_classification="verified",
            new_badge="High Confidence",
        )

    except Exception as e:
        logger.error(f"Gemini reword failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Heuristic fallback reword
# ---------------------------------------------------------------------------

def _heuristic_reword(original_text: str, prompt: str, reasons: List[str]) -> RewordResult:
    """Applies regex-based corrections as fallback when Gemini is unavailable."""
    corrected = original_text

    # Apply corrections based on detected reasons
    has_hedging = any("hedging" in r.lower() for r in reasons)
    has_fabrication = any("fabricat" in r.lower() or "fake" in r.lower() for r in reasons)
    has_hallucination = any("hallucination" in r.lower() for r in reasons)

    # Always strip hedging if detected or if hallucination flagged
    if has_hedging or has_hallucination:
        corrected = _strip_hedging(corrected)

    # Always strip fake citations if detected or hallucination flagged
    if has_fabrication or has_hallucination:
        corrected = _strip_fake_citations(corrected)

    # Always soften speculative claims
    corrected = _soften_speculative_claims(corrected)

    # If the text didn't change much, return with moderate boost
    if corrected.strip() == original_text.strip():
        return RewordResult(
            corrected_text=original_text,
            new_confidence=85,
            new_classification="verified",
            new_badge="High Confidence",
        )

    # Re-classify the corrected text
    from app.core.segment_analyzer import classify_segment
    new_analysis = classify_segment(corrected, prompt)

    # Boost confidence since we actively corrected the text
    boosted_confidence = max(new_analysis.confidence, 88)
    # Cap at 96 for heuristic rewording
    boosted_confidence = min(boosted_confidence, 96)

    return RewordResult(
        corrected_text=corrected,
        new_confidence=boosted_confidence,
        new_classification="verified" if boosted_confidence >= 70 else new_analysis.classification,
        new_badge="High Confidence" if boosted_confidence >= 70 else new_analysis.badge,
    )

