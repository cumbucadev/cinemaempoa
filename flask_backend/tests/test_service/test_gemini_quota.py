from google.genai.errors import ClientError

from flask_backend.service.gemini_quota import RateLimitInfo, classify_gemini_rate_limit

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
                        "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash"},
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
