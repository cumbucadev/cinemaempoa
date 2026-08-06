import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from flask_backend.utils.enums.environment import EnvironmentEnum
from scrapers.capitolio import Capitolio

FIXTURE_DIR = os.path.join("tests/files/files_capitolio")


def _make_capitolio():
    capitolio = Capitolio()
    capitolio.dir = FIXTURE_DIR
    return capitolio


class TestCapitolio:
    def test_get_weekly_features_json_parses_movie_and_stops_at_empty_day(self):
        with patch("scrapers.capitolio.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 5)
            mock_dt.strptime = datetime.strptime
            capitolio = _make_capitolio()
            features = capitolio.get_weekly_features_json()

        assert len(features) == 2

        oldboy = features[0]
        assert oldboy["title"] == "Oldboy"
        assert oldboy["poster"] == "https://example.com/poster.jpg"
        assert oldboy["time"] == ["2026-08-05T19:30h"]
        assert oldboy["read_more"] == "https://www.capitolio.org.br/filme/oldboy"
        assert oldboy["general_info"] == (
            "Oldboy | R$ 20\n"
            "Coreia do Sul, 2003, 120 min\n"
            "Direção: Park Chan-wook\n"
            "Classificação: 16 anos"
        )
        assert oldboy["excerpt"] == "Um belo resumo do filme."
        # excerpt content must not also appear inside general_info, and
        # vice versa - this is the duplication bug from #222.
        assert oldboy["excerpt"] not in oldboy["general_info"]
        assert oldboy["general_info"] not in oldboy["excerpt"]
        # field-level parsing (director/classification/original_title/
        # price) is no longer performed by this scraper.
        assert "director" not in oldboy
        assert "classification" not in oldboy
        assert "original_title" not in oldboy
        assert "price" not in oldboy

        ninotchka = features[1]
        assert ninotchka["title"] == "Ninotchka"
        assert ninotchka["general_info"] == (
            "Ninotchka - Entrada franca\n"
            "Estados Unidos, 1939, 110 min\n"
            "Classificação: Livre"
        )
        assert ninotchka["excerpt"] == "Uma comissária soviética se apaixona por Paris."
        assert ninotchka["excerpt"] not in ninotchka["general_info"]
        # the old subtitle-parsing fallback text must never appear.
        assert "Não informado" not in ninotchka["general_info"]
        assert "Não informado" not in ninotchka["excerpt"]

    def test_get_daily_features_json_is_an_alias(self):
        with patch("scrapers.capitolio.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 5)
            mock_dt.strptime = datetime.strptime
            capitolio = _make_capitolio()
            features = capitolio.get_daily_features_json()

        assert len(features) == 2

    def test_day_schedule_html_reads_from_cache_when_present(self):
        capitolio = _make_capitolio()
        html = capitolio._day_schedule_html("2026-08-05")
        assert "Oldboy" in html

    def test_day_schedule_html_fetches_and_caches_when_missing(self, tmp_path):
        capitolio = Capitolio()
        capitolio.dir = str(tmp_path)

        mock_response = MagicMock(text="<html>fetched</html>")
        with patch(
            "scrapers.capitolio.requests.get", return_value=mock_response
        ) as mock_get:
            html = capitolio._day_schedule_html("2026-09-01")

        mock_get.assert_called_once()
        assert html == "<html>fetched</html>"
        cached_file = tmp_path / "2026-09-01.html"
        assert cached_file.read_text() == "<html>fetched</html>"

    def test_day_schedule_html_does_not_cache_in_production(self, tmp_path):
        capitolio = Capitolio()
        capitolio.dir = str(tmp_path)

        mock_response = MagicMock(text="<html>live</html>")
        with (
            patch("scrapers.http_cache.APP_ENVIRONMENT", EnvironmentEnum.PRODUCTION),
            patch("scrapers.capitolio.requests.get", return_value=mock_response),
        ):
            html = capitolio._day_schedule_html("2026-09-02")

        assert html == "<html>live</html>"
        assert not (tmp_path / "2026-09-02.html").exists()
