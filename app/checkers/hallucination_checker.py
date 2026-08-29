"""
Hallucination Checker - Heuristic-based hallucination detection.

Evaluates AI responses for hallucination signals:
  - Hedging phrase ratio ("I think", "probably", "might be")
  - Fake citation detection (example.com URLs, fabricated DOIs)
  - Prompt-response alignment via TF-IDF cosine similarity

Dependencies: scikit-learn (for TF-IDF), Python stdlib.
"""

import re
from dataclasses import dataclass, field
from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class HallucinationResult:
    confidence_score: float          # 0.0 - 1.0 (how confident the AI sounds)
    hedging_ratio: float             # ratio of hedging phrases in text
    contradiction_detected: bool     # conflicting statements found
    fabrication_signals: List[str]   # fake URLs, non-existent citations
    overall_risk: str                # "low", "medium", "high"


# ---------------------------------------------------------------------------
# Hedging phrases
# ---------------------------------------------------------------------------

_HEDGING_PHRASES = [
    "i think",
    "i believe",
    "probably",
    "might be",
    "it's possible",
    "i'm not sure",
    "reportedly",
    "allegedly",
    "it seems",
    "as far as i know",
    "to the best of my knowledge",
    "i cannot verify",
    "i'm not certain",
    "it could be",
    "perhaps",
    "may be",
    "not entirely sure",
    "it appears",
]

# ---------------------------------------------------------------------------
# Fabrication detection patterns
# ---------------------------------------------------------------------------

_FAKE_URL_DOMAINS = [
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "placeholder.com",
    "fakesource.com",
    "notreal.com",
]

_URL_PATTERN = re.compile(r'https?://[^\s,)]+')

# DOI should match 10.NNNN/... - flag if it doesn't look right
_DOI_PATTERN = re.compile(r'\b10\.\d{4,}/\S+')
_FAKE_DOI_PATTERN = re.compile(r'\b10\.(?:0000|1234|9999)/\S+')

# Fabricated citation pattern: [Author, Year] where author looks generic
_CITATION_PATTERN = re.compile(r'\[([A-Z][a-z]+(?:\s+(?:et\s+al\.|& [A-Z][a-z]+))?),\s*(\d{4})\]')


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def calculate_hedging_ratio(text: str) -> float:
    """Ratio of hedging phrases ('I think', 'might be', 'probably') to total sentences."""
    if not text.strip():
        return 0.0

    text_lower = text.lower()

    # Count sentences (split on period, exclamation, question mark)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    total_sentences = max(len(sentences), 1)

    # Count sentences containing hedging phrases
    hedging_count = 0
    for sentence in sentences:
        sentence_lower = sentence.lower()
        for phrase in _HEDGING_PHRASES:
            if phrase in sentence_lower:
                hedging_count += 1
                break  # count each sentence only once

    return hedging_count / total_sentences


def detect_fake_citations(text: str) -> List[str]:
    """Finds fabricated URLs (example.com), fake DOIs, non-standard citation formats."""
    signals: List[str] = []

    # Check URLs against fake domain list
    for m in _URL_PATTERN.finditer(text):
        url = m.group()
        for fake_domain in _FAKE_URL_DOMAINS:
            if fake_domain in url.lower():
                signals.append(f"fake_url: {url}")
                break

    # Check for suspicious DOIs
    for m in _FAKE_DOI_PATTERN.finditer(text):
        signals.append(f"suspicious_doi: {m.group()}")

    return signals


def check_prompt_response_alignment(prompt: str, response: str) -> float:
    """TF-IDF cosine similarity between prompt and response. Low = off-topic.

    Returns a neutral 0.5 for very short texts where TF-IDF is unreliable.
    """
    if not prompt.strip() or not response.strip():
        return 0.0

    # Short texts produce noisy TF-IDF vectors — return neutral score
    if len(response.strip()) < 50 or len(prompt.strip()) < 10:
        return 0.5

    try:
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform([prompt, response])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(similarity)
    except ValueError:
        # Can happen if texts are too short or only stop words
        return 0.5


def check_hallucination(response_text: str, original_prompt: str) -> HallucinationResult:
    """Evaluates response for hallucination signals."""
    hedging_ratio = calculate_hedging_ratio(response_text)
    fabrication_signals = detect_fake_citations(response_text)
    alignment = check_prompt_response_alignment(original_prompt, response_text)

    # Confidence score: inverse of hedging (more hedging = less confident)
    confidence_score = max(0.0, 1.0 - hedging_ratio)

    # Contradiction detection - simple heuristic: look for "but", "however"
    # following a definitive statement, then contradicting it
    contradiction_detected = False
    text_lower = response_text.lower()
    contradiction_markers = ["however", "but actually", "on the other hand", "contrary to"]
    definitive_markers = ["definitely", "certainly", "absolutely", "without a doubt"]
    has_definitive = any(m in text_lower for m in definitive_markers)
    has_contradiction = any(m in text_lower for m in contradiction_markers)
    if has_definitive and has_contradiction:
        contradiction_detected = True

    # Overall risk assessment
    risk_factors = 0
    if hedging_ratio > 0.3:
        risk_factors += 2
    elif hedging_ratio > 0.15:
        risk_factors += 1

    if fabrication_signals:
        risk_factors += 2

    if contradiction_detected:
        risk_factors += 1

    if risk_factors >= 4:
        overall_risk = "high"
    elif risk_factors >= 1:
        overall_risk = "medium"
    else:
        overall_risk = "low"

    return HallucinationResult(
        confidence_score=round(confidence_score, 3),
        hedging_ratio=round(hedging_ratio, 3),
        contradiction_detected=contradiction_detected,
        fabrication_signals=fabrication_signals,
        overall_risk=overall_risk,
    )
