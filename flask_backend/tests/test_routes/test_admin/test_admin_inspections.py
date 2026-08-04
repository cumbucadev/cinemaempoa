"""Tests the basic functionality of /admin/movies/inspections."""

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository import movie_inspections


def _create_movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=None):
    movie = Movie(title=title, slug=slug, tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


class TestAdminInspectionsIndex:
    def test_requires_login(self, client):
        response = client.get("/admin/movies/inspections")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200_with_no_rows(self, auth_headers):
        response = auth_headers.get("/admin/movies/inspections")
        assert response.status_code == 200

    def test_lists_an_inspection_row(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="Diretor não coincide com o TMDB.",
                checked_tmdb_id=42,
            )

        response = auth_headers.get("/admin/movies/inspections")
        assert response.status_code == 200
        assert b"Filme de Teste" in response.data
        assert "Diretor não coincide com o TMDB.".encode() in response.data

    def test_filters_by_status(self, app, auth_headers):
        # Deliberately avoids status="fixed" here: that renders a Revert
        # button pointing at admin_inspections.revert, which isn't added
        # until Task 7. Fixed-row rendering is covered there instead.
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="tudo ok",
                checked_tmdb_id=42,
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="b não deveria aparecer com filtro consistent",
                checked_tmdb_id=42,
            )

        response = auth_headers.get("/admin/movies/inspections?status=consistent")
        assert response.status_code == 200
        assert "não deveria aparecer".encode() not in response.data

    def test_invalid_status_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/movies/inspections?status=bogus")
        assert response.status_code == 400

    def test_invalid_pagination_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/movies/inspections?page=invalid&limit=10")
        assert response.status_code == 400
