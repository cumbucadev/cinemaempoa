from unittest.mock import MagicMock, patch

from flask_backend.service.runner import Runner


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
        runner = Runner()
        runner.parse_scrapped_json([self._cinema_json()])
        assert runner.scrapped_results.cinemas[0].slug == "capitolio"


class TestRunnerImportScrappedResults:
    def test_import_scrapped_results_delegates_to_service(self):
        runner = Runner()
        runner.scrapped_results = MagicMock()
        fake_app = MagicMock()

        with patch(
            "flask_backend.service.runner.import_scrapped_results",
            return_value=5,
        ) as mock_import:
            result = runner.import_scrapped_results(fake_app)

        mock_import.assert_called_once_with(
            runner.scrapped_results, fake_app, pipeline_run_id=None
        )
        assert result == 5
