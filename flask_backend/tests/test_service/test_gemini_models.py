import pytest

from flask_backend.service.gemini_models import (
    AllGeminiModelsExhausted,
    call_with_fallback,
)


class TestCallWithFallback:
    def test_succeeds_on_first_model(self):
        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            return "ok"

        result = call_with_fallback(
            build_and_call,
            lambda _exc: False,
            models=["model-a", "model-b"],
        )

        assert result == "ok"
        assert calls == ["model-a"]

    def test_falls_back_after_rate_limited_models(self):
        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            if model_id != "model-c":
                raise ValueError("rate limited")
            return "ok"

        result = call_with_fallback(
            build_and_call,
            lambda exc: True,  # noqa: ARG005
            models=["model-a", "model-b", "model-c"],
        )

        assert result == "ok"
        assert calls == ["model-a", "model-b", "model-c"]

    def test_raises_all_exhausted_when_every_model_is_rate_limited(self):
        def build_and_call(model_id):
            raise ValueError(f"rate limited: {model_id}")

        with pytest.raises(AllGeminiModelsExhausted) as exc_info:
            call_with_fallback(
                build_and_call,
                lambda _exc: True,
                models=["model-a", "model-b"],
            )

        assert isinstance(exc_info.value.__cause__, ValueError)
        assert "model-b" in str(exc_info.value.__cause__)
        assert str(exc_info.value)
        assert "2" in str(exc_info.value)

    def test_non_rate_limited_exception_propagates_immediately(self):
        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            call_with_fallback(
                build_and_call,
                lambda _exc: False,
                models=["model-a", "model-b"],
            )

        assert calls == ["model-a"]

    def test_default_models_is_gemini_model_priority(self):
        from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            return "ok"

        call_with_fallback(build_and_call, lambda exc: False)  # noqa: ARG005

        assert calls == [GEMINI_MODEL_PRIORITY[0]]


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
