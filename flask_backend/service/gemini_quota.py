"""Tracks Gemini API usage per model so gemini_models.call_with_fallback can
skip models it already knows are exhausted, instead of discovering that on
every single call. See docs/superpowers/specs/2026-08-05-gemini-quota-management-design.md.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.genai.errors import ClientError
from zoneinfo import ZoneInfo

from flask_backend.repository import gemini_usage_events


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


PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
DEFAULT_RPM_COOLDOWN_SECONDS = 60

# Hand-maintained. A model with no entry, or a missing "rpm"/"rpd" key, is
# treated as unlimited for that dimension. gemini-2.5-flash's rpd=20 is the
# one confirmed data point (from a real 429 response); add others as their
# real limits are observed.
GEMINI_MODEL_LIMITS: dict[str, dict[str, int]] = {
    "gemini-2.5-flash": {"rpd": 20},
}


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _pacific_day_start_utc(now_utc_naive: datetime) -> datetime:
    now_pacific = now_utc_naive.replace(tzinfo=timezone.utc).astimezone(PACIFIC_TZ)
    today = now_pacific.date()
    midnight_pacific = datetime(today.year, today.month, today.day, tzinfo=PACIFIC_TZ)
    return midnight_pacific.astimezone(timezone.utc).replace(tzinfo=None)


def _next_pacific_midnight_utc(now_utc_naive: datetime) -> datetime:
    now_pacific = now_utc_naive.replace(tzinfo=timezone.utc).astimezone(PACIFIC_TZ)
    next_day = now_pacific.date() + timedelta(days=1)
    next_midnight_pacific = datetime(
        next_day.year, next_day.month, next_day.day, tzinfo=PACIFIC_TZ
    )
    return next_midnight_pacific.astimezone(timezone.utc).replace(tzinfo=None)


def is_available(model_id: str) -> bool:
    now = _utcnow_naive()

    last_event = gemini_usage_events.most_recent(model_id)
    if (
        last_event is not None
        and last_event.outcome == "rate_limited"
        and last_event.unavailable_until is not None
        and last_event.unavailable_until > now
    ):
        return False

    limits = GEMINI_MODEL_LIMITS.get(model_id, {})

    rpm_limit = limits.get("rpm")
    if rpm_limit is not None:
        rpm_count = gemini_usage_events.count_since(
            model_id, now - timedelta(seconds=60)
        )
        if rpm_count >= rpm_limit:
            return False

    rpd_limit = limits.get("rpd")
    if rpd_limit is not None:
        rpd_count = gemini_usage_events.count_since(
            model_id, _pacific_day_start_utc(now)
        )
        if rpd_count >= rpd_limit:
            return False

    return True


def record_attempt(
    model_id: str, outcome: str, rate_limit_info: Optional[RateLimitInfo]
) -> None:
    now = _utcnow_naive()
    quota_metric = None
    unavailable_until = None

    if rate_limit_info is not None:
        quota_metric = rate_limit_info.quota_metric
        if quota_metric == "requests_per_minute":
            delay = rate_limit_info.retry_delay_seconds or DEFAULT_RPM_COOLDOWN_SECONDS
            unavailable_until = now + timedelta(seconds=delay)
        else:  # "requests_per_day" or "unknown" - treated the same, conservatively
            unavailable_until = _next_pacific_midnight_utc(now)

    gemini_usage_events.create(
        model_id,
        now,
        outcome,
        quota_metric=quota_metric,
        unavailable_until=unavailable_until,
    )
