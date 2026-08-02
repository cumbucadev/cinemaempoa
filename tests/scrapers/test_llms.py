from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError as GoogleGenAIClientError

from scrapers.llms import (
    CineBancariosExtractorLLM,
    CineCincoExtractorLLM,
    PauloAmorimEmailExtractorLLM,
)


def _make_extractor():
    with (
        patch.object(CineBancariosExtractorLLM, "_get_llm", return_value=MagicMock()),
        patch("scrapers.llms.Settings"),
    ):
        return CineBancariosExtractorLLM("gemini-2.5-flash")


class TestGetLlm:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            CineBancariosExtractorLLM("gemini-2.5-flash")

    def test_invalid_model_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid model name"):
            CineBancariosExtractorLLM("not-a-real-model")

    def test_gemini_with_api_key_builds_google_genai_client(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", "fake-key"),
            patch("llama_index.llms.google_genai.GoogleGenAI") as mock_cls,
            patch("scrapers.llms.Settings"),
        ):
            CineBancariosExtractorLLM("gemini-2.5-flash")
        mock_cls.assert_called_once_with(model="gemini-2.5-flash", api_key="fake-key")


class TestExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        extractor.llm.as_structured_llm.return_value.chat.return_value = mock_response

        result = extractor.extract_screenings_from_text(
            "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
        )

        assert result == '{"movies": []}'

    def test_rate_limit_error_returns_none(self):
        extractor = _make_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        result = extractor.extract_screenings_from_text(
            "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
        )

        assert result is None

    def test_generic_exception_returns_none(self):
        extractor = _make_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = Exception(
            "boom"
        )

        result = extractor.extract_screenings_from_text(
            "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
        )

        assert result is None


class TestGetCurrYear:
    def test_returns_current_year(self):
        extractor = _make_extractor()
        with patch("scrapers.llms.datetime") as mock_dt:
            mock_dt.now.return_value.year = 2026
            assert extractor._get_curr_year() == 2026


class TestPromptBuilders:
    def test_get_system_prompt_includes_year(self):
        extractor = _make_extractor()
        prompt = extractor._get_system_prompt(2026)
        assert "2026" in prompt
        assert "cinema programming auditor" in prompt

    def test_get_prompt_builds_system_and_user_messages(self):
        extractor = _make_extractor()
        messages = extractor._get_prompt(2026, "some blog text")
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "some blog text"


def _make_cine_cinco_extractor():
    with (
        patch.object(CineCincoExtractorLLM, "_get_llm", return_value=MagicMock()),
        patch("scrapers.llms.Settings"),
    ):
        return CineCincoExtractorLLM("gemini-2.5-flash")


class TestCineCincoExtractorLLMGetLlm:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            CineCincoExtractorLLM("gemini-2.5-flash")

    def test_gemini_with_api_key_builds_google_genai_client(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", "fake-key"),
            patch("llama_index.llms.google_genai.GoogleGenAI") as mock_cls,
            patch("scrapers.llms.Settings"),
        ):
            CineCincoExtractorLLM("gemini-2.5-flash")
        mock_cls.assert_called_once_with(model="gemini-2.5-flash", api_key="fake-key")


class TestCineCincoExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_cine_cinco_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        extractor.llm.as_structured_llm.return_value.chat.return_value = mock_response

        result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result == '{"movies": []}'

    def test_rate_limit_error_returns_none(self):
        extractor = _make_cine_cinco_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result is None

    def test_generic_exception_returns_none(self):
        extractor = _make_cine_cinco_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = Exception(
            "boom"
        )

        result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result is None


class TestCineCincoPromptBuilders:
    def test_get_system_prompt_includes_year_and_cine_cinco(self):
        extractor = _make_cine_cinco_extractor()
        prompt = extractor._get_system_prompt(2026)
        assert "2026" in prompt
        assert "Cine Cinco" in prompt
        assert "Direção de" in prompt

    def test_get_prompt_builds_system_and_user_messages(self):
        extractor = _make_cine_cinco_extractor()
        messages = extractor._get_prompt(2026, "some page text")
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "some page text"


def _make_paulo_amorim_email_extractor():
    with (
        patch.object(
            PauloAmorimEmailExtractorLLM, "_get_llm", return_value=MagicMock()
        ),
        patch("scrapers.llms.Settings"),
    ):
        return PauloAmorimEmailExtractorLLM("gemini-2.5-flash")


class TestPauloAmorimEmailExtractorLLMGetLlm:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            PauloAmorimEmailExtractorLLM("gemini-2.5-flash")

    def test_gemini_with_api_key_builds_google_genai_client(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", "fake-key"),
            patch("llama_index.llms.google_genai.GoogleGenAI") as mock_cls,
            patch("scrapers.llms.Settings"),
        ):
            PauloAmorimEmailExtractorLLM("gemini-2.5-flash")
        mock_cls.assert_called_once_with(model="gemini-2.5-flash", api_key="fake-key")


class TestPauloAmorimEmailExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_paulo_amorim_email_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        extractor.llm.as_structured_llm.return_value.chat.return_value = mock_response

        result = extractor.extract_screenings_from_text(
            "Wed, 22 Jul 2026 10:15:00 +0000", "some newsletter text"
        )

        assert result == '{"movies": []}'

    def test_rate_limit_error_returns_none(self):
        extractor = _make_paulo_amorim_email_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        result = extractor.extract_screenings_from_text(
            "Wed, 22 Jul 2026 10:15:00 +0000", "some newsletter text"
        )

        assert result is None

    def test_generic_exception_returns_none(self):
        extractor = _make_paulo_amorim_email_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = Exception(
            "boom"
        )

        result = extractor.extract_screenings_from_text(
            "Wed, 22 Jul 2026 10:15:00 +0000", "some newsletter text"
        )

        assert result is None


class TestPauloAmorimEmailPromptBuilders:
    def test_get_system_prompt_includes_year_and_rooms(self):
        extractor = _make_paulo_amorim_email_extractor()
        prompt = extractor._get_system_prompt(2026)
        assert "2026" in prompt
        assert "Sala Eduardo Hirtz" in prompt
        assert "Sinopse:" in prompt

    def test_get_prompt_builds_system_and_user_messages(self):
        extractor = _make_paulo_amorim_email_extractor()
        messages = extractor._get_prompt(2026, "some newsletter text")
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "some newsletter text"
