from datetime import datetime, timedelta
from unittest.mock import patch

from google.genai.errors import ClientError

from flask_backend.repository import gemini_usage_events
from flask_backend.service.gemini_quota import (
    GEMINI_MODEL_LIMITS,
    RateLimitInfo,
    classify_gemini_rate_limit,
    is_available,
    record_attempt,
)

# Matches the real payload Google returns for a free-tier daily request cap.
SAMPLE_RPD_ERROR = {
    "error": {
        "code": 429,
        "message": "You exceeded your current quota...",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.Help",
                "links": [{"description": "docs", "url": "https://example.com"}],
            },
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaDimensions": {
                            "location": "global",
                            "model": "gemini-2.5-flash",
                        },
                        "quotaValue": "20",
                    }
                ],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "51s"},
        ],
    }
}

SAMPLE_RPM_ERROR = {
    "error": {
        "code": 429,
        "message": "rate limited",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {
                        "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
                        "quotaValue": "10",
                    }
                ],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "12s"},
        ],
    }
}


class TestClassifyGeminiRateLimit:
    def test_returns_none_for_non_client_error(self):
        assert classify_gemini_rate_limit(ValueError("boom")) is None

    def test_returns_none_for_non_429_client_error(self):
        exc = ClientError(code=400, response_json={})
        assert classify_gemini_rate_limit(exc) is None

    def test_classifies_per_day_quota_and_ignores_its_retry_delay(self):
        exc = ClientError(code=429, response_json=SAMPLE_RPD_ERROR)

        result = classify_gemini_rate_limit(exc)

        assert result == RateLimitInfo(
            quota_metric="requests_per_day", retry_delay_seconds=None
        )

    def test_classifies_per_minute_quota_and_keeps_its_retry_delay(self):
        exc = ClientError(code=429, response_json=SAMPLE_RPM_ERROR)

        result = classify_gemini_rate_limit(exc)

        assert result == RateLimitInfo(
            quota_metric="requests_per_minute", retry_delay_seconds=12.0
        )

    def test_classifies_as_unknown_when_no_quota_failure_present(self):
        exc = ClientError(code=429, response_json={})

        result = classify_gemini_rate_limit(exc)

        assert result == RateLimitInfo(quota_metric="unknown", retry_delay_seconds=None)


FROZEN_NOW = datetime(2026, 8, 5, 18, 0, 0)  # 18:00 UTC = 11:00 Pacific (PDT, UTC-7)


class TestIsAvailable:
    def test_available_when_no_events_logged(self, app):
        with app.app_context():
            assert is_available("gemini-2.5-flash") is True

    def test_unavailable_once_rpm_limit_reached_within_trailing_60s(self, app):
        # gemini-2.5-flash has no configured "rpm" in production - patch in a
        # fake model with one so this test doesn't depend on real config.
        with app.app_context(), patch(
            "flask_backend.service.gemini_quota.GEMINI_MODEL_LIMITS",
            {"test-model": {"rpm": 3}},
        ), patch(
            "flask_backend.service.gemini_quota._utcnow_naive", return_value=FROZEN_NOW
        ):
            for _ in range(3):
                gemini_usage_events.create("test-model", FROZEN_NOW, "success")

            assert is_available("test-model") is False

    def test_available_again_once_events_fall_outside_the_rpm_window(self, app):
        with app.app_context(), patch(
            "flask_backend.service.gemini_quota.GEMINI_MODEL_LIMITS",
            {"test-model": {"rpm": 3}},
        ):
            too_old = FROZEN_NOW - timedelta(seconds=61)
            for _ in range(3):
                gemini_usage_events.create("test-model", too_old, "success")

            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive",
                return_value=FROZEN_NOW,
            ):
                assert is_available("test-model") is True

    def test_unavailable_once_rpd_limit_reached_within_the_pacific_day(self, app):
        with app.app_context(), patch(
            "flask_backend.service.gemini_quota._utcnow_naive", return_value=FROZEN_NOW
        ):
            limit = GEMINI_MODEL_LIMITS["gemini-2.5-flash"]["rpd"]
            for _ in range(limit):
                gemini_usage_events.create("gemini-2.5-flash", FROZEN_NOW, "success")

            assert is_available("gemini-2.5-flash") is False

    def test_available_again_once_events_fall_outside_the_rpd_window(self, app):
        with app.app_context():
            limit = GEMINI_MODEL_LIMITS["gemini-2.5-flash"]["rpd"]
            yesterday = FROZEN_NOW - timedelta(days=1)
            for _ in range(limit):
                gemini_usage_events.create("gemini-2.5-flash", yesterday, "success")

            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive",
                return_value=FROZEN_NOW,
            ):
                assert is_available("gemini-2.5-flash") is True

    def test_unconfigured_model_is_always_available_regardless_of_volume(self, app):
        with app.app_context():
            for _ in range(1000):
                gemini_usage_events.create(
                    "some-unconfigured-model", FROZEN_NOW, "success"
                )

            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive",
                return_value=FROZEN_NOW,
            ):
                assert is_available("some-unconfigured-model") is True

    def test_reactive_cooldown_blocks_even_when_proactive_count_is_under_limit(
        self, app
    ):
        with app.app_context():
            gemini_usage_events.create(
                "gemini-2.5-flash",
                FROZEN_NOW,
                "rate_limited",
                quota_metric="requests_per_day",
                unavailable_until=FROZEN_NOW + timedelta(hours=1),
            )

            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive",
                return_value=FROZEN_NOW + timedelta(minutes=30),
            ):
                assert is_available("gemini-2.5-flash") is False

    def test_reactive_cooldown_clears_once_unavailable_until_has_passed(self, app):
        with app.app_context():
            gemini_usage_events.create(
                "gemini-2.5-flash",
                FROZEN_NOW,
                "rate_limited",
                quota_metric="requests_per_day",
                unavailable_until=FROZEN_NOW + timedelta(hours=1),
            )

            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive",
                return_value=FROZEN_NOW + timedelta(hours=2),
            ):
                assert is_available("gemini-2.5-flash") is True

    def test_a_later_success_clears_an_earlier_rate_limited_cooldown(self, app):
        with app.app_context():
            gemini_usage_events.create(
                "gemini-2.5-flash",
                FROZEN_NOW,
                "rate_limited",
                quota_metric="requests_per_day",
                unavailable_until=FROZEN_NOW + timedelta(hours=6),
            )
            gemini_usage_events.create(
                "gemini-2.5-flash", FROZEN_NOW + timedelta(seconds=1), "success"
            )

            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive",
                return_value=FROZEN_NOW + timedelta(seconds=2),
            ):
                assert is_available("gemini-2.5-flash") is True


