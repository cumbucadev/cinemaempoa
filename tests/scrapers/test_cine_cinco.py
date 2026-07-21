import json
import os
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from scrapers.cine_cinco import CineCinco
from scrapers.llm_cache import hash_text

FIXTURE_DIR = "tests/files/files_cine_cinco/2026-07-19"


def _make_scraper(tmp_path):
    cine_cinco = CineCinco()
    cine_cinco.todays_dir = FIXTURE_DIR
    cine_cinco.cache_file = os.path.join(tmp_path, "cache.json")
    return cine_cinco


class TestGetContentSoup:
    def test_returns_div_content(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        soup = scraper._get_content_soup()
        assert soup.name == "div"
        assert "content" in soup.get("class", [])

    def test_raises_when_div_content_missing(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        missing_dir = tmp_path / "missing"
        missing_dir.mkdir()
        (missing_dir / "page.html").write_text(
            "<html><body>no programming here</body></html>"
        )
        scraper.todays_dir = str(missing_dir)

        with pytest.raises(ValueError, match="Could not find div.content"):
            scraper._get_content_soup()


class TestGetTextFromSoup:
    def test_strips_script_and_style(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        soup = BeautifulSoup(
            "<div><script>ignored();</script><style>.a{}</style>"
            "<p>Lucía e o Sexo</p></div>",
            "html.parser",
        )

        text = scraper._get_text_from_soup(soup)

        assert "ignored();" not in text
        assert ".a{}" not in text
        assert "Lucía e o Sexo" in text


class TestGetDailyFeaturesJson:
    def test_cache_hit_skips_llm_call(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        content_text = scraper._get_text_from_soup(scraper._get_content_soup())
        content_hash = hash_text(content_text)
        cached_features = [{"title": "Cached Movie", "excerpt": "..."}]
        with open(scraper.cache_file, "w") as f:
            json.dump({"content_hash": content_hash, "features": cached_features}, f)

        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            result = scraper.get_daily_features_json()

        mock_extractor_cls.assert_not_called()
        assert result == cached_features

    def test_cache_miss_calls_llm_and_saves_cache(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        llm_output = json.dumps(
            {
                "movies": [
                    {
                        "title": "Lucía e o Sexo",
                        "image_url": "https://example.com/poster.jpg",
                        "general_info": "Espanha/França/2001/128min",
                        "director": "Julio Medem",
                        "classification": "18 anos",
                        "excerpt": "sinopse",
                        "screening_dates": ["2026-07-01 17:00"],
                    }
                ]
            }
        )

        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = llm_output
            result = scraper.get_daily_features_json()

        mock_extractor_cls.return_value.extract_screenings_from_text.assert_called_once()
        assert result[0]["title"] == "Lucía e o Sexo"
        assert result[0]["read_more"] == scraper.url

        with open(scraper.cache_file) as f:
            cache = json.load(f)
        assert cache["features"] == result

    def test_stale_cache_triggers_refresh(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        with open(scraper.cache_file, "w") as f:
            json.dump({"content_hash": "stale-hash", "features": [{"title": "Old"}]}, f)
        llm_output = json.dumps({"movies": []})

        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = llm_output
            result = scraper.get_daily_features_json()

        mock_extractor_cls.return_value.extract_screenings_from_text.assert_called_once()
        assert result == []

    def test_llm_failure_with_existing_cache_falls_back(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        with open(scraper.cache_file, "w") as f:
            json.dump({"content_hash": "stale-hash", "features": [{"title": "Old"}]}, f)

        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = None
            result = scraper.get_daily_features_json()

        assert result == [{"title": "Old"}]
        with open(scraper.cache_file) as f:
            cache = json.load(f)
        assert cache["content_hash"] == "stale-hash"

    def test_llm_failure_without_cache_returns_empty_list(self, tmp_path):
        scraper = _make_scraper(tmp_path)

        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = None
            result = scraper.get_daily_features_json()

        assert result == []
        assert not os.path.exists(scraper.cache_file)
