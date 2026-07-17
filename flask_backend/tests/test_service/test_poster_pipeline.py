from unittest.mock import patch

from flask_backend.db import db_session
from flask_backend.models import Cinema, Movie, PosterFetchAttempt, Screening
from flask_backend.service.poster_pipeline import (
    _extract_director_from_description,
    get_manual_review_summary,
    run_pipeline,
)


def _create_screening_without_poster(title="Filme Sem Poster", description=""):
    cinema = db_session.query(Cinema).first()
    movie = Movie(title=title, slug=title.lower().replace(" ", "-"))
    db_session.add(movie)
    db_session.commit()

    screening = Screening(
        movie_id=movie.id,
        cinema_id=cinema.id,
        description=description,
        image=None,
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening.id


class TestRunPipeline:
    def test_tmdb_success_saves_poster(self, client, app, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening_without_poster()

            with (
                patch(
                    "flask_backend.service.poster_pipeline._try_tmdb",
                    return_value="https://example.com/poster.jpg",
                ),
                patch(
                    "flask_backend.service.poster_pipeline.download_image_from_url",
                    return_value=(b"fake-bytes", "poster.jpg"),
                ),
                patch(
                    "flask_backend.service.poster_pipeline.save_image",
                    return_value=("poster.jpg", 100, 200),
                ),
            ):
                result = run_pipeline(app)

            assert result.posters_found == 1
            assert result.processed == 1

            screening = db_session.get(Screening, screening_id)
            assert screening.image == "poster.jpg"
            assert screening.image_width == 100

            attempts = (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "success"
            assert attempts[0].source == "tmdb"

    def test_tmdb_not_found_then_imdb_succeeds_on_next_run(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening_without_poster()

            with patch(
                "flask_backend.service.poster_pipeline._try_tmdb",
                return_value=None,
            ):
                first_result = run_pipeline(app)

            assert first_result.posters_not_found == 1
            attempts = (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].source == "tmdb"
            assert attempts[0].status == "not_found"

            with (
                patch(
                    "flask_backend.service.poster_pipeline._try_imdb",
                    return_value="https://example.com/imdb-poster.jpg",
                ),
                patch(
                    "flask_backend.service.poster_pipeline.download_image_from_url",
                    return_value=(b"fake-bytes", "imdb-poster.jpg"),
                ),
                patch(
                    "flask_backend.service.poster_pipeline.save_image",
                    return_value=("imdb-poster.jpg", 50, 60),
                ),
            ):
                second_result = run_pipeline(app)

            assert second_result.posters_found == 1
            attempts = (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .all()
            )
            assert len(attempts) == 2
            assert {a.source for a in attempts} == {"tmdb", "imdb"}

    def test_skips_when_all_sources_exhausted(self, client, app, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening_without_poster()
            from datetime import datetime

            db_session.add_all(
                [
                    PosterFetchAttempt(
                        screening_id=screening_id,
                        source="tmdb",
                        status="not_found",
                        attempted_at=datetime.now(),
                    ),
                    PosterFetchAttempt(
                        screening_id=screening_id,
                        source="imdb",
                        status="not_found",
                        attempted_at=datetime.now(),
                    ),
                ]
            )
            db_session.commit()

            result = run_pipeline(app)

        assert result.skipped_all_sources_tried == 1
        assert result.processed == 0

    def test_dry_run_does_not_call_handlers_or_record_attempts(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening_without_poster()

            with patch("flask_backend.service.poster_pipeline._try_tmdb") as mock_tmdb:
                result = run_pipeline(app, dry_run=True)

            mock_tmdb.assert_not_called()
            assert result.processed == 1
            assert (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .count()
                == 0
            )

    def test_limit_restricts_number_processed(self, client, app, setup_cinemas):
        with client.application.app_context():
            _create_screening_without_poster("Filme Um")
            _create_screening_without_poster("Filme Dois")

            with patch(
                "flask_backend.service.poster_pipeline._try_tmdb",
                return_value=None,
            ):
                result = run_pipeline(app, limit=1)

        assert result.processed == 1

    def test_handler_exception_records_error(self, client, app, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening_without_poster()

            with patch(
                "flask_backend.service.poster_pipeline._try_tmdb",
                side_effect=RuntimeError("boom"),
            ):
                result = run_pipeline(app)

            assert result.errors == 1
            attempt = (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .first()
            )
            assert attempt.status == "error"
            assert "boom" in attempt.error_message

    def test_download_failure_records_error(self, client, app, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening_without_poster()

            with (
                patch(
                    "flask_backend.service.poster_pipeline._try_tmdb",
                    return_value="https://example.com/poster.jpg",
                ),
                patch(
                    "flask_backend.service.poster_pipeline.download_image_from_url",
                    return_value=(None, None),
                ),
            ):
                result = run_pipeline(app)

            assert result.errors == 1
            attempt = (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .first()
            )
            assert attempt.status == "error"
            assert "Download falhou" in attempt.error_message

    def test_extracts_director_from_description_for_imdb_handler(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening_without_poster(description="Direção: Fulano de Tal")

            with patch(
                "flask_backend.service.poster_pipeline._try_imdb",
                return_value=None,
            ) as mock_imdb:
                # force imdb as the source to try
                with patch(
                    "flask_backend.service.poster_pipeline._try_tmdb",
                    return_value=None,
                ):
                    run_pipeline(app)  # exhausts tmdb
                run_pipeline(app)  # now tries imdb

            mock_imdb.assert_called_once_with(
                "Filme Sem Poster", director="Fulano de Tal"
            )


class TestExtractDirectorFromDescription:
    def test_returns_none_for_empty_description(self):
        assert _extract_director_from_description("") is None

    def test_extracts_from_direcao_prefix(self):
        assert (
            _extract_director_from_description("Direção: Fulano de Tal")
            == "Fulano de Tal"
        )

    def test_extracts_from_director_prefix(self):
        assert _extract_director_from_description("Director: Jane Doe") == "Jane Doe"

    def test_returns_none_when_no_matching_line(self):
        assert _extract_director_from_description("Sem informação de diretor") is None


class TestGetManualReviewSummary:
    def test_lists_screenings_with_all_sources_exhausted(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            from datetime import datetime

            screening_id = _create_screening_without_poster("Filme Pendente")
            db_session.add_all(
                [
                    PosterFetchAttempt(
                        screening_id=screening_id,
                        source="tmdb",
                        status="not_found",
                        attempted_at=datetime.now(),
                    ),
                    PosterFetchAttempt(
                        screening_id=screening_id,
                        source="imdb",
                        status="error",
                        attempted_at=datetime.now(),
                    ),
                ]
            )
            db_session.commit()

            summary = get_manual_review_summary()

        assert len(summary) == 1
        assert summary[0]["screening_id"] == screening_id
        assert summary[0]["movie_title"] == "Filme Pendente"
        assert summary[0]["sources_attempted"] == ["imdb", "tmdb"]

    def test_empty_when_no_screenings_need_review(self, client, app, setup_cinemas):
        with client.application.app_context():
            summary = get_manual_review_summary()
        assert summary == []
