"""
Tests the basic functionality of /movies and /movies/<slug> endpoints.
"""

from datetime import date

import pytest
from faker import Faker
from slugify import slugify

from flask_backend.db import db_session
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate


def create_sample_movies(app, quantity, should_draft):
    faker = Faker()
    with app.app_context():
        # Get cinemas (they should be created by setup_cinemas)
        cinemas = db_session.query(Cinema).all()
        if not cinemas:
            pytest.fail("Configuration is invalid, cannot proceed with test")

        cinema = cinemas[0]  # Use first cinema for all screenings

        movies = []
        for i in range(0, quantity):
            _title = faker.name()
            _slug = slugify(_title)
            movie = Movie(
                title=_title,
                slug=slugify(_title),
                screenings=[
                    Screening(
                        cinema_id=cinema.id,
                        description=f"Description for {_title}",
                        draft=should_draft,
                        url=f"http://example.com/{_slug}",
                        dates=[ScreeningDate(date=date(2025, 1, 1 + i), time="19:00")],
                    )
                ],
            )
            db_session.add(movie)
            movies.append(movie)
        db_session.commit()

        return movies


@pytest.fixture
def sample_movies_with_screenings(app, setup_cinemas):
    """Create a set of movies with screenings for testing pagination and search."""
    return create_sample_movies(app, 20, should_draft=False)


@pytest.fixture
def additional_draft_movies(app, setup_cinemas):
    """Create additional movies with only draft screenings to test draft filtering."""
    return create_sample_movies(app, 5, should_draft=True)


class TestMoviesIndex:
    """Test cases for public movie index (/movies)."""

    def test_movies_index_returns_200(self, client):
        """Test that the movies index page returns 200 OK."""
        response = client.get("/movies")
        assert response.status_code == 200

    def test_movies_index_with_empty_database(self, client):
        """Test movies index with no movies in database."""
        response = client.get("/movies")
        assert response.status_code == 200
        # Should show 0 movies
        assert b"Total de filmes encontrados: 0." in response.data

    def test_movies_index_shows_movies(self, client, sample_movies_with_screenings):
        """Test that movies are displayed on the index page."""
        response = client.get("/movies")
        assert response.status_code == 200
        # Should show at least one movie title
        assert b"Total de filmes encontrados: 0" not in response.data

    def test_movies_index_hides_draft_movies_when_not_logged_in(
        self, client, sample_movies_with_screenings, additional_draft_movies
    ):
        """Test that draft movies are hidden when user is not logged in."""
        response = client.get("/movies")
        assert response.status_code == 200
        assert (
            len(additional_draft_movies) > 0
        ), "Should have seeded the database for this test"
        assert (
            len(sample_movies_with_screenings) > 0
        ), "Should have seeded the database for this test"
        # Draft movies should not appear
        expected_test = (
            f"Total de filmes encontrados: {len(sample_movies_with_screenings)}"
        )
        assert expected_test.encode("utf-8") in response.data

    def test_movies_index_shows_draft_movies_when_logged_in(
        self,
        client,
        sample_movies_with_screenings,
        additional_draft_movies,
        auth_headers,
    ):
        """Test that draft movies are shown when user is logged in."""
        response = auth_headers.get("/movies")
        assert response.status_code == 200
        assert response.status_code == 200
        assert (
            len(additional_draft_movies) > 0
        ), "Should have seeded the database for this test"
        assert (
            len(sample_movies_with_screenings) > 0
        ), "Should have seeded the database for this test"
        # Draft movies should appear when logged in
        expected_test = f"Total de filmes encontrados: {len(sample_movies_with_screenings) + len(additional_draft_movies)}"
        assert expected_test.encode("utf-8") in response.data
