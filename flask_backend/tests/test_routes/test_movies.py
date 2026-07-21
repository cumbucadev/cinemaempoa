"""
Tests the basic functionality of /movies and /movies/<slug> endpoints.
"""

from datetime import date

import pytest
from faker import Faker
from slugify import slugify

from flask_backend.db import db_session
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate
from flask_backend.repository import movies as movies_repository


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

    def test_movies_index_deduplicates_movie_with_multiple_screenings(
        self, client, app, setup_cinemas
    ):
        """A movie joined to more than one screening must be listed once,
        and counted once in the total, not once per screening."""
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="s1",
                    draft=False,
                    url="http://example.com/1",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                ),
                Screening(
                    cinema_id=cinema.id,
                    description="s2",
                    draft=False,
                    url="http://example.com/2",
                    dates=[ScreeningDate(date=date(2026, 8, 2), time="21:00")],
                ),
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies")
        assert response.status_code == 200
        assert b"Total de filmes encontrados: 1" in response.data
        assert response.data.count(b"Filme Duplicado") == 1


class TestMoviesRepositoryDistinct:
    """Regression tests for the `distinct()` clauses in get_all/get_all_paginated:
    a movie joined to multiple screenings must be returned/counted once."""

    def _create_movie_with_screenings(self, cinema, title, slug, screening_count):
        movie = Movie(title=title, slug=slug)
        movie.screenings = [
            Screening(
                cinema_id=cinema.id,
                description=f"screening {i}",
                draft=False,
                url=f"http://example.com/{slug}/{i}",
                dates=[ScreeningDate(date=date(2026, 8, 1 + i), time="19:00")],
            )
            for i in range(screening_count)
        ]
        db_session.add(movie)
        db_session.commit()
        return movie

    def test_get_all_returns_movie_once_regardless_of_screening_count(
        self, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            self._create_movie_with_screenings(
                cinema, "Filme com Varias Sessoes", "filme-com-varias-sessoes", 3
            )

            movies = movies_repository.get_all()
            assert len(movies) == 1

    def test_get_all_paginated_counts_movie_once_regardless_of_screening_count(
        self, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            self._create_movie_with_screenings(
                cinema, "Filme com Varias Sessoes", "filme-com-varias-sessoes", 3
            )

            movies, total_pages, total_count = movies_repository.get_all_paginated(
                movie="", current_page=1, per_page=10, include_drafts=False
            )
            assert total_count == 1
            assert len(movies) == 1
            assert total_pages == 1


class TestMoviesPosters:
    def test_posters_returns_200(self, client):
        response = client.get("/movies/posters")
        assert response.status_code == 200

    def test_posters_cubism_returns_200(self, client):
        response = client.get("/movies/posters/cubism")
        assert response.status_code == 200

    def test_posters_cubism_accepts_crop_position(self, client):
        response = client.get("/movies/posters/cubism?crop_position=cover")
        assert response.status_code == 200


class TestMoviesPosterImages:
    def test_requires_lazy_load_header(self, client):
        response = client.get("/movies/posters/images")
        assert response.status_code == 400

    def test_invalid_page_returns_400(self, client):
        response = client.get(
            "/movies/posters/images?page=invalid", headers={"X-LAZY-LOAD": "1"}
        )
        assert response.status_code == 400

    def test_no_screenings_returns_404(self, client):
        response = client.get("/movies/posters/images", headers={"X-LAZY-LOAD": "1"})
        assert response.status_code == 404

    def test_returns_images_for_screenings_with_posters(
        self, client, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Com Poster", slug="filme-com-poster")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/posters/images", headers={"X-LAZY-LOAD": "1"})
        assert response.status_code == 200
        assert b"poster.jpg" in response.data

    def test_returns_movie_slug_for_each_image(self, client, app, setup_cinemas):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Com Poster", slug="filme-com-poster")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/posters/images", headers={"X-LAZY-LOAD": "1"})
        assert response.status_code == 200
        assert b'data-movie-slug="filme-com-poster"' in response.data

    def test_includes_image_alt_when_present(self, client, app, setup_cinemas):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Com Alt", slug="filme-com-alt")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster-alt.jpg",
                    image_alt="Descrição alternativa do poster",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/posters/images", headers={"X-LAZY-LOAD": "1"})
        assert response.status_code == 200
        assert 'alt="Descrição alternativa do poster"' in response.get_data(
            as_text=True
        )

    def test_omits_alt_attribute_when_image_alt_missing(
        self, client, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Sem Alt", slug="filme-sem-alt")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster-sem-alt.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/posters/images", headers={"X-LAZY-LOAD": "1"})
        assert response.status_code == 200
        assert "alt=" not in response.get_data(as_text=True)

    def test_skips_screenings_without_poster_when_paginating(
        self, client, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()

            movie_with_poster = Movie(title="Filme Com Poster", slug="filme-com-poster")
            movie_with_poster.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie_with_poster)
            db_session.commit()

            # More recent screenings (higher id, sorted first) with no poster
            # yet must not push the page-1 result set empty.
            movie_without_poster = Movie(
                title="Filme Sem Poster", slug="filme-sem-poster"
            )
            movie_without_poster.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
                for _ in range(4)
            ]
            db_session.add(movie_without_poster)
            db_session.commit()

        response = client.get("/movies/posters/images", headers={"X-LAZY-LOAD": "1"})
        assert response.status_code == 200
        assert b"poster.jpg" in response.data


