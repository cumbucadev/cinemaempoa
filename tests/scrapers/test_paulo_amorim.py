from datetime import date, datetime
from unittest.mock import MagicMock, patch

from scrapers.paulo_amorim import CinematecaPauloAmorim

FIXTURE_DIR = "tests/files/files_paulo-amorim"
FIXTURE_DAY_DIR = f"{FIXTURE_DIR}/2026-08-05"


def _make_scraper():
    scraper = CinematecaPauloAmorim()
    scraper.dir = FIXTURE_DIR
    scraper.todays_dir = FIXTURE_DAY_DIR
    return scraper


class TestGetWeeklyFeaturesJson:
    def test_parses_movie_from_programacao_grade_and_detail_pages(self):
        with patch("scrapers.paulo_amorim.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 5)
            scraper = _make_scraper()
            features = scraper.get_weekly_features_json()

        assert len(features) == 1
        feature = features[0]
        assert feature["title"] == "Nome Do Filme"
        assert feature["director"] == "Direção: Fulano de Tal"
        assert feature["classification"] == "14 anos"
        assert feature["genre"] == "Drama"
        assert feature["room"] == "Sala 1"
        assert feature["general_info"] == "Brasil, 2024, 100 min | Sala 1 | Drama"
        assert feature["excerpt"] == "Um resumo do filme aqui."
        assert feature["time"] == ["2026-08-05T14:30"]
        assert (
            feature["read_more"]
            == "https://www.cinematecapauloamorim.com.br/programacao/1234/nome-do-filme"
        )
        assert (
            feature["poster"]
            == "https://www.cinematecapauloamorim.com.br//uploads/poster.jpg"
        )

    def test_get_daily_features_json_is_an_alias(self):
        with patch("scrapers.paulo_amorim.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 5)
            scraper = _make_scraper()
            features = scraper.get_daily_features_json()

        assert len(features) == 1


class TestParseDateFromStrongText:
    def _scraper(self):
        return CinematecaPauloAmorim()

    def test_en_dash_separator(self):
        with patch("scrapers.paulo_amorim.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            result = self._scraper()._parse_date_from_strong_text(
                "30 de julho – quarta-feira"
            )
        assert result == date(2026, 7, 30)

    def test_pipe_separator(self):
        with patch("scrapers.paulo_amorim.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            result = self._scraper()._parse_date_from_strong_text(
                "8 de dezembro | sexta"
            )
        assert result == date(2026, 12, 8)

    def test_no_recognized_separator_returns_none(self):
        result = self._scraper()._parse_date_from_strong_text("30 de julho")
        assert result is None

    def test_missing_de_returns_none(self):
        result = self._scraper()._parse_date_from_strong_text("30 julho – quarta")
        assert result is None

    def test_unknown_month_returns_none(self):
        result = self._scraper()._parse_date_from_strong_text(
            "30 de mesinventado – quarta"
        )
        assert result is None

    def test_non_numeric_day_returns_none(self):
        result = self._scraper()._parse_date_from_strong_text(
            "trinta de julho – quarta"
        )
        assert result is None


class TestGetPageHtml:
    def test_reads_from_cache_when_present(self):
        scraper = _make_scraper()
        html = scraper._get_page_html(
            f"{FIXTURE_DAY_DIR}/grade.html", "https://example.com/grade"
        )
        assert "5 de agosto" in html

    def test_fetches_and_caches_when_missing(self, tmp_path):
        scraper = CinematecaPauloAmorim()
        scraper.dir = str(tmp_path)
        scraper.todays_dir = str(tmp_path)

        mock_response = MagicMock(text="<html>fetched</html>")
        with patch(
            "scrapers.paulo_amorim.requests.Session.get", return_value=mock_response
        ) as mock_get:
            html = scraper._get_page_html(
                str(tmp_path / "new.html"), "https://example.com/new"
            )

        mock_get.assert_called_once()
        assert html == "<html>fetched</html>"
        assert (tmp_path / "new.html").read_text() == "<html>fetched</html>"
