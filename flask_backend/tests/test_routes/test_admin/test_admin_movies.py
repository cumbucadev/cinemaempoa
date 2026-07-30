"""
Tests the basic functionality of /admin/movies/* endpoints.
"""

from unittest.mock import patch

import requests

from flask_backend.db import db_session
from flask_backend.models import Director, Genre, Movie


def _create_movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=None):
    movie = Movie(title=title, slug=slug, tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


class TestAdminMoviesEdit:
    def test_requires_login(self, client):
        with client.application.app_context():
            movie_id = _create_movie().id

        response = client.get(f"/admin/movies/{movie_id}")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_missing_movie(self, auth_headers):
        response = auth_headers.get("/admin/movies/99999")
        assert response.status_code == 404

    def test_returns_200_with_auth(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        response = auth_headers.get(f"/admin/movies/{movie_id}")
        assert response.status_code == 200
        assert b"Filme de Teste" in response.data


class TestAdminMoviesTmdbSearch:
    def test_requires_login(self, client):
        with client.application.app_context():
            movie_id = _create_movie().id

        response = client.get(f"/admin/movies/{movie_id}/tmdb-search?q=filme")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_candidates_as_json(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        search_results = [
            {
                "id": 42,
                "title": "Um Filme",
                "original_title": "A Movie",
                "release_date": "2020-05-01",
                "poster_path": "/poster.jpg",
            }
        ]
        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.search_movies.return_value = search_results
            response = auth_headers.get(
                f"/admin/movies/{movie_id}/tmdb-search?q=Um Filme"
            )

        assert response.status_code == 200
        assert response.json == [
            {
                "tmdb_id": 42,
                "title": "Um Filme",
                "original_title": "A Movie",
                "release_year": 2020,
                "poster_url": "https://image.tmdb.org/t/p/w92/poster.jpg",
            }
        ]

    def test_returns_empty_list_for_blank_query(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        response = auth_headers.get(f"/admin/movies/{movie_id}/tmdb-search?q=")
        assert response.status_code == 200
        assert response.json == []

    def test_returns_502_on_tmdb_failure(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.search_movies.side_effect = (
                requests.RequestException("boom")
            )
            response = auth_headers.get(f"/admin/movies/{movie_id}/tmdb-search?q=x")

        assert response.status_code == 502


class TestAdminMoviesTmdbLink:
    def test_requires_login(self, client):
        with client.application.app_context():
            movie_id = _create_movie().id

        response = client.post(
            f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 42}
        )
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_persists_tmdb_id_and_relations(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        details = {
            "genres": [{"id": 28, "name": "Ação"}],
            "directors": [{"id": 42, "name": "Jane Director"}],
            "countries": [],
            "original_title": "Original",
            "release_year": 2021,
            "original_language": "en",
        }
        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.get_movie_details.return_value = details
            response = auth_headers.post(
                f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 555}
            )

        assert response.status_code == 200
        assert response.json["tmdb_id"] == 555
        assert response.json["directors"] == ["Jane Director"]
        assert response.json["genres"] == ["Ação"]

        with client.application.app_context():
            updated = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert updated.tmdb_id == 555
            assert [d.name for d in updated.directors] == ["Jane Director"]

    def test_relinking_to_different_tmdb_id_replaces_relations(
        self, client, auth_headers
    ):
        with client.application.app_context():
            movie_id = _create_movie().id

        details_a = {
            "genres": [{"id": 28, "name": "Ação"}],
            "directors": [{"id": 1, "name": "Director A"}],
            "countries": [],
            "original_title": "Title A",
            "release_year": 2001,
            "original_language": "en",
        }
        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.get_movie_details.return_value = details_a
            response = auth_headers.post(
                f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 111}
            )
        assert response.status_code == 200
        assert response.json["directors"] == ["Director A"]
        assert response.json["genres"] == ["Ação"]

        details_b = {
            "genres": [{"id": 35, "name": "Comédia"}],
            "directors": [{"id": 2, "name": "Director B"}],
            "countries": [],
            "original_title": "Title B",
            "release_year": 2002,
            "original_language": "fr",
        }
        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.get_movie_details.return_value = details_b
            response = auth_headers.post(
                f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 222}
            )

        assert response.status_code == 200
        assert response.json["tmdb_id"] == 222
        assert response.json["directors"] == ["Director B"]
        assert response.json["genres"] == ["Comédia"]

        with client.application.app_context():
            updated = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert updated.tmdb_id == 222
            assert [d.name for d in updated.directors] == ["Director B"]
            assert [g.name for g in updated.genres] == ["Comédia"]

    def test_first_time_link_replaces_preexisting_relations(self, client, auth_headers):
        """A movie can already have directors/genres (e.g. from a merge or
        prior manual edit) before ever being linked to TMDB. Linking it to
        TMDB for the first time must replace those relations, not append
        to them."""
        with client.application.app_context():
            movie = _create_movie()
            stale_director = Director(tmdb_id=999, name="Stale Director")
            stale_genre = Genre(tmdb_id=999, name="Stale Genre")
            db_session.add_all([stale_director, stale_genre])
            db_session.commit()
            movie.directors.append(stale_director)
            movie.genres.append(stale_genre)
            db_session.add(movie)
            db_session.commit()
            movie_id = movie.id

        details = {
            "genres": [{"id": 28, "name": "Ação"}],
            "directors": [{"id": 42, "name": "Jane Director"}],
            "countries": [],
            "original_title": "Original",
            "release_year": 2021,
            "original_language": "en",
        }
        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.get_movie_details.return_value = details
            response = auth_headers.post(
                f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 555}
            )

        assert response.status_code == 200
        assert response.json["directors"] == ["Jane Director"]
        assert response.json["genres"] == ["Ação"]

        with client.application.app_context():
            updated = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert [d.name for d in updated.directors] == ["Jane Director"]
            assert [g.name for g in updated.genres] == ["Ação"]

    def test_relinking_clears_collection_when_new_match_has_none(
        self, client, auth_headers
    ):
        with client.application.app_context():
            movie_id = _create_movie().id

        details_with_collection = {
            "genres": [],
            "directors": [],
            "countries": [],
            "collection": {"id": 10, "name": "Some Collection"},
            "original_title": "Title A",
            "release_year": 2001,
            "original_language": "en",
        }
        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.get_movie_details.return_value = (
                details_with_collection
            )
            response = auth_headers.post(
                f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 111}
            )
        assert response.json["collection"] == "Some Collection"

        details_without_collection = {
            "genres": [],
            "directors": [],
            "countries": [],
            "original_title": "Title B",
            "release_year": 2002,
            "original_language": "fr",
        }
        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.get_movie_details.return_value = (
                details_without_collection
            )
            response = auth_headers.post(
                f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 222}
            )

        assert response.status_code == 200
        assert response.json["collection"] is None

        with client.application.app_context():
            updated = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert updated.collection_id is None

    def test_returns_400_when_tmdb_id_missing(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        response = auth_headers.post(f"/admin/movies/{movie_id}/tmdb-link", json={})
        assert response.status_code == 400

    def test_returns_400_when_tmdb_id_not_numeric(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        response = auth_headers.post(
            f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": "abc"}
        )
        assert response.status_code == 400

    def test_returns_502_and_does_not_write_on_tmdb_failure(self, client, auth_headers):
        with client.application.app_context():
            movie_id = _create_movie().id

        with patch("flask_backend.routes.admin.movies.TMDBClient") as mock_client_cls:
            mock_client_cls.return_value.get_movie_details.side_effect = (
                requests.RequestException("boom")
            )
            response = auth_headers.post(
                f"/admin/movies/{movie_id}/tmdb-link", json={"tmdb_id": 555}
            )

        assert response.status_code == 502
        with client.application.app_context():
            updated = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert updated.tmdb_id is None


class TestAdminMoviesTmdbUnlink:
    def test_requires_login(self, client):
        with client.application.app_context():
            movie_id = _create_movie(tmdb_id=555).id

        response = client.post(f"/admin/movies/{movie_id}/tmdb-unlink")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_clears_tmdb_id_without_touching_relations(self, client, auth_headers):
        with client.application.app_context():
            movie = _create_movie(tmdb_id=555)
            director = Director(tmdb_id=42, name="Jane Director")
            db_session.add(director)
            db_session.commit()
            movie.directors.append(director)
            db_session.add(movie)
            db_session.commit()
            movie_id = movie.id

        response = auth_headers.post(f"/admin/movies/{movie_id}/tmdb-unlink")
        assert response.status_code == 200
        assert response.json["tmdb_id"] is None

        with client.application.app_context():
            updated = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert updated.tmdb_id is None
            assert [d.name for d in updated.directors] == ["Jane Director"]
