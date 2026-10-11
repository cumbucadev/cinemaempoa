import json

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspectionRequest
from flask_backend.repository import movie_inspection_requests, pipeline_runs


def _create_movie(tmdb_id=None):
    movie = Movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


class TestCreateForMovie:
    def test_captures_the_current_tmdb_id_as_dispatched(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            request = movie_inspection_requests.create_for_movie(movie)

            stored = (
                db_session.query(MovieInspectionRequest).filter_by(id=request.id).one()
            )
            assert stored.movie_id == movie.id
            assert stored.checked_tmdb_id == 42
            assert stored.status == "dispatched"
            assert json.loads(stored.observed_tmdb_ids) == []
            assert stored.execution_id is None
            assert stored.pipeline_run_id is None
            assert stored.created_at is not None
            assert stored.finished_at is None

    def test_records_the_pipeline_run(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            run = pipeline_runs.start("inspect-movies")

            request = movie_inspection_requests.create_for_movie(
                movie, pipeline_run_id=run.id
            )

            assert request.pipeline_run_id == run.id


class TestGetById:
    def test_returns_the_request(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))

            assert movie_inspection_requests.get_by_id(request.id).id == request.id

    def test_returns_none_for_an_unknown_id(self, app):
        with app.app_context():
            assert movie_inspection_requests.get_by_id(999) is None


class TestCleanDb:
    """Runs in file order: the first test leaves a row behind for the
    conftest's clean_db to remove before the second one."""

    def test_leaves_a_request_behind(self, app):
        with app.app_context():
            movie_inspection_requests.create_for_movie(_create_movie(42))

            assert db_session.query(MovieInspectionRequest).count() == 1

    def test_starts_without_requests(self, app):
        with app.app_context():
            assert db_session.query(MovieInspectionRequest).count() == 0
