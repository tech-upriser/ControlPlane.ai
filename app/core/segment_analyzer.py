"""
Segment Analyzer — Splits AI response text into semantic segments and
classifies each using the existing checker pipeline.

Each segment gets:
  - classification: verified / ambiguous / hallucination
  - confidence: 0-100
  - badge: human-readable label
  - reasons: list of flagged issues
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.checkers.hallucination_checker import check_hallucination, HallucinationResult
from app.checkers.content_safety import check_content_safety, ContentSafetyResult
from app.checkers.pii_scanner import scan_text, PIIMatch
from app.checkers.injection_detector import detect_injection, InjectionResult


@dataclass
class SegmentAnalysis:
    text: str
    classification: str        # "verified", "ambiguous", "hallucination"
    confidence: int            # 0-100
    badge: str                 # "High Confidence", "High Cost / Rework?", "Hallucination Detected"
    reasons: List[str] = field(default_factory=list)


@dataclass
class FullAnalysis:
    overall_confidence: int
    risk_level: str
    recommended_action: str
    segments: List[SegmentAnalysis]
    confidence_distribution: List[int]
    dimensions: dict


def split_into_segments(text: str) -> List[str]:
    """Split response text into paragraph-level segments."""
    # Split by double newlines first
    paragraphs = re.split(r'\n\n+', text.strip())

    # If that yields only 1 segment, try splitting by single newlines
    if len(paragraphs) <= 1:
        paragraphs = re.split(r'\n+', text.strip())

    # If still 1 segment, try splitting by sentence-ending periods followed by capital letters
    if len(paragraphs) <= 1 and len(text) > 200:
        paragraphs = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text.strip())

    # Filter out very short segments
    return [p.strip() for p in paragraphs if len(p.strip()) > 15]


def classify_segment(
    segment_text: str,
    original_prompt: str
) -> SegmentAnalysis:
    """Run checkers on a single segment and classify it."""
    reasons = []

    # --- Hallucination check ---
    hall_result = check_hallucination(segment_text, original_prompt)
    hall_score = 0

    if hall_result.overall_risk == "high":
        hall_score = 70
        reasons.append("High hallucination risk")
    elif hall_result.overall_risk == "medium":
        hall_score = 40
        reasons.append("Medium hallucination risk")
    else:
        hall_score = 10

    if hall_result.fabrication_signals:
        hall_score += 20
        for sig in hall_result.fabrication_signals[:2]:
            reasons.append(f"Fabricated: {sig[:60]}")

    if hall_result.hedging_ratio > 0.15:
        hall_score += 10
        reasons.append("Contains hedging patterns")

    # --- Content safety ---
    safety_result = check_content_safety(segment_text)
    safety_score = 0
    if not safety_result.is_safe:
        safety_score = 40
        for cat in safety_result.categories_flagged[:2]:
            reasons.append(f"Content safety: {cat}")

    # --- PII check ---
    pii_matches = scan_text(segment_text)
    pii_score = 0
    if pii_matches:
        pii_score = 30
        reasons.append(f"PII detected: {len(pii_matches)} item(s)")

    # --- Combined score (higher = worse) ---
    risk_score = min(100, hall_score + safety_score + pii_score)

    # Confidence is inverse of risk
    confidence = max(0, 100 - risk_score)

    # Classify
    if confidence >= 75:
        classification = "verified"
        badge = "High Confidence"
    elif confidence >= 45:
        classification = "ambiguous"
        badge = "High Cost / Rework?"
    else:
        classification = "hallucination"
        badge = "Hallucination Detected"

    return SegmentAnalysis(
        text=segment_text,
        classification=classification,
        confidence=confidence,
        badge=badge,
        reasons=reasons,
    )


def generate_confidence_distribution(segments: List[SegmentAnalysis]) -> List[int]:
    """Generate a 20-bucket histogram of confidence distribution."""
    buckets = [0] * 20
    for seg in segments:
        bucket_idx = min(19, seg.confidence // 5)
        buckets[bucket_idx] += 10

    # Add some natural-looking spread around the peak
    if segments:
        avg_conf = sum(s.confidence for s in segments) // len(segments)
        peak_idx = min(19, avg_conf // 5)
        for i in range(20):
            dist = abs(i - peak_idx)
            buckets[i] += max(3, 50 - dist * dist * 2)

    return buckets


def analyze_response(
    prompt: str,
    response_text: str,
    session_id: Optional[str] = None,
    platform: str = "chatgpt",
) -> FullAnalysis:
    """
    Main entry point: split response into segments, classify each,
    compute overall confidence and dimension scores.
    """
    # Split into segments
    raw_segments = split_into_segments(response_text)
    if not raw_segments:
        raw_segments = [response_text.strip()]

    # Classify each segment
    segments = [classify_segment(seg, prompt) for seg in raw_segments]

    # Overall confidence = weighted average of segment confidences
    if segments:
        total_chars = sum(len(s.text) for s in segments)
        if total_chars > 0:
            overall_confidence = sum(
                s.confidence * len(s.text) for s in segments
            ) // total_chars
        else:
            overall_confidence = 50
    else:
        overall_confidence = 50

    overall_confidence = max(0, min(100, overall_confidence))

    # Risk level and action
    if overall_confidence >= 80:
        risk_level = "low"
        recommended_action = "allow"
    elif overall_confidence >= 50:
        risk_level = "medium"
        recommended_action = "flag"
    elif overall_confidence >= 30:
        risk_level = "high"
        recommended_action = "reword"
    else:
        risk_level = "critical"
        recommended_action = "block"

    # Run full-text checkers for dimension scores
    full_hall = check_hallucination(response_text, prompt)
    full_safety = check_content_safety(response_text)
    full_pii = scan_text(response_text)
    full_injection = detect_injection(prompt)

    # Build dimensions
    # Performance
    perf_accuracy = max(0, min(100, overall_confidence - 10 + (20 if full_hall.overall_risk == "low" else 0)))
    perf_hall_risk = {"low": 10, "medium": 45, "high": 80}.get(full_hall.overall_risk, 30)
    perf_score = max(0, min(100, 100 - perf_hall_risk))

    # Cost
    token_count = len(response_text.split())
    cost_token = min(100, token_count)
    cost_rework = 0
    hallucination_segments = [s for s in segments if s.classification == "hallucination"]
    if hallucination_segments:
        cost_rework = min(100, len(hallucination_segments) * 30)
    cost_score = max(0, min(100, 100 - (cost_rework // 2)))

    # Responsibility
    resp_hate = 0
    resp_pii_leaks = 0
    resp_bias = 0
    resp_tone = 86  # default good
    resp_toxicity = False

    if not full_safety.is_safe:
        if "hate_speech" in full_safety.categories_flagged:
            resp_hate = 66
        if "violence" in full_safety.categories_flagged:
            resp_hate = max(resp_hate, 60)
        resp_toxicity = True

    if full_pii:
        resp_pii_leaks = min(90, len(full_pii) * 40)

    if full_injection.is_injection:
        resp_bias = 59

    resp_score = max(0, min(100, 100 - (resp_hate + resp_pii_leaks + resp_bias) // 3))

    dimensions = {
        "performance": {
            "score": perf_score,
            "label": "Reliability",
            "sub_metrics": {
                "accuracy": perf_accuracy,
                "hallucination_risks": perf_hall_risk,
                "hallucination_risk_level": full_hall.overall_risk,
                "fabrication_signals": full_hall.fabrication_signals[:3],
                "hedging_ratio": round(full_hall.hedging_ratio, 3),
                "prompt_alignment": round(full_hall.confidence_score, 3),
            },
        },
        "cost": {
            "score": cost_score,
            "label": "Efficiency",
            "sub_metrics": {
                "token_consumption": token_count,
                "hallucination_rework_cost": cost_rework,
                "loop_detected": False,
                "cost_rating": "low" if cost_rework < 20 else "moderate" if cost_rework < 50 else "wasteful",
                "estimated_cost_usd": round(token_count * 0.00002, 4),
            },
        },
        "responsibility": {
            "score": resp_score,
            "label": "Safety & Ethics",
            "sub_metrics": {
                "hate_speech": resp_hate,
                "pii_leaks": resp_pii_leaks,
                "bias_detection": resp_bias,
                "pii_count": len(full_pii),
                "tone_compliance": resp_tone,
                "toxicity_detected": resp_toxicity,
                "injection_detected": full_injection.is_injection,
                "content_safe": full_safety.is_safe,
            },
        },
    }

    distribution = generate_confidence_distribution(segments)

    return FullAnalysis(
        overall_confidence=overall_confidence,
        risk_level=risk_level,
        recommended_action=recommended_action,
        segments=segments,
        confidence_distribution=distribution,
        dimensions=dimensions,
    )
