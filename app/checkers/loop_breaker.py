"""
Loop Breaker — Detects repetitive agent behavior using a sliding window.

Algorithm:
  1. Take last N entries from action_history
  2. Vectorize all entries using TF-IDF
  3. Compute pairwise cosine similarity matrix
  4. Average the upper triangle (excluding diagonal)
  5. If average > threshold → loop detected

Action escalation:
  score > 0.95 → "kill"
  score > threshold → "warn"
  else → "continue"

Dependencies: scikit-learn (for TF-IDF), Python stdlib.
"""

import numpy as np
from dataclasses import dataclass
from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class LoopDetectionResult:
    is_loop: bool
    repetition_score: float        # 0.0 – 1.0 (avg pairwise similarity)
    window_size: int
    recommended_action: str        # "continue", "warn", "kill"


def detect_loop(
    action_history: List[str],
    window_size: int = 5,
    threshold: float = 0.85,
) -> LoopDetectionResult:
    """Checks if the last N actions are semantically repetitive."""

    # Take last window_size entries
    window = action_history[-window_size:] if len(action_history) > window_size else action_history

    # Need at least 2 entries to compare
    if len(window) < 2:
        return LoopDetectionResult(
            is_loop=False,
            repetition_score=0.0,
            window_size=len(window),
            recommended_action="continue",
        )

    try:
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(window)
        similarity_matrix = cosine_similarity(tfidf_matrix)

        # Average the upper triangle (excluding diagonal)
        n = similarity_matrix.shape[0]
        upper_triangle_sum = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                upper_triangle_sum += similarity_matrix[i][j]
                count += 1

        avg_similarity = upper_triangle_sum / count if count > 0 else 0.0

    except ValueError:
        # Can happen if all entries are identical stop words or empty
        avg_similarity = 1.0

    # Cast to native Python types (numpy bools fail `is True` identity checks)
    avg_similarity = float(avg_similarity)

    # Determine action
    is_loop = avg_similarity > threshold
    if avg_similarity > 0.95:
        action = "kill"
    elif avg_similarity > threshold:
        action = "warn"
    else:
        action = "continue"

    return LoopDetectionResult(
        is_loop=bool(is_loop),
        repetition_score=round(avg_similarity, 4),
        window_size=len(window),
        recommended_action=action,
    )
