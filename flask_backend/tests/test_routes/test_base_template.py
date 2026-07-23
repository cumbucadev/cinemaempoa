from unittest.mock import patch

from flask_backend.utils.enums.environment import EnvironmentEnum

DEV_BANNER_SNIPPET = "Ambiente de desenvolvimento"
USER_SKIP_MARKER_SNIPPET = 'style="display: none;" data-goatcounter-skip'


class TestBaseTemplateGoatcounterSkip:
    def test_shows_user_skip_marker_when_logged_in(self, auth_headers, setup_cinemas):
        with patch("flask_backend.APP_ENVIRONMENT", EnvironmentEnum.PRODUCTION):
            response = auth_headers.get("/")
        html = response.get_data(as_text=True)
        assert USER_SKIP_MARKER_SNIPPET in html
        assert DEV_BANNER_SNIPPET not in html

    def test_hides_user_skip_marker_when_logged_out(self, client, setup_cinemas):
        with patch("flask_backend.APP_ENVIRONMENT", EnvironmentEnum.PRODUCTION):
            response = client.get("/")
        html = response.get_data(as_text=True)
        assert USER_SKIP_MARKER_SNIPPET not in html
        assert DEV_BANNER_SNIPPET not in html

    def test_shows_dev_banner_skip_marker_when_not_production(
        self, client, setup_cinemas
    ):
        with patch("flask_backend.APP_ENVIRONMENT", EnvironmentEnum.DEVELOPMENT):
            response = client.get("/")
        html = response.get_data(as_text=True)
        assert DEV_BANNER_SNIPPET in html
        assert USER_SKIP_MARKER_SNIPPET not in html

    def test_shows_both_skip_markers_when_not_production_and_logged_in(
        self, auth_headers, setup_cinemas
    ):
        with patch("flask_backend.APP_ENVIRONMENT", EnvironmentEnum.DEVELOPMENT):
            response = auth_headers.get("/")
        html = response.get_data(as_text=True)
        assert DEV_BANNER_SNIPPET in html
        assert USER_SKIP_MARKER_SNIPPET in html
