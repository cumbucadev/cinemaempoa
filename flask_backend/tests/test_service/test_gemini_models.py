from unittest.mock import patch

import pytest

from flask_backend.service.gemini_models import (
    AllGeminiModelsExhausted,
    call_with_fallback,
)
from flask_backend.service.gemini_quota import RateLimitInfo

RATE_LIMITED = RateLimitInfo(quota_metric="unknown", retry_delay_seconds=None)


class TestCallWithFallback:
    def test_succeeds_on_first_model(self, app):
        with app.app_context():
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                return "ok"

            result = call_with_fallback(
                build_and_call,
                lambda _exc: None,
                models=["model-a", "model-b"],
            )

            assert result == "ok"
            assert calls == ["model-a"]

    def test_falls_back_after_rate_limited_models(self, app):
        with app.app_context():
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                if model_id != "model-c":
                    raise ValueError("rate limited")
                return "ok"

            result = call_with_fallback(
                build_and_call,
                lambda _exc: RATE_LIMITED,
                models=["model-a", "model-b", "model-c"],
            )

            assert result == "ok"
            assert calls == ["model-a", "model-b", "model-c"]

    def test_raises_all_exhausted_when_every_model_is_rate_limited(self, app):
        with app.app_context():

            def build_and_call(model_id):
                raise ValueError(f"rate limited: {model_id}")

            with pytest.raises(AllGeminiModelsExhausted) as exc_info:
                call_with_fallback(
                    build_and_call,
                    lambda _exc: RATE_LIMITED,
                    models=["model-a", "model-b"],
                )

            assert isinstance(exc_info.value.__cause__, ValueError)
            assert "model-b" in str(exc_info.value.__cause__)
            assert str(exc_info.value)
            assert "2" in str(exc_info.value)

    def test_non_rate_limited_exception_propagates_immediately(self, app):
        with app.app_context():
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                raise ValueError("boom")

            with pytest.raises(ValueError, match="boom"):
                call_with_fallback(
                    build_and_call,
                    lambda _exc: None,
                    models=["model-a", "model-b"],
                )

            assert calls == ["model-a"]

    def test_default_models_is_gemini_model_priority(self, app):
        from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

        with app.app_context():
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                return "ok"

            call_with_fallback(build_and_call, lambda _exc: None)

            assert calls == [GEMINI_MODEL_PRIORITY[0]]

    def test_pre_check_skips_a_model_already_in_cooldown_without_calling_it(self, app):
        with (
            app.app_context(),
            patch(
                "flask_backend.service.gemini_quota.is_available",
                side_effect=lambda model_id: model_id != "model-a",
            ),
        ):
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                return "ok"

            result = call_with_fallback(
                build_and_call,
                lambda _exc: None,
                models=["model-a", "model-b"],
            )

            assert result == "ok"
            assert calls == ["model-b"]

    def test_all_models_pre_check_skipped_raises_without_any_calls(self, app):
        with (
            app.app_context(),
            patch(
                "flask_backend.service.gemini_quota.is_available", return_value=False
            ),
        ):
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                return "ok"

            with pytest.raises(AllGeminiModelsExhausted):
                call_with_fallback(
                    build_and_call,
                    lambda _exc: None,
                    models=["model-a", "model-b"],
                )

            assert calls == []

    def test_a_real_per_day_429_blocks_the_model_on_the_next_call(self, app):
        from google.genai.errors import ClientError

        from flask_backend.service.gemini_quota import classify_gemini_rate_limit

        rpd_error_payload = {
            "error": {
                "code": 429,
                "message": "quota exceeded",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                "quotaValue": "20",
                            }
                        ],
                    },
                ],
            }
        }

        with app.app_context():

            def always_429(model_id):
                raise ClientError(code=429, response_json=rpd_error_payload)

            with pytest.raises(AllGeminiModelsExhausted) as exc_info:
                call_with_fallback(
                    always_429, classify_gemini_rate_limit, models=["gemini-2.5-flash"]
                )
            assert exc_info.value.__cause__ is not None

            # Second, separate call: the model must now be skipped entirely by
            # the pre-check written from the first call's real 429 - not mocked,
            # not simulated, the actual is_available()/record_attempt() round trip.
            calls = []

            def spy(model_id):
                calls.append(model_id)
                return "should never be called"

            with pytest.raises(AllGeminiModelsExhausted) as exc_info2:
                call_with_fallback(
                    spy, classify_gemini_rate_limit, models=["gemini-2.5-flash"]
                )
            assert calls == []
            assert exc_info2.value.__cause__ is None


class TestGeminiModelPriority:
    def test_has_seven_models_newest_flash_before_lite_per_generation(self):
        from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

        assert [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-flash-preview",
            "gemini-2.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
        ] == GEMINI_MODEL_PRIORITY
