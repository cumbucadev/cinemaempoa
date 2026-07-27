"""
Tests the basic functionality of /cinemas and /cinemas/<slug> endpoints.
"""

from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository import cinemas
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


def _create_screening(app, title, slug, screening_date, cinema_slug="capitolio"):
    with app.app_context():
        movie = Movie(title=title, slug=slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug(cinema_slug)
        screening = Screening(
            movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
        )
        db_session.add(screening)
        db_session.commit()
        db_session.add(
            ScreeningDate(screening_id=screening.id, date=screening_date, time="20:00")
        )
        db_session.commit()


def _populate_cinema_profile(app, slug="capitolio"):
    with app.app_context():
        cinema = get_cinema_by_slug(slug)
        cinemas.update(
            cinema,
            name=cinema.name,
            url=cinema.url,
            address="Rua Fictícia, 123",
            opening_hours="Ter-Dom 14h-22h",
            instagram_url="https://instagram.com/capitolio-fake",
            map_embed_url="https://maps.example.com/embed/capitolio-fake",
            photo="https://example.com/capitolio-photo.jpg",
            photo_width=800,
            photo_height=600,
        )


class TestCinemaIndex:
    def test_returns_200_and_lists_cinemas(self, client, setup_cinemas):
        response = client.get("/cinemas")
        assert response.status_code == 200
        assert "Cinemateca Capitólio" in response.get_data(as_text=True)

    def test_renders_photo_for_fully_populated_cinema(self, app, client, setup_cinemas):
        _populate_cinema_profile(app)

        response = client.get("/cinemas")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "https://example.com/capitolio-photo.jpg" in body


class TestCinemaShow:
    def test_returns_200_for_known_slug(self, client, setup_cinemas):
        response = client.get("/cinemas/capitolio")
        assert response.status_code == 200

    def test_returns_404_for_unknown_slug(self, client, setup_cinemas):
        response = client.get("/cinemas/does-not-exist")
        assert response.status_code == 404

    def test_shows_upcoming_and_past_movies(self, app, client, setup_cinemas):
        _create_screening(
            app, "Filme Futuro", "filme-futuro", date.today() + timedelta(days=1)
        )
        _create_screening(
            app, "Filme Antigo", "filme-antigo", date.today() - timedelta(days=1)
        )

        response = client.get("/cinemas/capitolio")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Filme Futuro" in body
        assert "Filme Antigo" in body

    def test_renders_all_profile_fields_for_fully_populated_cinema(
        self, app, client, setup_cinemas
    ):
        _populate_cinema_profile(app)

        response = client.get("/cinemas/capitolio")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "https://example.com/capitolio-photo.jpg" in body
        assert "https://maps.example.com/embed/capitolio-fake" in body
        assert "https://instagram.com/capitolio-fake" in body
