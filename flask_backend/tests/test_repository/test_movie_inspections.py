from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspection
from flask_backend.repository import movie_inspections


def _create_movie(title="Filme de Teste", tmdb_id=None):
    movie = Movie(title=title, slug="filme-de-teste", tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


class TestCreate:
    def test_persists_all_fields(self, app):
        with app.app_context():
            movie = _create_movie()

            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Diretor e ano não coincidiam com o TMDB.",
                checked_tmdb_id=42,
                previous_snapshot='{"tmdb_id": 1}',
                new_snapshot='{"tmdb_id": 42}',
            )

            assert inspection.id is not None
            stored = db_session.query(MovieInspection).filter_by(id=inspection.id).one()
            assert stored.movie_id == movie.id
            assert stored.status == "fixed"
            assert stored.checked_tmdb_id == 42
            assert stored.previous_snapshot == '{"tmdb_id": 1}'
            assert stored.new_snapshot == '{"tmdb_id": 42}'
            assert stored.created_at is not None


class TestGetMoviesNeedingInspection:
    def test_ignores_movies_without_a_tmdb_match(self, app):
        with app.app_context():
            _create_movie(title="Sem TMDB", tmdb_id=None)

            assert movie_inspections.get_movies_needing_inspection() == []

    def test_includes_matched_movie_never_inspected(self, app):
        with app.app_context():
            movie = _create_movie(title="Nunca Inspecionado", tmdb_id=42)

            result = movie_inspections.get_movies_needing_inspection()

            assert [m.id for m in result] == [movie.id]

    def test_excludes_movie_already_checked_at_its_current_tmdb_id(self, app):
        with app.app_context():
            movie = _create_movie(title="Já Checado", tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="Ok.",
                checked_tmdb_id=42,
            )

            assert movie_inspections.get_movies_needing_inspection() == []

    def test_includes_movie_whose_match_changed_since_last_check(self, app):
        with app.app_context():
            movie = _create_movie(title="Rematched", tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="Ok na época.",
                checked_tmdb_id=1,
            )

            result = movie_inspections.get_movies_needing_inspection()

            assert [m.id for m in result] == [movie.id]

    def test_includes_movie_whose_only_prior_row_is_an_error(self, app):
        with app.app_context():
            movie = _create_movie(title="Erro Antes", tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="error",
                reasoning="Gemini indisponível.",
                checked_tmdb_id=42,
            )

            result = movie_inspections.get_movies_needing_inspection()

            assert [m.id for m in result] == [movie.id]


class TestGetPaginated:
    def test_filters_by_status(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="b",
                checked_tmdb_id=42,
            )

            fixed, pages, total = movie_inspections.get_paginated("fixed", 1, 20)

            assert total == 1
            assert pages == 1
            assert [i.status for i in fixed] == ["fixed"]

    def test_no_filter_returns_everything_newest_first(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            first = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            second = movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="b",
                checked_tmdb_id=42,
            )

            rows, _, total = movie_inspections.get_paginated(None, 1, 20)

            assert total == 2
            assert [r.id for r in rows] == [second.id, first.id]

    def test_paginates(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            for i in range(3):
                movie_inspections.create(
                    movie_id=movie.id,
                    status="consistent",
                    reasoning=f"row {i}",
                    checked_tmdb_id=42,
                )

            page_one, pages, total = movie_inspections.get_paginated(None, 1, 2)
            page_two, _, _ = movie_inspections.get_paginated(None, 2, 2)

            assert total == 3
            assert pages == 2
            assert len(page_one) == 2
            assert len(page_two) == 1


class TestGetById:
    def test_returns_none_for_missing_id(self, app):
        with app.app_context():
            assert movie_inspections.get_by_id(99999) is None

    def test_returns_the_matching_row(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            created = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )

            assert movie_inspections.get_by_id(created.id).id == created.id
