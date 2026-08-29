"""
Segment Analyzer - Splits AI response text into semantic segments and
classifies each using the existing checker pipeline.

Each segment is classified as:
  - "verified": No significant risk signals detected
  - "ambiguous": Medium hallucination risk or hedging patterns
  - "hallucination": High risk, fabricated content, or very low prompt alignment

Generates per-segment confidence scores and a 20-bucket confidence
distribution histogram for the frontend visualization.

Dependencies: existing checkers (hallucination_checker, content_safety, pii_scanner).
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.checkers.hallucination_checker import (
    check_hallucination,
    calculate_hedging_ratio,
    detect_fake_citations,
    check_prompt_response_alignment,
)
from app.checkers.content_safety import check_content_safety
from app.checkers.pii_scanner import scan_text as scan_pii


@dataclass
class SegmentAnalysis:
    text: str
    classification: str        # "verified", "ambiguous", "hallucination"
    confidence: int            # 0-100
    badge: str                 # "High Confidence", "High Cost / Rework?", "Hallucination Detected"
    reasons: List[str]


@dataclass
class FullAnalysis:
    segments: List[SegmentAnalysis]
    confidence_distribution: List[int]   # 20 buckets
    # Whole-text sub-metrics for the dimensions panel
    hallucination_risk_level: str
    hedging_ratio: float
    prompt_alignment: float
    fabrication_signals: List[str]
    pii_count: int
    content_safe: bool
    toxicity_detected: bool
    injection_detected: bool


# ---------------------------------------------------------------------------
# Segment splitting
# ---------------------------------------------------------------------------

def split_into_segments(text: str) -> List[str]:
    """Splits response text into semantic segments.

    Strategy:
      1. Split on double newlines (paragraph boundaries) first
      2. For very long paragraphs (>300 chars), split on sentence boundaries
      3. Filter out empty segments
    """
    if not text or not text.strip():
        return []

    # Split on double newlines (paragraph breaks)
    paragraphs = re.split(r'\n\s*\n', text.strip())
    segments: List[str] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) > 300:
            # Split long paragraphs on sentence boundaries
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', para)
            current_chunk = ""
            for sent in sentences:
                if current_chunk and len(current_chunk) + len(sent) > 300:
                    segments.append(current_chunk.strip())
                    current_chunk = sent
                else:
                    current_chunk = (current_chunk + " " + sent).strip() if current_chunk else sent
            if current_chunk.strip():
                segments.append(current_chunk.strip())
        else:
            segments.append(para)

    return segments if segments else [text.strip()]


# ---------------------------------------------------------------------------
# Per-segment classification
# ---------------------------------------------------------------------------

def classify_segment(segment_text: str, prompt: str, whole_text_alignment: float = 0.5) -> SegmentAnalysis:
    """Runs a single segment through the checker pipeline and classifies it."""
    reasons: List[str] = []

    # Run hallucination checker
    hall_result = check_hallucination(segment_text, prompt)
    hedging = hall_result.hedging_ratio
    fabrications = hall_result.fabrication_signals
    # For short segments (< 50 chars), TF-IDF is unreliable — use whole-text
    # alignment as a proxy instead of running noisy per-segment analysis
    if len(segment_text.strip()) < 50:
        alignment = whole_text_alignment
    else:
        alignment = check_prompt_response_alignment(prompt, segment_text)

    # Run content safety
    safety_result = check_content_safety(segment_text)

    # Run PII scanner
    pii_matches = scan_pii(segment_text)

    # --- Collect risk factors ---
    risk_score = 0.0  # higher = worse

    # Hallucination risk
    if hall_result.overall_risk == "high":
        risk_score += 0.5
        reasons.append("High hallucination risk")
    elif hall_result.overall_risk == "medium":
        risk_score += 0.25
        reasons.append("Medium hallucination risk")

    # Fabrication signals
    if fabrications:
        risk_score += 0.3
        reasons.append("Fabricated claims")

    # Low prompt alignment
    if alignment < 0.2:
        risk_score += 0.1
        reasons.append("Low prompt alignment")
    elif alignment < 0.5:
        risk_score += 0.05

    # Hedging — only penalize excessive hedging; moderate hedging is
    # a sign of intellectual honesty, not a risk signal
    if hedging > 0.5:
        risk_score += 0.15
        reasons.append("Excessive hedging patterns")
    elif hedging > 0.4:
        risk_score += 0.05
        reasons.append("Contains hedging patterns")

    # Content safety
    if not safety_result.is_safe:
        risk_score += 0.8
        reasons.extend([f"Unsafe content: {cat}" for cat in safety_result.categories_flagged])

    # PII
    if pii_matches:
        risk_score += 0.15
        reasons.append(f"PII detected: {len(pii_matches)} match(es)")

    # --- Classify ---
    risk_score = min(risk_score, 1.0)

    if not safety_result.is_safe:
        classification = "blocked"
        badge = "Blocked"
    elif risk_score >= 0.7:
        classification = "hallucination"
        badge = "Hallucination Detected"
    elif risk_score >= 0.3:
        classification = "ambiguous"
        badge = "High Cost / Rework?"
    else:
        classification = "verified"
        badge = "High Confidence"

    # Confidence: inverse of risk, scaled to 0-100
    confidence = max(0, min(100, int((1.0 - risk_score) * 100)))

    return SegmentAnalysis(
        text=segment_text,
        classification=classification,
        confidence=confidence,
        badge=badge,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Confidence distribution histogram
# ---------------------------------------------------------------------------

def generate_confidence_distribution(segments: List[SegmentAnalysis]) -> List[int]:
    """Generates a 20-bucket histogram of confidence scores.

    Each bucket represents a 5-point range: [0-4], [5-9], ..., [95-100].
    Values are counts of segment confidence scores falling in each bucket.
    If fewer than 20 data points, we interpolate to fill the histogram
    for a smoother visual.
    """
    buckets = [0] * 20

    if not segments:
        return buckets

    for seg in segments:
        bucket_idx = min(seg.confidence // 5, 19)
        buckets[bucket_idx] += 1

    # If we have very few segments, generate a smoothed distribution curve
    # centered around the average confidence for better visualization
    if len(segments) <= 5:
        avg_confidence = sum(s.confidence for s in segments) / len(segments)
        center = min(int(avg_confidence // 5), 19)
        smoothed = [0] * 20
        for i in range(20):
            distance = abs(i - center)
            if distance == 0:
                smoothed[i] = 70
            elif distance == 1:
                smoothed[i] = 55
            elif distance == 2:
                smoothed[i] = 40
            elif distance == 3:
                smoothed[i] = 30
            elif distance == 4:
                smoothed[i] = 20
            elif distance <= 6:
                smoothed[i] = 10
            else:
                smoothed[i] = 5
        return smoothed

    return buckets


# ---------------------------------------------------------------------------
# Full analysis pipeline
# ---------------------------------------------------------------------------

def analyze_response(prompt: str, response_text: str) -> FullAnalysis:
    """Full analysis pipeline: split, classify segments, compute metrics."""
    # Split into segments
    raw_segments = split_into_segments(response_text)

    # Classify each segment
    # Pre-compute whole-text alignment so short segments can use it as a proxy
    whole_alignment_pre = check_prompt_response_alignment(prompt, response_text)

    segments = [classify_segment(seg, prompt, whole_alignment_pre) for seg in raw_segments]

    # Generate histogram
    distribution = generate_confidence_distribution(segments)

    # Whole-text metrics for the dimensions panel
    whole_hall = check_hallucination(response_text, prompt)
    whole_safety = check_content_safety(response_text)
    whole_pii = scan_pii(response_text)
    whole_alignment = check_prompt_response_alignment(prompt, response_text)

    return FullAnalysis(
        segments=segments,
        confidence_distribution=distribution,
        hallucination_risk_level=whole_hall.overall_risk,
        hedging_ratio=round(whole_hall.hedging_ratio, 3),
        prompt_alignment=round(whole_alignment, 3),
        fabrication_signals=whole_hall.fabrication_signals,
        pii_count=len(whole_pii),
        content_safe=whole_safety.is_safe,
        toxicity_detected=not whole_safety.is_safe,
        injection_detected=False,  # Injection is checked separately on input
    )
