from unittest.mock import MagicMock, patch

from flask_backend.service.runner import Runner


class TestRunnerInit:
    def test_init_with_no_cinemas_has_empty_features(self):
        runner = Runner([])
        assert runner.features == []

    def test_init_with_capitolio(self):
        with patch("flask_backend.service.runner.Capitolio") as mock_cls:
            runner = Runner(["capitolio"])
        assert len(runner.features) == 1
        feature = runner.features[0]
        assert feature["cls"] == mock_cls.return_value
        assert feature["slug"] == "capitolio"
        assert feature["cinema"] == "Cinemateca Capitólio"

    def test_init_with_redencao(self):
        with patch("flask_backend.service.runner.SalaRedencao") as mock_cls:
            runner = Runner(["redencao"])
        assert len(runner.features) == 1
        feature = runner.features[0]
        assert feature["cls"] == mock_cls.return_value
        assert feature["slug"] == "sala-redencao"
        assert feature["cinema"] == "Sala Redenção"

    def test_init_with_cinebancarios(self):
        with patch("flask_backend.service.runner.CineBancarios") as mock_cls:
            runner = Runner(["cinebancarios"])
        assert len(runner.features) == 1
        feature = runner.features[0]
        assert feature["cls"] == mock_cls.return_value
        assert feature["slug"] == "cinebancarios"
        assert feature["cinema"] == "CineBancários"

    def test_init_with_paulo_amorim(self):
        with patch("flask_backend.service.runner.CinematecaPauloAmorim") as mock_cls:
            runner = Runner(["pauloAmorim"])
        assert len(runner.features) == 1
        feature = runner.features[0]
        assert feature["cls"] == mock_cls.return_value
        assert feature["slug"] == "paulo-amorim"
        assert feature["cinema"] == "Cinemateca Paulo Amorim"

    def test_init_with_all_cinemas(self):
        with (
            patch("flask_backend.service.runner.Capitolio"),
            patch("flask_backend.service.runner.SalaRedencao"),
            patch("flask_backend.service.runner.CineBancarios"),
            patch("flask_backend.service.runner.CinematecaPauloAmorim"),
        ):
            runner = Runner(["capitolio", "redencao", "cinebancarios", "pauloAmorim"])
        assert len(runner.features) == 4
        assert {f["slug"] for f in runner.features} == {
            "capitolio",
            "sala-redencao",
            "cinebancarios",
            "paulo-amorim",
        }


class TestRunnerScrap:
    def test_scrap_calls_get_daily_features_json_for_each_cinema(self):
        runner = Runner([])
        mock_scraper = MagicMock()
        mock_scraper.get_daily_features_json.return_value = [{"title": "Filme"}]
        runner.features = [{"cls": mock_scraper}]

        runner.scrap()

        mock_scraper.get_daily_features_json.assert_called_once()
        assert runner.features[0]["features"] == [{"title": "Filme"}]


class TestRunnerParseScrappedJson:
    def _cinema_json(self):
        return {
            "url": "https://example.com",
            "cinema": "Cinemateca Capitólio",
            "slug": "capitolio",
            "features": [
                {
                    "poster": "",
                    "time": ["2026-08-01T19:00"],
                    "title": "Um Filme",
                    "original_title": "",
                    "price": "",
                    "director": "",
                    "classification": "",
                    "general_info": "",
                    "excerpt": "excerto",
                    "read_more": "",
                }
            ],
        }

    def test_parse_scrapped_json_with_explicit_features(self):
        runner = Runner([])
        runner.parse_scrapped_json([self._cinema_json()])
        assert runner.scrapped_results.cinemas[0].slug == "capitolio"

    def test_parse_scrapped_json_uses_self_features_by_default(self):
        runner = Runner([])
        runner.features = [self._cinema_json()]
        runner.parse_scrapped_json()
        assert runner.scrapped_results.cinemas[0].slug == "capitolio"


class TestRunnerImportScrappedResults:
    def test_import_scrapped_results_delegates_to_service(self):
        runner = Runner([])
        runner.scrapped_results = MagicMock()
        fake_app = MagicMock()

        with patch(
            "flask_backend.service.runner.import_scrapped_results",
            return_value=5,
        ) as mock_import:
            result = runner.import_scrapped_results(fake_app)

        mock_import.assert_called_once_with(runner.scrapped_results, fake_app)
        assert result == 5
