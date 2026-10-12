import json
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from flask_backend.db import Base, configure_sqlite_pragmas, db_session
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


class TestAddObservedTmdbIds:
    def test_accumulates_across_calls_without_duplicates(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))

            movie_inspection_requests.add_observed_tmdb_ids(request.id, [7, 8, 7])
            merged = movie_inspection_requests.add_observed_tmdb_ids(request.id, [8, 9])

            assert merged == [7, 8, 9]
            stored = movie_inspection_requests.get_by_id(request.id)
            assert json.loads(stored.observed_tmdb_ids) == [7, 8, 9]

    def test_nothing_new_leaves_the_list_as_is(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            movie_inspection_requests.add_observed_tmdb_ids(request.id, [7])

            assert movie_inspection_requests.add_observed_tmdb_ids(request.id, []) == [
                7
            ]

    def test_parallel_calls_do_not_lose_ids(self, tmp_path, monkeypatch):
        """Two callers on separate connections to a file-backed SQLite, the
        way the MCP server runs parallel tool calls: the second starts while
        the first sits between its read and its write. Without the write lock
        taken before the read, the second would read [] too and one id would
        be lost."""
        engine = create_engine(f"sqlite:///{tmp_path / 'requests.sqlite'}")
        configure_sqlite_pragmas(engine)
        Base.metadata.create_all(engine)
        session = scoped_session(sessionmaker(bind=engine))
        monkeypatch.setattr(movie_inspection_requests, "db_session", session)
        request = MovieInspectionRequest(
            movie_id=1, observed_tmdb_ids="[]", status="dispatched"
        )
        session.add(request)
        session.commit()
        request_id = request.id
        session.remove()

        first_has_read = threading.Event()
        merge_ids = movie_inspection_requests._merge_ids

        def slow_merge(current, new_ids):
            if threading.current_thread().name == "first":
                first_has_read.set()
                # Give the second caller time to reach its own read.
                threading.Event().wait(0.3)
            return merge_ids(current, new_ids)

        monkeypatch.setattr(movie_inspection_requests, "_merge_ids", slow_merge)

        def add(ids):
            try:
                movie_inspection_requests.add_observed_tmdb_ids(request_id, ids)
            finally:
                session.remove()

        first = threading.Thread(target=add, args=([1],), name="first")
        first.start()
        assert first_has_read.wait(5)
        second = threading.Thread(target=add, args=([2],), name="second")
        second.start()
        first.join(10)
        second.join(10)

        stored = session.get(MovieInspectionRequest, request_id)
        assert json.loads(stored.observed_tmdb_ids) == [1, 2]
        session.remove()
        engine.dispose()


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
