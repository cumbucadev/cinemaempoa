from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from google.genai.errors import ServerError

from flask_backend.service.gemini_models import (
    AllGeminiModelsExhausted,
    call_with_fallback,
    call_with_fallback_waiting,
)
from flask_backend.service.gemini_quota import RateLimitInfo, classify_gemini_rate_limit

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


def _high_demand_503():
    return ServerError(
        code=503,
        response_json={
            "error": {
                "code": 503,
                "message": "This model is currently experiencing high demand.",
                "status": "UNAVAILABLE",
            }
        },
    )


class TestServerUnavailableFallback:
    def test_a_real_503_falls_back_to_the_next_model(self, app):
        with app.app_context():
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                if model_id == "model-a":
                    raise _high_demand_503()
                return "ok"

            result = call_with_fallback(
                build_and_call,
                classify_gemini_rate_limit,
                models=["model-a", "model-b"],
            )

            assert result == "ok"
            assert calls == ["model-a", "model-b"]

    def test_a_503_only_briefly_skips_the_model(self, app):
        from flask_backend.service import gemini_quota

        now = datetime(2026, 8, 5, 18, 0, 0)
        with app.app_context():
            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive", return_value=now
            ):

                def overloaded(model_id):
                    raise _high_demand_503()

                with pytest.raises(AllGeminiModelsExhausted):
                    call_with_fallback(
                        overloaded, classify_gemini_rate_limit, models=["model-a"]
                    )
                assert gemini_quota.is_available("model-a") is False

            with patch(
                "flask_backend.service.gemini_quota._utcnow_naive",
                return_value=now + timedelta(minutes=2),
            ):
                assert gemini_quota.is_available("model-a") is True


class TestCallWithFallbackWaiting:
    def test_returns_first_pass_result_without_waiting(self, app):
        with app.app_context(), patch(
            "flask_backend.service.gemini_models.time.sleep"
        ) as sleep:
            result = call_with_fallback_waiting(
                lambda _model_id: "ok",
                classify_gemini_rate_limit,
                max_wait_seconds=90,
                models=["model-a"],
            )

            assert result == "ok"
            sleep.assert_not_called()

    def test_waits_for_the_cooldown_and_retries_when_every_model_503s(self, app):
        with app.app_context():
            calls = []

            def build_and_call(model_id):
                calls.append(model_id)
                if len(calls) <= 2:
                    raise _high_demand_503()
                return "ok"

            # Sleeping "passes" the 60s cooldown by moving the clock forward.
            clock = {"now": datetime(2026, 8, 5, 18, 0, 0)}

            def fake_sleep(seconds):
                clock["now"] += timedelta(seconds=seconds)

            with (
                patch(
                    "flask_backend.service.gemini_quota._utcnow_naive",
                    side_effect=lambda: clock["now"],
                ),
                patch(
                    "flask_backend.service.gemini_models.time.sleep",
                    side_effect=fake_sleep,
                ) as sleep,
            ):
                result = call_with_fallback_waiting(
                    build_and_call,
                    classify_gemini_rate_limit,
                    max_wait_seconds=90,
                    models=["model-a", "model-b"],
                )

            assert result == "ok"
            assert calls == ["model-a", "model-b", "model-a"]
            sleep.assert_called_once_with(60)

    def test_reraises_without_waiting_when_recovery_is_too_far(self, app):
        with app.app_context(), patch(
            "flask_backend.service.gemini_models.time.sleep"
        ) as sleep:

            def build_and_call(model_id):
                raise ValueError("daily quota")

            with pytest.raises(AllGeminiModelsExhausted):
                call_with_fallback_waiting(
                    build_and_call,
                    lambda _exc: RATE_LIMITED,  # "unknown": cooldown until midnight
                    max_wait_seconds=90,
                    models=["model-a"],
                )

            sleep.assert_not_called()

    def test_reraises_without_waiting_when_only_stale_cooldowns_exist(self, app):
        from flask_backend.repository import gemini_usage_events

        now = datetime(2026, 8, 5, 18, 0, 0)
        with (
            app.app_context(),
            patch("flask_backend.service.gemini_quota._utcnow_naive", return_value=now),
            patch(
                "flask_backend.service.gemini_quota.is_available", return_value=False
            ),
            patch("flask_backend.service.gemini_models.time.sleep") as sleep,
        ):
            gemini_usage_events.create(
                "model-a",
                now - timedelta(days=1),
                "rate_limited",
                quota_metric="requests_per_minute",
                unavailable_until=now - timedelta(days=1) + timedelta(seconds=60),
            )

            with pytest.raises(AllGeminiModelsExhausted):
                call_with_fallback_waiting(
                    lambda _model_id: "never called",
                    classify_gemini_rate_limit,
                    max_wait_seconds=90,
                    models=["model-a"],
                )

            sleep.assert_not_called()


class TestGeminiModelPriority:
    def test_has_six_models_newest_flash_before_lite_per_generation(self):
        from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

        assert [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-flash-preview",
            "gemini-2.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
        ] == GEMINI_MODEL_PRIORITY