class TestRecordAttempt:
    def test_success_writes_a_row_with_no_quota_metric_or_cooldown(self, app):
        with app.app_context(), patch(
            "flask_backend.service.gemini_quota._utcnow_naive", return_value=FROZEN_NOW
        ):
            record_attempt("gemini-2.5-flash", "success", None)

            event = gemini_usage_events.most_recent("gemini-2.5-flash")
            assert event.outcome == "success"
            assert event.quota_metric is None
            assert event.unavailable_until is None

    def test_requests_per_minute_cooldown_uses_retry_delay(self, app):
        from flask_backend.service.gemini_quota import RateLimitInfo

        with app.app_context(), patch(
            "flask_backend.service.gemini_quota._utcnow_naive", return_value=FROZEN_NOW
        ):
            record_attempt(
                "gemini-2.5-flash",
                "rate_limited",
                RateLimitInfo(
                    quota_metric="requests_per_minute", retry_delay_seconds=12.0
                ),
            )

            event = gemini_usage_events.most_recent("gemini-2.5-flash")
            assert event.quota_metric == "requests_per_minute"
            assert event.unavailable_until == FROZEN_NOW + timedelta(seconds=12)

    def test_requests_per_minute_cooldown_falls_back_to_default_when_no_retry_delay(
        self, app
    ):
        from flask_backend.service.gemini_quota import (
            DEFAULT_RPM_COOLDOWN_SECONDS,
            RateLimitInfo,
        )

        with app.app_context(), patch(
            "flask_backend.service.gemini_quota._utcnow_naive", return_value=FROZEN_NOW
        ):
            record_attempt(
                "gemini-2.5-flash",
                "rate_limited",
                RateLimitInfo(
                    quota_metric="requests_per_minute", retry_delay_seconds=None
                ),
            )

            event = gemini_usage_events.most_recent("gemini-2.5-flash")
            assert event.unavailable_until == FROZEN_NOW + timedelta(
                seconds=DEFAULT_RPM_COOLDOWN_SECONDS
            )

    def test_requests_per_day_cooldown_is_next_pacific_midnight_ignoring_retry_delay(
        self, app
    ):
        from flask_backend.service.gemini_quota import RateLimitInfo

        # FROZEN_NOW = 2026-08-05 18:00 UTC = 2026-08-05 11:00 PDT (UTC-7).
        # Next Pacific midnight is 2026-08-06 00:00 PDT = 2026-08-06 07:00 UTC.
        with app.app_context(), patch(
            "flask_backend.service.gemini_quota._utcnow_naive", return_value=FROZEN_NOW
        ):
            record_attempt(
                "gemini-2.5-flash",
                "rate_limited",
                RateLimitInfo(
                    quota_metric="requests_per_day", retry_delay_seconds=None
                ),
            )

            event = gemini_usage_events.most_recent("gemini-2.5-flash")
            assert event.unavailable_until == datetime(2026, 8, 6, 7, 0, 0)
