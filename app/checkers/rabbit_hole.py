"""
Rabbit Hole Detector - Prevents AI from drifting off-topic during web searches.

Two checks:
  1. Query alignment: TF-IDF cosine similarity between the original user prompt
     and the AI-generated search query. Below threshold = query drift.
  2. Domain reputation: Blocklist (SEO spam, content farms) and allowlist
     (Wikipedia, .gov, .edu, major news outlets).

Dependencies: scikit-learn (for TF-IDF), Python stdlib.
"""

import re
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlparse

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class AlignmentResult:
    similarity_score: float        # 0.0 - 1.0
    is_relevant: bool              # True if score >= threshold
    flagged_domains: List[str]     # domains that failed reputation check
    recommendation: str            # "proceed", "warn_query_drift", "block_irrelevant"


# ---------------------------------------------------------------------------
# Domain reputation lists
# ---------------------------------------------------------------------------

_DOMAIN_BLOCKLIST = {
    # SEO spam / content farms
    "seo-spam-blog.xyz",
    "content-farm.info",
    "clickbait-news.co",
    "fake-news-daily.com",
    "spam-articles.net",
    "viral-content.buzz",
    "ad-revenue-site.com",
    "keyword-stuffing.org",
    "scraped-content.io",
    "link-farm.xyz",
}

# TLD blocklist (commonly abused)
_SUSPICIOUS_TLDS = {".xyz", ".buzz", ".info", ".click", ".top", ".gq", ".ml", ".tk", ".cf", ".ga"}

_DOMAIN_ALLOWLIST = {
    # Encyclopedias
    "wikipedia.org",
    "britannica.com",
    # Government
    "gov",  # matches *.gov
    # Education
    "edu",  # matches *.edu
    # Major news
    "reuters.com",
    "apnews.com",
    "bbc.co.uk",
    "bbc.com",
    "nytimes.com",
    "washingtonpost.com",
    "theguardian.com",
    # Tech documentation
    "docs.python.org",
    "developer.mozilla.org",
    "stackoverflow.com",
    "github.com",
    # Science
    "nature.com",
    "sciencedirect.com",
    "pubmed.ncbi.nlm.nih.gov",
    "arxiv.org",
}


# ---------------------------------------------------------------------------
# Query alignment
# ---------------------------------------------------------------------------

def check_query_alignment(
    original_prompt: str,
    search_query: str,
    threshold: float = 0.3,
) -> AlignmentResult:
    """TF-IDF cosine similarity between prompt and AI-generated search query."""
    if not original_prompt.strip() or not search_query.strip():
        return AlignmentResult(
            similarity_score=0.0,
            is_relevant=False,
            flagged_domains=[],
            recommendation="block_irrelevant",
        )

    try:
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform([original_prompt, search_query])
        score = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])
    except ValueError:
        score = 0.0

    is_relevant = score >= threshold

    if score >= threshold:
        recommendation = "proceed"
    elif score >= threshold * 0.5:
        recommendation = "warn_query_drift"
    else:
        recommendation = "block_irrelevant"

    return AlignmentResult(
        similarity_score=round(score, 4),
        is_relevant=is_relevant,
        flagged_domains=[],
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Domain reputation
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Extracts the domain from a URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().lstrip("www.")
    except Exception:
        return url.lower()


def _is_allowlisted(domain: str) -> bool:
    """Checks if a domain is in the allowlist."""
    # Direct match
    if domain in _DOMAIN_ALLOWLIST:
        return True
    # Check if domain ends with an allowlisted suffix (e.g., .gov, .edu)
    for allowed in _DOMAIN_ALLOWLIST:
        if domain.endswith(f".{allowed}") or domain == allowed:
            return True
    return False


def _is_blocklisted(domain: str) -> bool:
    """Checks if a domain is in the blocklist or has a suspicious TLD."""
    if domain in _DOMAIN_BLOCKLIST:
        return True
    # Check suspicious TLDs
    for tld in _SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            return True
    return False


def check_domain_relevance(
    prompt_topic: str,
    cited_urls: List[str],
) -> AlignmentResult:
    """Checks if cited domains are reputable and topically relevant."""
    flagged: List[str] = []

    for url in cited_urls:
        domain = _extract_domain(url)
        if _is_blocklisted(domain) and not _is_allowlisted(domain):
            flagged.append(domain)
        elif not _is_allowlisted(domain):
            # Unknown domain - not flagged but also not trusted
            pass

    is_relevant = len(flagged) == 0

    if flagged:
        recommendation = "warn_query_drift"
    else:
        recommendation = "proceed"

    return AlignmentResult(
        similarity_score=1.0 if is_relevant else 0.0,
        is_relevant=is_relevant,
        flagged_domains=flagged,
        recommendation=recommendation,
    )
