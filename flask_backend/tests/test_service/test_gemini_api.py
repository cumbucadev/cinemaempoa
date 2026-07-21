import io
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError

from flask_backend.service.gemini_api import Gemini


class TestGeminiInit:
    def test_missing_api_key_raises_value_error(self):
        with (
            patch("flask_backend.service.gemini_api.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="Invalid Gemini API key"),
        ):
            Gemini()

    def test_with_api_key_builds_client(self):
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
    def test_success_returns_response_text(self):
        gemini = _make_gemini()
        mock_response = MagicMock()
        mock_response.text = "Uma bela descrição."
        gemini.client.models.generate_content.return_value = mock_response

        image = io.BytesIO(b"fake-image-bytes")
        image.mimetype = "image/jpeg"

        result = gemini.prompt_image(image, "describe this")

        assert result == "Uma bela descrição."
        args, kwargs = gemini.client.models.generate_content.call_args
        assert kwargs["model"] == Gemini.MODEL
        assert kwargs["contents"][0] == "describe this"

    def test_rate_limit_error_propagates(self):
        gemini = _make_gemini()
        gemini.client.models.generate_content.side_effect = ClientError(
            code=429, response_json={}
        )

        image = io.BytesIO(b"fake-image-bytes")
        image.mimetype = "image/jpeg"

        with pytest.raises(ClientError):
            gemini.prompt_image(image, "describe this")
