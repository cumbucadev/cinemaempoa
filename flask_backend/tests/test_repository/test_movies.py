from datetime import date

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository import pipeline_runs
from flask_backend.repository.movies import (
    create,
    create_distinct,
    get_by_title_or_create,
    get_movies_with_similar_titles,
    resolve_for_screening,
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


class TestCreateDistinct:
    def test_creates_a_new_movie_with_base_slug_when_none_exists(self, app):
        with app.app_context():
            movie = create_distinct("Filme Único")

            assert movie.id is not None
            assert movie.slug == "filme-unico"

    def test_disambiguates_slug_on_first_collision(self, app):
        with app.app_context():
            first = create_distinct("Filme Repetido")
            second = create_distinct("Filme Repetido")

            assert second.id != first.id
            assert first.slug == "filme-repetido"
            assert second.slug == "filme-repetido-2"

    def test_disambiguates_slug_on_second_collision(self, app):
        with app.app_context():
            create_distinct("Filme Triplo")
            create_distinct("Filme Triplo")
            third = create_distinct("Filme Triplo")

            assert third.slug == "filme-triplo-3"

    def test_both_movies_keep_the_same_title(self, app):
        with app.app_context():
            first = create_distinct("Filme Igual")
            second = create_distinct("Filme Igual")

            assert first.title == second.title == "Filme Igual"
            assert db_session.query(Movie).filter_by(title="Filme Igual").count() == 2

    def test_threads_pipeline_run_id_through_to_the_created_movie(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")
            movie = create_distinct(
                "Filme Via Pipeline Distinto", pipeline_run_id=run.id
            )

            assert movie.pipeline_run_id == run.id


class TestResolveForScreening:
    def test_creates_a_new_movie_when_none_exists(self, app):
        with app.app_context():
            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Filme Inédito", cinema_id=1
            )

            assert created is True
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.slug == "filme-inedito"

    def test_returns_base_movie_when_no_siblings_exist(self, app):
        with app.app_context():
            base, _ = get_by_title_or_create("Filme Solo")

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Filme Solo", cinema_id=1
            )

            assert created is False
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.id == base.id

    def test_resolves_to_sibling_with_matching_cinema_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            get_by_title_or_create("Noite")
            sibling = create_distinct("Noite")
            db_session.add(
                Screening(
                    movie_id=sibling.id,
                    cinema_id=2,  # sala-redencao
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            db_session.commit()
            sibling_id = sibling.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=2
            )

            assert created is False
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.id == sibling_id

    def test_resolves_to_base_movie_when_base_has_the_matching_cinema_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            db_session.add(
                Screening(
                    movie_id=base.id,
                    cinema_id=1,  # capitolio
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            create_distinct("Noite")
            db_session.commit()
            base_id = base.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=1
            )

            assert created is False
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.id == base_id

    def test_flags_ambiguous_when_no_candidate_has_the_cinema_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            sibling = create_distinct("Noite")
            db_session.add(
                Screening(
                    movie_id=base.id,
                    cinema_id=1,  # capitolio
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            db_session.commit()
            base_id, sibling_id = base.id, sibling.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite",
                cinema_id=3,  # cinebancarios: neither candidate plays here
            )

            assert created is False
            assert ambiguous is True
            assert movie.id == base_id
            assert set(candidate_ids) == {base_id, sibling_id}

    def test_flags_ambiguous_when_more_than_one_candidate_matches_the_cinema(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            sibling = create_distinct("Noite")
            db_session.add_all(
                [
                    Screening(
                        movie_id=base.id,
                        cinema_id=1,
                        description="",
                        dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                    ),
                    Screening(
                        movie_id=sibling.id,
                        cinema_id=1,
                        description="",
                        dates=[ScreeningDate(date=date(2026, 8, 11), time="21:00")],
                    ),
                ]
            )
            db_session.commit()
            base_id = base.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=1
            )

            assert ambiguous is True
            assert movie.id == base_id

    def test_does_not_treat_a_same_substring_title_as_a_sibling(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            db_session.add(Movie(title="Noites Paraguayas", slug="noites-paraguayas"))
            db_session.add(
                Screening(
                    movie_id=base.id,
                    cinema_id=1,
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            db_session.commit()
            base_id = base.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=1
            )

            assert ambiguous is False
            assert movie.id == base_id
