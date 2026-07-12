"""Tests for /api/* endpoints (import and poster APIs)."""

import pytest

from web import create_app
from web.db import db_session
from web.env_config import APP_ENVIRONMENT
from web.models import Cinema, Movie, PosterFetchAttempt, Screening, ScreeningDate
from web.seeds.cinema_seeds import create_cinemas
from web.utils.enums.environment import EnvironmentEnum

VALID_TOKEN = "test-token-abc"

VALID_CINEMA_BODY = [
    {
        "url": "https://www.capitolio.org.br",
        "cinema": "Cinemateca Capitólio",
        "slug": "capitolio",
        "features": [
            {
                "poster": None,
                "time": "14h",
                "title": "Filme Teste",
                "original_title": None,
                "price": None,
                "director": None,
                "classification": None,
                "general_info": None,
                "excerpt": "Uma descrição do filme.",
                "read_more": None,
            }
        ],
    }
]


@pytest.fixture()
def app():
    if APP_ENVIRONMENT == EnvironmentEnum.PRODUCTION:
        pytest.exit("Absolutely no testing in production")
    app = create_app({"TESTING": True})
    with app.app_context():
        from web.db import init_db
        init_db()
    yield app


@pytest.fixture(autouse=True)
def clean_db(app):
    with app.app_context():
        db_session.query(PosterFetchAttempt).delete()
        db_session.query(ScreeningDate).delete()
        db_session.query(Screening).delete()
        db_session.query(Movie).delete()
        db_session.query(Cinema).delete()
        db_session.commit()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def setup_cinemas(app):
    with app.app_context():
        create_cinemas(db_session)


@pytest.fixture()
def auth_header():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


@pytest.fixture()
def configured_token(monkeypatch):
    import web.routes.api as api_module
    monkeypatch.setattr(api_module, "IMPORT_API_TOKEN", VALID_TOKEN)


class TestImportEndpoint:
    def test_valid_import_creates_screenings(self, client, setup_cinemas, auth_header, configured_token):
        response = client.post(
            "/api/import",
            json=VALID_CINEMA_BODY,
            headers=auth_header,
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "created" in data
        assert data["created"] >= 1

    def test_missing_auth_header_returns_401(self, client, configured_token):
        response = client.post("/api/import", json=VALID_CINEMA_BODY)
        assert response.status_code == 401

    def test_wrong_token_returns_401(self, client, configured_token):
        response = client.post(
            "/api/import",
            json=VALID_CINEMA_BODY,
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401

    def test_malformed_body_returns_400(self, client, auth_header, configured_token):
        response = client.post(
            "/api/import",
            data="not json",
            content_type="application/json",
            headers=auth_header,
        )
        assert response.status_code == 400

    def test_non_array_body_returns_400(self, client, auth_header, configured_token):
        response = client.post(
            "/api/import",
            json={"cinema": "capitolio"},
            headers=auth_header,
        )
        assert response.status_code == 400

    def test_unknown_cinema_slug_returns_422(self, client, setup_cinemas, auth_header, configured_token):
        body = [
            {
                "url": "https://example.com",
                "cinema": "Unknown",
                "slug": "nonexistent-slug",
                "features": [],
            }
        ]
        response = client.post("/api/import", json=body, headers=auth_header)
        assert response.status_code == 422

    def test_unconfigured_token_returns_500(self, client, monkeypatch):
        import web.routes.api as api_module
        monkeypatch.setattr(api_module, "IMPORT_API_TOKEN", None)
        response = client.post(
            "/api/import",
            json=VALID_CINEMA_BODY,
            headers={"Authorization": "Bearer anything"},
        )
        assert response.status_code == 500


class TestMissingPostersEndpoint:
    def test_returns_empty_list_when_no_screenings(self, client, auth_header, configured_token):
        response = client.get("/api/screenings/missing-posters", headers=auth_header)
        assert response.status_code == 200
        assert response.get_json() == []

    def test_unauthorized_returns_401(self, client, configured_token):
        response = client.get("/api/screenings/missing-posters")
        assert response.status_code == 401


@pytest.fixture()
def seeded_screening(app, setup_cinemas):
    with app.app_context():
        from web.repository.movies import create as create_movie
        from web.repository.screenings import create as create_screening
        from web.repository.cinemas import get_by_slug as get_cinema_by_slug
        from web.models import ScreeningDate
        from datetime import date

        movie = create_movie("Filme de Teste")
        cinema = get_cinema_by_slug("capitolio")
        screening = create_screening(
            movie_id=movie.id,
            description="desc",
            cinema_id=cinema.id,
            screening_dates=[ScreeningDate(date=date(2025, 12, 25), time="14:00")],
            image=None,
            image_width=None,
            image_height=None,
        )
        return screening.id


class TestUpdatePosterEndpoint:
    def test_screening_not_found_returns_404(self, client, auth_header, configured_token):
        response = client.patch(
            "/api/screenings/99999/poster",
            json={"url": "https://example.com/image.jpg", "source": "tmdb"},
            headers=auth_header,
        )
        assert response.status_code == 404

    def test_unauthorized_returns_401(self, client, configured_token):
        response = client.patch(
            "/api/screenings/1/poster",
            json={"url": "https://example.com/image.jpg", "source": "tmdb"},
        )
        assert response.status_code == 401

    def test_bad_url_returns_422_and_records_error_attempt(
        self, app, client, auth_header, configured_token, seeded_screening, monkeypatch
    ):
        import web.routes.api as api_module
        monkeypatch.setattr(api_module, "download_image_from_url", lambda url: (None, None))

        response = client.patch(
            f"/api/screenings/{seeded_screening}/poster",
            json={"url": "https://bad-url.example.com/image.jpg", "source": "tmdb"},
            headers=auth_header,
        )

        assert response.status_code == 422

        with app.app_context():
            attempts = db_session.query(PosterFetchAttempt).filter_by(
                screening_id=seeded_screening
            ).all()
            assert len(attempts) == 1
            assert attempts[0].status == "error"
            assert attempts[0].source == "tmdb"

    def test_success_updates_screening_and_records_attempt(
        self, app, client, auth_header, configured_token, seeded_screening, monkeypatch
    ):
        import web.routes.api as api_module
        monkeypatch.setattr(
            api_module, "download_image_from_url", lambda url: (b"imgbytes", "poster.jpg")
        )
        monkeypatch.setattr(
            api_module, "save_image", lambda img, app, filename: ("saved_poster.jpg", 800, 600)
        )

        response = client.patch(
            f"/api/screenings/{seeded_screening}/poster",
            json={"url": "https://example.com/poster.jpg", "source": "imdb"},
            headers=auth_header,
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data == {"image": "saved_poster.jpg"}

        with app.app_context():
            screening = db_session.query(Screening).filter_by(id=seeded_screening).one()
            assert screening.image == "saved_poster.jpg"
            assert screening.image_width == 800
            assert screening.image_height == 600

            attempts = db_session.query(PosterFetchAttempt).filter_by(
                screening_id=seeded_screening
            ).all()
            assert len(attempts) == 1
            assert attempts[0].status == "success"
            assert attempts[0].source == "imdb"
