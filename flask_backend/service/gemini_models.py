from typing import Callable, Optional, TypeVar

from flask_backend.service import gemini_quota
from flask_backend.service.gemini_quota import RateLimitInfo

T = TypeVar("T")

GEMINI_MODEL_PRIORITY = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]


class AllGeminiModelsExhausted(Exception):
    """Every model in GEMINI_MODEL_PRIORITY was rate-limited or already
    known to be exhausted from a prior call."""


def call_with_fallback(
    build_and_call: Callable[[str], T],
    classify_rate_limit: Callable[[Exception], Optional[RateLimitInfo]],
    models: list[str] = GEMINI_MODEL_PRIORITY,
) -> T:
    """Calls build_and_call(model_id) for each model in priority order,
    returning the first successful result. Models gemini_quota.is_available
    already knows are exhausted are skipped without being called at all.
    classify_rate_limit(exc) is called on any exception build_and_call
    raises: returning None re-raises immediately; returning a RateLimitInfo
    logs the attempt and moves to the next model. Raises
    AllGeminiModelsExhausted (chained from the last real error, or
    chained from nothing if every model was skipped by the pre-check) if no
    model produces a result."""
    last_error = None
    for model_id in models:
        if not gemini_quota.is_available(model_id):
            continue
        try:
            result = build_and_call(model_id)
        except Exception as exc:
            rate_limit_info = classify_rate_limit(exc)
            if rate_limit_info is None:
                raise
            gemini_quota.record_attempt(model_id, "rate_limited", rate_limit_info)
            last_error = exc
            continue
        gemini_quota.record_attempt(model_id, "success", None)
        return result
    if last_error is None:
        raise AllGeminiModelsExhausted(
            f"All {len(models)} Gemini models are already known to be unavailable "
            "(quota pre-check skipped every one; none were called)"
        )
    raise AllGeminiModelsExhausted(
        f"All {len(models)} Gemini models rate-limited (last error: {last_error})"
    ) from last_error
