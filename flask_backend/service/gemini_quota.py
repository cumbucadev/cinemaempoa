"""Tracks Gemini API usage per model so gemini_models.call_with_fallback can
skip models it already knows are exhausted, instead of discovering that on
every single call. See docs/superpowers/specs/2026-08-05-gemini-quota-management-design.md.
"""

from dataclasses import dataclass
from typing import Optional

from google.genai.errors import ClientError


@dataclass
class RateLimitInfo:
    quota_metric: str  # "requests_per_minute" | "requests_per_day" | "unknown"
    retry_delay_seconds: Optional[float]


def _details_list(response_json: dict) -> list:
    """Google's ClientError.details is response_json as-is, which comes in
    two shapes depending on the caller: {"details": [...]} directly, or
    nested under {"error": {"details": [...]}}. Mirrors the same defensive
    lookup APIError itself uses for message/status/code."""
    response_json = response_json or {}
    details = response_json.get("details")
    if details is None:
        details = response_json.get("error", {}).get("details")
    return details or []


def _extract_quota_id(response_json: dict) -> str:
    for entry in _details_list(response_json):
        if entry.get("@type", "").endswith("QuotaFailure"):
            violations = entry.get("violations") or []
            if violations:
                return violations[0].get("quotaId", "")
    return ""


def _extract_retry_delay(response_json: dict) -> Optional[float]:
    for entry in _details_list(response_json):
        if entry.get("@type", "").endswith("RetryInfo"):
            raw = entry.get("retryDelay")
            if isinstance(raw, str) and raw.endswith("s"):
                try:
                    return float(raw[:-1])
                except ValueError:
                    return None
    return None


def classify_gemini_rate_limit(exc: Exception) -> Optional[RateLimitInfo]:
    """Returns None if exc isn't a 429. Otherwise classifies which quota was
    hit from the QuotaFailure violation's quotaId, and extracts Google's
    suggested retryDelay - but only for requests_per_minute violations; see
    the "Why not trust retryDelay uniformly" note in the design spec for why
    requests_per_day (and unknown) violations ignore it."""
    if not (isinstance(exc, ClientError) and exc.code == 429):
        return None

    quota_id = _extract_quota_id(exc.details)
    if "PerDay" in quota_id:
        return RateLimitInfo(quota_metric="requests_per_day", retry_delay_seconds=None)
    if "PerMinute" in quota_id:
        return RateLimitInfo(
            quota_metric="requests_per_minute",
            retry_delay_seconds=_extract_retry_delay(exc.details),
        )
    return RateLimitInfo(quota_metric="unknown", retry_delay_seconds=None)
