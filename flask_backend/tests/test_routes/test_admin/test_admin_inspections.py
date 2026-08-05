"""Tests the basic functionality of /admin/movies/inspections."""

from unittest.mock import patch

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

    def test_renders_revert_button_for_fixed_rows(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Rematched.",
                checked_tmdb_id=42,
                previous_snapshot='{"tmdb_id": 1, "title": "Original"}',
                new_snapshot='{"tmdb_id": 42, "title": "Filme de Teste"}',
            )
            inspection_id = inspection.id

        response = auth_headers.get("/admin/movies/inspections?status=fixed")
        assert response.status_code == 200
        assert (
            f"/admin/movies/inspections/{inspection_id}/revert".encode()
            in response.data
        )
        assert b"Reverter" in response.data

    def test_filters_by_status(self, app, auth_headers):
        # Uses non-"fixed" statuses simply because they're the simplest
        # rows to build; fixed-row rendering (Revert button included) is
        # covered by test_renders_revert_button_for_fixed_rows above.
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


class TestAdminInspectionsRevert:
    def test_requires_login(self, client, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            inspection_id = inspection.id

        response = client.post(f"/admin/movies/inspections/{inspection_id}/revert")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_missing_inspection(self, auth_headers):
        response = auth_headers.post("/admin/movies/inspections/99999/revert")
        assert response.status_code == 404

    def test_returns_400_for_non_fixed_inspection(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="ok",
                checked_tmdb_id=42,
            )
            inspection_id = inspection.id

        response = auth_headers.post(
            f"/admin/movies/inspections/{inspection_id}/revert"
        )
        assert response.status_code == 400

    def test_reverts_and_redirects(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            inspection_id = inspection.id

        with patch(
            "flask_backend.routes.admin.inspections.revert_inspection"
        ) as mock_revert:
            response = auth_headers.post(
                f"/admin/movies/inspections/{inspection_id}/revert",
                data={"status": "fixed"},
            )

        mock_revert.assert_called_once_with(inspection_id)
        assert response.status_code == 302
        assert response.headers["Location"].endswith(
            "/admin/movies/inspections?status=fixed"
        )

    def test_returns_400_for_a_stale_fixed_inspection(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="a",
                checked_tmdb_id=1,
                previous_snapshot='{"tmdb_id": 1}',
                new_snapshot='{"tmdb_id": 42}',
            )
            inspection_id = inspection.id
            movie.tmdb_id = 99
            db_session.add(movie)
            db_session.commit()

        response = auth_headers.post(
            f"/admin/movies/inspections/{inspection_id}/revert"
        )
        assert response.status_code == 400
