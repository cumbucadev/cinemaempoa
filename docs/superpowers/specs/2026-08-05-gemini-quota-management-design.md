# Gemini quota management — design spec

## Problem

`flask_backend/service/gemini_models.py` provides `call_with_fallback`, used by
three call sites (`Gemini.prompt_image`, `movie_inspector.inspect_movie`,
`scrapers/llms.py`'s extractors) to retry a Gemini request across
`GEMINI_MODEL_PRIORITY` on a 429. This fallback is entirely stateless: every
call starts back at the top of the priority list, with no memory of which
models are currently rate-limited.

In practice, Gemini 429s come from three different quota dimensions —
requests per minute, tokens per day, requests per day — each with a very
different recovery time. A request-per-day exhaustion lasts until the next
daily reset (effectively the rest of the day), but the current code will
still retry that same model on every subsequent call in a batch (e.g. one
call per movie in `inspect-movies`), wasting an HTTP round trip and eating a
429 every time before falling through to the next model.

This spec adds a `gemini_usage_events` table so the app can track its own
Gemini usage and skip models it already knows are exhausted, before making a
doomed request.

## Goals

- Avoid retrying a model that is already known to be exhausted for the
  current window (requests-per-minute or requests-per-day).
- Work correctly across all three existing call sites without changing their
  external behavior (same exceptions, same fallback order).
- Support multiple concurrent processes/agents in the future without
  requiring cross-process locking today.

## Non-goals

- Token-per-day (TPD) tracking. Dropped from scope: extracting token usage
  from `call_with_fallback`'s generic `Callable[[str], T]` return value would
  require call-site-specific extraction logic, and for
  `movie_inspector.py`'s multi-turn tool-calling agent loop, token usage
  isn't available at the `call_with_fallback` return boundary at all (it
  would need a separate accumulator fed by the agent's per-turn hooks). A
  model that hits a token-per-day cap is still caught by the reactive
  cooldown described below — it just isn't pre-empted proactively.
- Perfectly accurate RPM counting for `movie_inspector.py`'s tool-calling
  loop. That loop can make up to `MAX_TOOL_CALLS` (4) real Gemini requests
  per model before `call_with_fallback` sees one success/failure. Usage is
  logged once per `call_with_fallback` attempt (not once per underlying HTTP
  request), so RPM tracking for this call site is an undercount in the
  multi-turn case. `gemini_api.py` and the scraper extractors make exactly
  one real request per attempt, so they're unaffected. The reactive cooldown
  (below) covers whatever this undercount misses.
- Cross-process locking around the pre-check/log sequence. See
  "Concurrency" below.

## Data model

New table, following the existing `PosterFetchAttempt` /
`MovieMetadataFetchAttempt` append-only attempt-log shape:

```python
class GeminiUsageEvent(Base):
    __tablename__ = "gemini_usage_events"

    id = Column(Integer, primary_key=True)
    model_id = Column(String, nullable=False, index=True)
    occurred_at = Column(DateTime, nullable=False, index=True)
    outcome = Column(String, nullable=False)  # "success" | "rate_limited"
    quota_metric = Column(String, nullable=True)
    # "requests_per_minute" | "requests_per_day" | "unknown"; only set when
    # outcome == "rate_limited"
    unavailable_until = Column(DateTime, nullable=True)
    # only set when outcome == "rate_limited"; see "Reactive cooldown" below
```

One row is written per `call_with_fallback` attempt — i.e. once per model
actually tried, whether it succeeded or was rate-limited. Non-rate-limit
exceptions still propagate immediately with no row written (unchanged from
today's behavior).

**Timestamp convention deviation:** the rest of the codebase uses naive
`datetime.now()` (server-local time) for attempt tables. `occurred_at` here
is deliberately stored as a naive **UTC** timestamp
(`datetime.now(timezone.utc).replace(tzinfo=None)`) instead, because the
requests-per-day window must line up with Google's actual daily quota reset
(Pacific time), not server local time. An ambiguous server-local timestamp
can't support that conversion reliably.

New config, alongside `GEMINI_MODEL_PRIORITY` in `gemini_models.py`:

```python
GEMINI_MODEL_LIMITS: dict[str, dict[str, int]] = {
    "gemini-2.5-flash": {"rpm": 20, "rpd": 20},
    # ... one entry per model in GEMINI_MODEL_PRIORITY, hand-maintained.
    # A model with no entry, or a missing "rpm"/"rpd" key, is treated as
    # unlimited for that dimension.
}
```

## Classifying a 429

`google.genai.errors.ClientError` (a subclass of `APIError`) exposes the full
JSON error body as `exc.details`, matching the structure in Google's error
responses: a `details` list containing a `QuotaFailure` entry
(`violations[0]["quotaId"]`) and a `RetryInfo` entry (`retryDelay`, e.g.
`"51s"`).

```python
@dataclass
class RateLimitInfo:
    quota_metric: str  # "requests_per_minute" | "requests_per_day" | "unknown"
    retry_delay_seconds: Optional[float]

def classify_gemini_rate_limit(exc: Exception) -> Optional[RateLimitInfo]:
    """Returns None if exc is not a 429 ClientError. Otherwise classifies
    which quota was hit from the QuotaFailure violation's quotaId, and
    extracts Google's suggested retryDelay if present."""
    if not (isinstance(exc, ClientError) and exc.code == 429):
        return None
    quota_id = _extract_quota_id(exc.details)  # "" if not found
    metric = (
        "requests_per_day" if "PerDay" in quota_id
        else "requests_per_minute" if "PerMinute" in quota_id
        else "unknown"
    )
    return RateLimitInfo(metric, _extract_retry_delay(exc.details))
```

This lives in a new `flask_backend/service/gemini_quota.py` module and
**replaces** each call site's `_is_rate_limited(exc) -> bool` predicate with a
`_classify_rate_limit(exc) -> Optional[RateLimitInfo]` one:

- `gemini_api.py`, `scrapers/llms.py`: pass `classify_gemini_rate_limit`
  straight through — neither wraps the underlying `ClientError`.
- `movie_inspector.py`: keeps its one-line `InstructorRetryException` unwrap
  (`instructor` wraps the underlying error), then delegates to
  `classify_gemini_rate_limit`. The quotaId-parsing logic itself lives in
  exactly one place.

Why not trust `retryDelay` uniformly: Google's own sample response reports a
`retryDelay` of `51s` for a violation whose `quotaId` is
`GenerateRequestsPerDayPerProjectPerModel-FreeTier` — a **daily** cap. A
51-second retry delay is clearly not tied to the actual reset time for a
per-day quota; it reads as a generic backoff hint rather than a reliable
signal. So `retryDelay` is only trusted for `requests_per_minute` violations;
`requests_per_day` (and `unknown`) violations ignore it entirely and use the
next quota reset instead (see below).

## Pre-check and reactive cooldown

`gemini_quota.is_available(model_id)` is checked before every model attempt
in `call_with_fallback`'s loop. It combines two mechanisms:

1. **Reactive cooldown (safety net):** if the most recent `rate_limited` row
   for this model has an `unavailable_until` still in the future, the model
   is unavailable — regardless of what the proactive counts below say. This
   is what protects against our own counts drifting from reality (e.g. a
   config value that no longer matches Google's actual current limit, or
   another process's usage that wasn't logged).
2. **Proactive counting (primary):** counts this model's logged attempts
   (any outcome) in the relevant window and compares against
   `GEMINI_MODEL_LIMITS`. RPM window is the trailing 60 seconds; RPD window
   is the current calendar day in `America/Los_Angeles` (via
   `zoneinfo.ZoneInfo`), matching Google's actual daily reset schedule. A
   model with no configured limit for a dimension always passes that check.

```python
def is_available(model_id: str) -> bool:
    now = _utcnow_naive()

    last_block = _most_recent_rate_limited_row(model_id)
    if last_block and last_block.unavailable_until > now:
        return False

    limits = GEMINI_MODEL_LIMITS.get(model_id, {})
    if (rpm := limits.get("rpm")) and _count_since(model_id, now - timedelta(seconds=60)) >= rpm:
        return False
    if (rpd := limits.get("rpd")) and _count_since(model_id, _pacific_day_start(now)) >= rpd:
        return False
    return True
```

`unavailable_until` is computed **once, at write time** (in
`record_attempt`, below), not recomputed on every read:

- `requests_per_minute`: `occurred_at + retry_delay_seconds`, falling back to
  a default (60s) if Google didn't include a `RetryInfo.retryDelay`.
- `requests_per_day` and `unknown`: the next Pacific-time midnight, converted
  to UTC.

```python
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
        else:  # "requests_per_day" or "unknown" - treated conservatively the same way
            unavailable_until = _next_pacific_midnight_utc(now)
    # insert GeminiUsageEvent(model_id, now, outcome, quota_metric, unavailable_until)
```

## Integration into `call_with_fallback`

```python
def call_with_fallback(
    build_and_call: Callable[[str], T],
    classify_rate_limit: Callable[[Exception], Optional[RateLimitInfo]],
    models: list[str] = GEMINI_MODEL_PRIORITY,
) -> T:
    last_error = None
    for model_id in models:
        if not gemini_quota.is_available(model_id):
            continue  # skip entirely - zero HTTP calls for known-exhausted models
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
    raise AllGeminiModelsExhausted(
        f"All {len(models)} Gemini models unavailable (last error: {last_error})"
    ) from last_error
```

If every model is skipped by the pre-check, no HTTP call is made at all and
`last_error` stays `None` — `AllGeminiModelsExhausted` is still raised (same
contract callers already handle), just without a chained cause in that case.

## Concurrency

The pre-check (`SELECT`/count) and the subsequent `INSERT` are not wrapped in
a single transaction. Two concurrent processes could both pass the
pre-check right at the boundary and both proceed, causing a real 429 that a
fully serialized check would have avoided. This is accepted rather than
solved now: the reactive cooldown catches the overshoot on the very next
check for either process, and SQLite's single-writer model means the
underlying data is never corrupted — just occasionally a hair too
optimistic. Given current call volume (a handful of sequential CLI
pipelines, not yet high-frequency parallel agents), cross-process locking
isn't justified today; this is the first place to revisit if concurrent
agents become real.

## Migration

`flask --app flask_backend db-revision --autogenerate -m "add gemini_usage_events table"`,
adding `GeminiUsageEvent` to `flask_backend/models.py`.

## Testing

- `gemini_quota.py` unit tests: quotaId classification
  (`PerDay`/`PerMinute`/unrecognized) and retry-delay parsing against crafted
  `ClientError` instances matching Google's sample payload; `is_available`
  boundary conditions (exactly at/under/over RPM and RPD limits); Pacific
  midnight rollover with a mocked `now` just before/after the boundary; the
  reactive cooldown overriding a proactive count that would otherwise say
  "available."
- `test_gemini_models.py`: existing tests updated for the new
  `classify_rate_limit` contract (predicates now return `RateLimitInfo(...)`
  or `None` instead of a bool); new test confirming a pre-check-skipped
  model never reaches `build_and_call`; new test confirming an all-skipped
  run raises `AllGeminiModelsExhausted` with zero calls made.
- `test_gemini_api.py`, `test_movie_inspector.py`, scraper LLM tests: updated
  wherever they construct the old boolean rate-limit predicate directly.

## Summary of call-site changes

- `gemini_models.py`: `call_with_fallback`'s second parameter changes type
  from `Callable[[Exception], bool]` to
  `Callable[[Exception], Optional[RateLimitInfo]]`; pre-check/record calls
  added around the loop.
- `gemini_api.py`, `scrapers/llms.py`: `_is_rate_limited` replaced by passing
  `classify_gemini_rate_limit` directly.
- `movie_inspector.py`: `_is_rate_limited` becomes `_classify_rate_limit`,
  keeping its `InstructorRetryException` unwrap before delegating.
- New `flask_backend/service/gemini_quota.py`: `GEMINI_MODEL_LIMITS`,
  `RateLimitInfo`, `classify_gemini_rate_limit`, `is_available`,
  `record_attempt`, and the Pacific-day/UTC helpers.
