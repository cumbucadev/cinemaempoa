from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository import pipeline_runs
from flask_backend.repository.movies import (
    create,
    get_by_title_or_create,
    get_movies_with_similar_titles,
)


class TestGetByTitleOrCreate:
    def test_creates_a_new_movie_when_none_exists(self, app):
        with app.app_context():
            movie, was_created = get_by_title_or_create("Filme Novo")

            assert was_created is True
            assert movie.id is not None
            assert movie.slug == "filme-novo"

    def test_returns_existing_movie_without_creating_a_duplicate(self, app):
        with app.app_context():
            first, _ = get_by_title_or_create("Filme Repetido")
            second, was_created = get_by_title_or_create("Filme Repetido")

            assert was_created is False
            assert second.id == first.id
            assert db_session.query(Movie).filter_by(slug="filme-repetido").count() == 1

    def test_threads_pipeline_run_id_through_to_the_created_movie(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")
            movie, was_created = get_by_title_or_create(
                "Filme Via Pipeline", pipeline_run_id=run.id
            )

            assert was_created is True
            assert movie.pipeline_run_id == run.id

    def test_does_not_overwrite_pipeline_run_id_on_an_existing_movie(self, app):
        with app.app_context():
            run_a = pipeline_runs.start("import-json")
            run_b = pipeline_runs.start("import-json")
            first, _ = get_by_title_or_create(
                "Filme Existente", pipeline_run_id=run_a.id
            )
            second, was_created = get_by_title_or_create(
                "Filme Existente", pipeline_run_id=run_b.id
            )

            assert was_created is False
            assert second.pipeline_run_id == run_a.id


class TestCreate:
    def test_leaves_pipeline_run_id_null_by_default(self, app):
        with app.app_context():
            movie = create(title="Filme Manual")
            assert movie.pipeline_run_id is None

    def test_stores_given_pipeline_run_id(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")
            movie = create(title="Filme Manual 2", pipeline_run_id=run.id)
            assert movie.pipeline_run_id == run.id


class TestGetMoviesWithSimilarTitles:
    def test_matches_partial_title_case_insensitively(self, app):
        with app.app_context():
            movie = Movie(title="Duna Parte Dois", slug="duna-parte-dois")
            db_session.add(movie)
            db_session.commit()

            results = get_movies_with_similar_titles("duna")

            assert [m.title for m in results] == ["Duna Parte Dois"]

    def test_excludes_given_movie_id(self, app):
        with app.app_context():
            keep = Movie(title="Duna Parte Um", slug="duna-parte-um")
            exclude = Movie(title="Duna Parte Dois", slug="duna-parte-dois-2")
            db_session.add_all([keep, exclude])
            db_session.commit()

            results = get_movies_with_similar_titles(
                "duna", exclude_movie_id=exclude.id
            )

            assert [m.id for m in results] == [keep.id]
