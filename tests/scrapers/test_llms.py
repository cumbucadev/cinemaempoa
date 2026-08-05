from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError as GoogleGenAIClientError

from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY
from scrapers.llms import CineBancariosExtractorLLM, CineCincoExtractorLLM


class TestCineBancariosExtractorLLMInit:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            CineBancariosExtractorLLM()

    def test_gemini_with_api_key_constructs(self):
        with patch("scrapers.llms.GEMINI_API_KEY", "fake-key"):
            CineBancariosExtractorLLM()


def _make_extractor():
    with patch("scrapers.llms.GEMINI_API_KEY", "fake-key"):
        return CineBancariosExtractorLLM()


class TestExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.return_value = mock_response

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result == '{"movies": []}'
        mock_build.assert_called_once_with(GEMINI_MODEL_PRIORITY[0])

    def test_rate_limit_on_first_model_falls_back_to_second(self):
        extractor = _make_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        first_llm = MagicMock()
        first_llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )
        second_llm = MagicMock()
        second_llm.as_structured_llm.return_value.chat.return_value = mock_response

        with (
            patch(
                "scrapers.llms._build_llm", side_effect=[first_llm, second_llm]
            ) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result == '{"movies": []}'
        assert mock_build.call_args_list[0].args == (GEMINI_MODEL_PRIORITY[0],)
        assert mock_build.call_args_list[1].args == (GEMINI_MODEL_PRIORITY[1],)

    def test_rate_limit_on_every_model_returns_none(self):
        extractor = _make_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result is None
        assert mock_build.call_count == len(GEMINI_MODEL_PRIORITY)

    def test_generic_exception_returns_none(self):
        extractor = _make_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = Exception("boom")

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result is None
        assert mock_build.call_count == 1


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
    with patch("scrapers.llms.GEMINI_API_KEY", "fake-key"):
        return CineCincoExtractorLLM()


class TestCineCincoExtractorLLMInit:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            CineCincoExtractorLLM()


class TestCineCincoExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_cine_cinco_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.return_value = mock_response

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result == '{"movies": []}'
        mock_build.assert_called_once_with(GEMINI_MODEL_PRIORITY[0])

    def test_rate_limit_on_every_model_returns_none(self):
        extractor = _make_cine_cinco_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result is None
        assert mock_build.call_count == len(GEMINI_MODEL_PRIORITY)

    def test_generic_exception_returns_none(self):
        extractor = _make_cine_cinco_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = Exception("boom")

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result is None
        assert mock_build.call_count == 1


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