class TestMoviesPosterImagesUrls:
    def test_invalid_page_returns_400(self, client):
        response = client.get("/movies/posters/images/urls?page=invalid")
        assert response.status_code == 400

    def test_no_screenings_returns_404(self, client):
        response = client.get("/movies/posters/images/urls")
        assert response.status_code == 404

    def test_returns_unique_image_urls(self, client, app, setup_cinemas):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Com Poster", slug="filme-com-poster")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster.jpg",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/posters/images/urls")
        assert response.status_code == 200
        assert response.get_json() == ["poster.jpg"]


class TestMoviesSearch:
    def test_requires_login(self, client):
        response = client.get("/movies/search?title=x")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_matching_titles(
        self, auth_headers, app, sample_movies_with_screenings
    ):
        with app.app_context():
            target_title = db_session.query(Movie).first().title
        response = auth_headers.get(f"/movies/search?title={target_title}")
        assert response.status_code == 200
        titles = [item["title"] for item in response.get_json()]
        assert target_title in titles


class TestMovieShow:
    def test_unknown_slug_returns_400(self, client):
        response = client.get("/movies/does-not-exist")
        assert response.status_code == 400

    def test_shows_movie_with_images(self, client, app, setup_cinemas):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Individual", slug="filme-individual")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster.jpg",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/filme-individual")
        assert response.status_code == 200
        assert b"Filme Individual" in response.data

    def test_carousel_opens_on_selected_screening(self, client, app, setup_cinemas):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Com Varias Sessoes", slug="filme-varias-sessoes")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d1",
                    image="poster-um.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                ),
                Screening(
                    cinema_id=cinema.id,
                    description="d2",
                    image="poster-dois.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 2), time="20:00")],
                ),
            ]
            db_session.add(movie)
            db_session.commit()
            second_screening_id = movie.screenings[1].id

        response = client.get(
            f"/movies/filme-varias-sessoes?screening={second_screening_id}"
        )
        assert response.status_code == 200
        html = response.data.decode()
        first_slide = html[
            html.index("poster-um.jpg") - 200 : html.index("poster-um.jpg")
        ]
        second_slide = html[
            html.index("poster-dois.jpg") - 200 : html.index("poster-dois.jpg")
        ]
        assert "active" not in first_slide
        assert "active" in second_slide

    def test_invalid_screening_falls_back_to_first_slide(
        self, client, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(
                title="Filme Com Sessao Invalida", slug="filme-sessao-invalida"
            )
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d1",
                    image="poster-um.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                ),
                Screening(
                    cinema_id=cinema.id,
                    description="d2",
                    image="poster-dois.jpg",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 2), time="20:00")],
                ),
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/filme-sessao-invalida?screening=999999")
        assert response.status_code == 200
        html = response.data.decode()
        first_slide = html[
            html.index("poster-um.jpg") - 200 : html.index("poster-um.jpg")
        ]
        second_slide = html[
            html.index("poster-dois.jpg") - 200 : html.index("poster-dois.jpg")
        ]
        assert "active" in first_slide
        assert "active" not in second_slide

    def test_shows_alt_badge_for_single_image_when_image_alt_present(
        self, client, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Show Alt", slug="filme-show-alt")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster.jpg",
                    image_alt="Descrição do poster único",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/filme-show-alt")
        html = response.get_data(as_text=True)
        assert 'class="alt-badge' in html
        assert 'data-bs-content="Descrição do poster único"' in html

    def test_hides_alt_badge_for_single_image_when_image_alt_missing(
        self, client, app, setup_cinemas
    ):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Show Sem Alt", slug="filme-show-sem-alt")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d",
                    image="poster.jpg",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/filme-show-sem-alt")
        html = response.get_data(as_text=True)
        assert 'class="alt-badge' not in html

    def test_shows_alt_badge_on_each_carousel_slide(self, client, app, setup_cinemas):
        with app.app_context():
            cinema = db_session.query(Cinema).first()
            movie = Movie(title="Filme Carrossel Alt", slug="filme-carrossel-alt")
            movie.screenings = [
                Screening(
                    cinema_id=cinema.id,
                    description="d1",
                    image="poster-um.jpg",
                    image_alt="Alt do poster um",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                ),
                Screening(
                    cinema_id=cinema.id,
                    description="d2",
                    image="poster-dois.jpg",
                    image_alt="Alt do poster dois",
                    image_width=100,
                    image_height=200,
                    dates=[ScreeningDate(date=date(2026, 8, 2), time="20:00")],
                ),
            ]
            db_session.add(movie)
            db_session.commit()

        response = client.get("/movies/filme-carrossel-alt")
        html = response.get_data(as_text=True)
        assert html.count('class="alt-badge') == 2
        assert 'data-bs-content="Alt do poster um"' in html
        assert 'data-bs-content="Alt do poster dois"' in html
