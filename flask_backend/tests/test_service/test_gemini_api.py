import io
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError

from flask_backend.service.gemini_api import Gemini
from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY


class TestGeminiInit:
    def test_missing_api_key_raises_value_error(self, app):
        with app.app_context():
            with (
                patch("flask_backend.service.gemini_api.GEMINI_API_KEY", None),
                pytest.raises(ValueError, match="Invalid Gemini API key"),
            ):
                Gemini()

    def test_with_api_key_builds_client(self, app):
        with app.app_context():
            with (
                patch("flask_backend.service.gemini_api.GEMINI_API_KEY", "fake-key"),
                patch("flask_backend.service.gemini_api.genai.Client") as mock_client_cls,
            ):
                Gemini()
            mock_client_cls.assert_called_once_with(api_key="fake-key")


def _make_gemini():
    with (
        patch("flask_backend.service.gemini_api.GEMINI_API_KEY", "fake-key"),
        patch(
            "flask_backend.service.gemini_api.genai.Client", return_value=MagicMock()
        ),
    ):
        return Gemini()


class TestPromptImage:
    def test_success_returns_response_text(self, app):
        with app.app_context():
            gemini = _make_gemini()
            mock_response = MagicMock()
            mock_response.text = "Uma bela descrição."
            gemini.client.models.generate_content.return_value = mock_response

            image = io.BytesIO(b"fake-image-bytes")
            image.mimetype = "image/jpeg"

            result = gemini.prompt_image(image, "describe this")

            assert result == "Uma bela descrição."
            args, kwargs = gemini.client.models.generate_content.call_args
            assert kwargs["model"] == GEMINI_MODEL_PRIORITY[0]
            assert kwargs["contents"][0] == "describe this"

    def test_rate_limit_on_first_model_falls_back_to_second(self, app):
        with app.app_context():
            gemini = _make_gemini()
            mock_response = MagicMock()
            mock_response.text = "Uma bela descrição."
            gemini.client.models.generate_content.side_effect = [
                ClientError(code=429, response_json={}),
                mock_response,
            ]

            image = io.BytesIO(b"fake-image-bytes")
            image.mimetype = "image/jpeg"

            result = gemini.prompt_image(image, "describe this")

            assert result == "Uma bela descrição."
            calls = gemini.client.models.generate_content.call_args_list
            assert calls[0].kwargs["model"] == GEMINI_MODEL_PRIORITY[0]
            assert calls[1].kwargs["model"] == GEMINI_MODEL_PRIORITY[1]

    def test_rate_limit_on_every_model_raises_all_exhausted(self, app):
        from flask_backend.service.gemini_models import AllGeminiModelsExhausted

        with app.app_context():
            gemini = _make_gemini()
            gemini.client.models.generate_content.side_effect = ClientError(
                code=429, response_json={}
            )

            image = io.BytesIO(b"fake-image-bytes")
            image.mimetype = "image/jpeg"

            with pytest.raises(AllGeminiModelsExhausted):
                gemini.prompt_image(image, "describe this")

            assert gemini.client.models.generate_content.call_count == len(
                GEMINI_MODEL_PRIORITY
            )

    def test_non_rate_limit_error_propagates_without_fallback(self, app):
        with app.app_context():
            gemini = _make_gemini()
            gemini.client.models.generate_content.side_effect = ValueError("boom")

            image = io.BytesIO(b"fake-image-bytes")
            image.mimetype = "image/jpeg"

            with pytest.raises(ValueError, match="boom"):
                gemini.prompt_image(image, "describe this")

            assert gemini.client.models.generate_content.call_count == 1
