from unittest.mock import MagicMock, patch

from flask_backend.utils.enums.environment import EnvironmentEnum
from scrapers.http_cache import fetch_page


class TestFetchPage:
    def test_reads_from_cache_when_present(self, tmp_path):
        cache_path = tmp_path / "page.html"
        cache_path.write_text("<html>cached</html>")

        fetch = MagicMock()
        html = fetch_page(str(cache_path), fetch)

        assert html == "<html>cached</html>"
        fetch.assert_not_called()

    def test_fetches_and_caches_when_missing(self, tmp_path):
        cache_path = tmp_path / "page.html"
        mock_response = MagicMock(text="<html>fetched</html>")
        fetch = MagicMock(return_value=mock_response)

        html = fetch_page(str(cache_path), fetch)

        fetch.assert_called_once()
        mock_response.raise_for_status.assert_called_once()
        assert html == "<html>fetched</html>"
        assert cache_path.read_text() == "<html>fetched</html>"

    def test_production_never_reads_or_writes_cache(self, tmp_path):
        cache_path = tmp_path / "page.html"
        cache_path.write_text("<html>stale</html>")
        mock_response = MagicMock(text="<html>fresh</html>")
        fetch = MagicMock(return_value=mock_response)

        with patch("scrapers.http_cache.APP_ENVIRONMENT", EnvironmentEnum.PRODUCTION):
            html = fetch_page(str(cache_path), fetch)

        fetch.assert_called_once()
        assert html == "<html>fresh</html>"
        assert cache_path.read_text() == "<html>stale</html>"
