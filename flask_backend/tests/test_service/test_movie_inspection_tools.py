import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from flask_backend.db import db_session
from flask_backend.models import Director, Movie
from flask_backend.service import movie_inspection_tools as tools

TMDB_DETAILS = {
    "directors": [{"id": 1, "name": "Jean-Michel Tchissoukou"}],
    "genres": [],
    "countries": [],
    "collection": None,
    "original_title": "A Capela",
    "release_year": 1979,
    "original_language": "fr",
}


def _create_movie(tmdb_id=None):
    movie = Movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


@pytest.fixture(autouse=True)
def tmdb_api_token(monkeypatch):
    """TMDBClient() is instantiated without an explicit token, so it falls
    back to TMDB_API_TOKEN. That env var isn't set in CI, so stub it here
    rather than relying on a real .env."""
    monkeypatch.setattr("flask_backend.service.tmdb.TMDB_API_TOKEN", "fake-token")


@pytest.fixture(autouse=True)
def _reenable_tools_logger(app):
    # migrations/env.py calls logging.config.fileConfig(...) on every `app`
    # fixture setup, which disables loggers that already existed - including
    # this module's. Re-enable it so caplog can observe log calls.
    tools.logger.disabled = False


class TestSnapshot:
    def test_captures_key_fields(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie.original_title = "Original"
            movie.release_year = 1979
            director = Director(tmdb_id=1, name="Jean-Michel Tchissoukou")
            db_session.add(director)
            movie.directors.append(director)
            db_session.add(movie)
            db_session.commit()

            snapshot = tools.snapshot(movie)

            assert snapshot == {
                "tmdb_id": 42,
                "title": "Filme de Teste",
                "original_title": "Original",
                "release_year": 1979,
                "directors": ["Jean-Michel Tchissoukou"],
                "countries": [],
            }


class TestApplyRematch:
    def test_applies_new_tmdb_details(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            details = {
                "directors": [{"id": 2, "name": "Jane Director"}],
                "genres": [],
                "countries": [{"iso_3166_1": "BR", "name": "Brasil"}],
                "collection": None,
                "original_title": "New Original",
                "release_year": 1979,
                "original_language": "pt",
            }
            with patch.object(
                tools.TMDBClient,
                "get_movie_details",
                return_value=details,
            ):
                tools.apply_rematch(movie, 42)

            assert movie.tmdb_id == 42
            assert movie.original_title == "New Original"
            assert [d.name for d in movie.directors] == ["Jane Director"]

    def test_clears_metadata_when_tmdb_id_is_none(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            movie.original_title = "Something"
            db_session.add(movie)
            db_session.commit()

            tools.apply_rematch(movie, None)

            assert movie.tmdb_id is None
            assert movie.original_title is None
            assert movie.tmdb_excluded is False


class TestRunSearchTmdbCandidates:
    def test_formats_candidates(self, app):
        with app.app_context():
            results = [
                {"id": 573412, "title": "A Capela", "release_date": "1979-01-01"},
                {"id": 999, "title": "A Capela (remake)", "release_date": ""},
            ]
            with patch.object(tools.TMDBClient, "search_movies", return_value=results):
                observation, ids = tools.run_search_tmdb_candidates("A Capela")

            assert "tmdb_id=573412" in observation
            assert "ano=1979" in observation
            assert "tmdb_id=999" in observation
            assert ids == [573412, 999]

    def test_reports_no_results(self, app):
        with app.app_context():
            with patch.object(tools.TMDBClient, "search_movies", return_value=[]):
                observation, ids = tools.run_search_tmdb_candidates("Xyz")

            assert "Nenhum resultado" in observation
            assert ids == []

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                tools.TMDBClient,
                "search_movies",
                side_effect=requests.RequestException("timeout"),
            ):
                observation, ids = tools.run_search_tmdb_candidates("Xyz")

            assert "Erro" in observation
            assert ids == []


class TestRunGetTmdbDetails:
    def test_formats_details(self, app):
        with app.app_context():
            details = {
                "directors": [{"id": 1, "name": "Jean-Michel Tchissoukou"}],
                "countries": [{"iso_3166_1": "CG", "name": "Congo"}],
                "genres": [],
                "collection": None,
                "original_title": "A Capela",
                "release_year": 1979,
                "original_language": "fr",
            }
            with patch.object(
                tools.TMDBClient, "get_movie_details", return_value=details
            ):
                observation, ids = tools.run_get_tmdb_details(573412)

            assert "Jean-Michel Tchissoukou" in observation
            assert "1979" in observation
            assert "Congo" in observation
            assert ids == [573412]

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                tools.TMDBClient,
                "get_movie_details",
                side_effect=requests.RequestException("timeout"),
            ):
                observation, ids = tools.run_get_tmdb_details(1)

            assert "Erro" in observation
            assert ids == []


class TestRunFetchScreeningSource:
    def test_reports_missing_screening(self, app):
        with app.app_context():
            observation = tools.run_fetch_screening_source(99999)

            assert "não encontrada" in observation

    def test_reports_missing_url(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                url=None,
            )
            db_session.add(screening)
            db_session.commit()

            observation = tools.run_fetch_screening_source(screening.id)

            assert "não tem URL" in observation

    def test_fetches_and_extracts_text(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                url="https://example.com/evento",
            )
            db_session.add(screening)
            db_session.commit()

            response = MagicMock()
            response.text = (
                "<html><body><p>Jean-Michel Tchissoukou, 1979</p></body></html>"
            )
            response.raise_for_status = MagicMock()
            with patch(
                "flask_backend.service.movie_inspection_tools.requests.get",
                return_value=response,
            ):
                observation = tools.run_fetch_screening_source(screening.id)

            assert "Jean-Michel Tchissoukou, 1979" in observation

    def test_reports_request_errors(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                url="https://example.com/evento",
            )
            db_session.add(screening)
            db_session.commit()

            with patch(
                "flask_backend.service.movie_inspection_tools.requests.get",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = tools.run_fetch_screening_source(screening.id)

            assert "Erro" in observation


class TestFetchScreeningSourceTruncation:
    def test_strips_html_and_cuts_to_max_chars(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                url="https://example.com/evento",
            )
            db_session.add(screening)
            db_session.commit()

            response = MagicMock()
            response.text = "<p>" + "a" * 5000 + "</p>"
            with patch(
                "flask_backend.service.movie_inspection_tools.requests.get",
                return_value=response,
            ):
                observation = tools.run_fetch_screening_source(screening.id)

            assert observation == (
                "Conteúdo de https://example.com/evento:\n" + "a" * 4000
            )


class TestResolveVerdict:
    def test_consistent_leaves_movie_untouched(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            outcome = tools.resolve_verdict(movie, "consistent", "Tudo ok.", None, [])

            assert outcome == tools.InspectionOutcome(
                status="consistent", reasoning="Tudo ok."
            )
            assert movie.tmdb_id == 42

    def test_needs_review_is_passed_through(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            outcome = tools.resolve_verdict(movie, "needs_review", "Incerto.", None, [])

            assert outcome.status == "needs_review"
            assert outcome.reasoning == "Incerto."

    def test_fixed_applies_rematch_and_captures_snapshots(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            with patch.object(
                tools.TMDBClient, "get_movie_details", return_value=TMDB_DETAILS
            ):
                outcome = tools.resolve_verdict(
                    movie, "fixed", "Diretor e ano batem.", 573412, {573412}
                )

            assert outcome.status == "fixed"
            assert outcome.reasoning == "Diretor e ano batem."
            assert movie.tmdb_id == 573412
            assert outcome.before_snapshot["tmdb_id"] == 1
            assert outcome.after_snapshot["tmdb_id"] == 573412
            assert outcome.after_snapshot["directors"] == ["Jean-Michel Tchissoukou"]

    def test_fixed_without_new_tmdb_id_becomes_needs_review(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            outcome = tools.resolve_verdict(movie, "fixed", "Sem id.", None, {1})

            assert outcome.status == "needs_review"
            assert outcome.before_snapshot is None
            assert movie.tmdb_id == 1

    def test_fixed_with_unobserved_tmdb_id_becomes_needs_review(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            outcome = tools.resolve_verdict(
                movie, "fixed", "Confio que é o id 999999.", 999999, [573412]
            )

            assert outcome.status == "needs_review"
            assert outcome.reasoning == (
                "Veredito 'fixed' com um tmdb_id que não foi observado por "
                "nenhuma ferramenta nesta inspeção; tratado como revisão "
                "manual. Raciocínio original: Confio que é o id 999999."
            )
            assert movie.tmdb_id == 1

    def test_unobserved_tmdb_id_guard_logs_warning(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            with caplog.at_level(logging.WARNING, logger=tools.__name__):
                tools.resolve_verdict(movie, "fixed", "Confio.", 999999, [])

            messages = [r.getMessage() for r in caplog.records]
            assert any(
                str(movie.id) in m and "999999" in m and "não foi observado" in m
                for m in messages
            )
