import json
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from flask_backend.db import db_session
from flask_backend.models import (
    Cinema,
    Country,
    Director,
    Genre,
    Movie,
    MovieInspection,
    PipelineRun,
    Screening,
)
from flask_backend.repository import movie_inspection_requests
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


def _create_linked_movie_with_screening():
    """A movie linked to TMDB with directors, countries, genres and one
    screening, so get_movie_context has every field to report."""
    movie = _create_movie(tmdb_id=42)
    movie.original_title = "A Capela"
    movie.release_year = 1979
    movie.original_language = "fr"
    movie.directors.append(Director(tmdb_id=1, name="Jean-Michel Tchissoukou"))
    movie.countries.append(Country(iso_3166_1="CG", name="Congo"))
    movie.genres.append(Genre(tmdb_id=18, name="Drama"))
    cinema = Cinema(slug="cine-teste", name="Cine Teste", url="https://example.com")
    db_session.add_all([movie, cinema])
    db_session.commit()
    screening = Screening(
        movie_id=movie.id,
        cinema_id=cinema.id,
        description="Drama congolês de 1979.",
        url="https://example.com/sessao",
    )
    db_session.add(screening)
    db_session.commit()
    return movie, screening


def _set_request_status(request, status):
    request.status = status
    db_session.add(request)
    db_session.commit()


class TestGetMovieContext:
    def test_returns_the_movie_match_and_screenings(self, app):
        with app.app_context():
            movie, screening = _create_linked_movie_with_screening()
            request = movie_inspection_requests.create_for_movie(movie)

            context = tools.get_movie_context(request.id)

            assert context.model_dump() == {
                "movie_title": "Filme de Teste",
                "tmdb_id": 42,
                "tmdb_original_title": "A Capela",
                "tmdb_release_year": 1979,
                "tmdb_original_language": "fr",
                "tmdb_directors": ["Jean-Michel Tchissoukou"],
                "tmdb_countries": ["Congo"],
                "tmdb_genres": ["Drama"],
                "screenings": [
                    {
                        "screening_id": screening.id,
                        "cinema_name": "Cine Teste",
                        "description": "Drama congolês de 1979.",
                    }
                ],
            }

    def test_reports_a_null_tmdb_id_for_an_unlinked_movie(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie())

            assert tools.get_movie_context(request.id).tmdb_id is None

    def test_refuses_an_unknown_request(self, app):
        with app.app_context(), pytest.raises(
            tools.InspectionRequestError, match="Pedido de inspeção #999 não existe"
        ):
            tools.get_movie_context(999)

    @pytest.mark.parametrize("status", ["done", "expired"])
    def test_refuses_a_request_no_longer_dispatched(self, app, status):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            _set_request_status(request, status)

            with pytest.raises(
                tools.InspectionRequestError,
                match=f"Pedido de inspeção #{request.id} não está mais ativo",
            ):
                tools.get_movie_context(request.id)


def _observed_ids(request_id):
    return json.loads(movie_inspection_requests.get_by_id(request_id).observed_tmdb_ids)


SEARCH_RESULTS = [
    {"id": 573412, "title": "A Capela", "release_date": "1979-01-01"},
    {"id": 999, "title": "A Capela (remake)", "release_date": ""},
]

# Each observation tool, called for `request_id` with arguments that are
# valid for any request, so the request checks can run over all three.
OBSERVATION_TOOLS = {
    "search_tmdb_candidates": lambda request_id: tools.search_tmdb_candidates(
        request_id, "A Capela"
    ),
    "get_tmdb_details": lambda request_id: tools.get_tmdb_details(request_id, 1),
    "fetch_screening_source": lambda request_id: tools.fetch_screening_source(
        request_id, 1
    ),
}


class TestObservationToolsRequestChecks:
    @pytest.mark.parametrize("tool", OBSERVATION_TOOLS)
    def test_refuses_an_unknown_request(self, app, tool):
        with app.app_context(), pytest.raises(
            tools.InspectionRequestError, match="Pedido de inspeção #999 não existe"
        ):
            OBSERVATION_TOOLS[tool](999)

    @pytest.mark.parametrize("tool", OBSERVATION_TOOLS)
    @pytest.mark.parametrize("status", ["done", "expired"])
    def test_refuses_a_request_no_longer_dispatched(self, app, tool, status):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            _set_request_status(request, status)

            with pytest.raises(
                tools.InspectionRequestError,
                match=f"Pedido de inspeção #{request.id} não está mais ativo",
            ):
                OBSERVATION_TOOLS[tool](request.id)


class TestSearchTmdbCandidates:
    def test_returns_the_core_text_and_records_the_exposed_ids(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            with patch.object(
                tools.TMDBClient, "search_movies", return_value=SEARCH_RESULTS
            ):
                observation = tools.search_tmdb_candidates(request.id, "A Capela")
                expected, _ = tools.run_search_tmdb_candidates("A Capela")

            assert observation == expected
            assert _observed_ids(request.id) == [573412, 999]

    def test_a_tmdb_error_comes_back_as_observation_text(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            with patch.object(
                tools.TMDBClient,
                "search_movies",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = tools.search_tmdb_candidates(request.id, "A Capela")

            assert observation.startswith("Erro ao buscar 'A Capela' no TMDB")
            assert _observed_ids(request.id) == []


class TestGetTmdbDetails:
    def test_returns_the_core_text_and_records_the_id(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            with patch.object(
                tools.TMDBClient, "get_movie_details", return_value=TMDB_DETAILS
            ):
                observation = tools.get_tmdb_details(request.id, 573412)
                expected, _ = tools.run_get_tmdb_details(573412)

            assert observation == expected
            assert _observed_ids(request.id) == [573412]

    def test_a_tmdb_error_comes_back_as_observation_text(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            with patch.object(
                tools.TMDBClient,
                "get_movie_details",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = tools.get_tmdb_details(request.id, 573412)

            assert observation.startswith("Erro ao buscar detalhes do TMDB")
            assert _observed_ids(request.id) == []


class TestObservedIdsAcrossTools:
    def test_accumulate_between_calls_without_duplicates(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))
            with patch.object(
                tools.TMDBClient, "search_movies", return_value=SEARCH_RESULTS
            ), patch.object(
                tools.TMDBClient, "get_movie_details", return_value=TMDB_DETAILS
            ):
                tools.search_tmdb_candidates(request.id, "A Capela")
                tools.get_tmdb_details(request.id, 573412)
                tools.get_tmdb_details(request.id, 12)
                tools.search_tmdb_candidates(request.id, "A Capela")

            assert _observed_ids(request.id) == [573412, 999, 12]


class TestFetchScreeningSource:
    def test_returns_the_source_of_a_screening_of_the_requests_movie(self, app):
        with app.app_context():
            movie, screening = _create_linked_movie_with_screening()
            request = movie_inspection_requests.create_for_movie(movie)
            response = MagicMock()
            response.text = "<p>Jean-Michel Tchissoukou, 1979</p>"
            with patch(
                "flask_backend.service.movie_inspection_tools.requests.get",
                return_value=response,
            ):
                observation = tools.fetch_screening_source(request.id, screening.id)

            assert observation == (
                "Conteúdo de https://example.com/sessao:\n"
                "Jean-Michel Tchissoukou, 1979"
            )

    def test_a_network_error_comes_back_as_observation_text(self, app):
        with app.app_context():
            movie, screening = _create_linked_movie_with_screening()
            request = movie_inspection_requests.create_for_movie(movie)
            with patch(
                "flask_backend.service.movie_inspection_tools.requests.get",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = tools.fetch_screening_source(request.id, screening.id)

            assert observation.startswith("Erro ao buscar https://example.com/sessao")

    def test_refuses_a_screening_of_another_movie(self, app):
        with app.app_context():
            _, screening = _create_linked_movie_with_screening()
            other = Movie(title="Outro Filme", slug="outro-filme", tmdb_id=7)
            db_session.add(other)
            db_session.commit()
            request = movie_inspection_requests.create_for_movie(other)

            with patch(
                "flask_backend.service.movie_inspection_tools.requests.get"
            ) as fetch, pytest.raises(
                tools.InspectionRequestError,
                match=(
                    f"Sessão #{screening.id} não pertence ao filme do pedido "
                    f"de inspeção #{request.id}"
                ),
            ):
                tools.fetch_screening_source(request.id, screening.id)
            fetch.assert_not_called()

    def test_refuses_an_unknown_screening(self, app):
        with app.app_context():
            request = movie_inspection_requests.create_for_movie(_create_movie(42))

            with pytest.raises(
                tools.InspectionRequestError, match="Sessão #999 não pertence"
            ):
                tools.fetch_screening_source(request.id, 999)


def _create_request(tmdb_id=1, observed=(), pipeline_run_id=None):
    movie = _create_movie(tmdb_id=tmdb_id)
    if pipeline_run_id is None:
        run = PipelineRun(
            pipeline_name="inspect-movies", started_at=datetime.now(), status="running"
        )
        db_session.add(run)
        db_session.commit()
        pipeline_run_id = run.id
    request = movie_inspection_requests.create_for_movie(
        movie, pipeline_run_id=pipeline_run_id
    )
    movie_inspection_requests.add_observed_tmdb_ids(request.id, observed)
    return movie, request


def _inspections():
    return db_session.query(MovieInspection).order_by(MovieInspection.id).all()


class TestApplyVerdict:
    @pytest.mark.parametrize("status", ["consistent", "needs_review"])
    def test_records_the_row_and_closes_the_request_without_touching_the_movie(
        self, app, status
    ):
        with app.app_context():
            movie, request = _create_request(tmdb_id=42)

            result = tools.apply_verdict(request.id, status, "Raciocínio.", None)

            [inspection] = _inspections()
            assert result == tools.VerdictResult(
                inspection_id=inspection.id, status=status, reasoning="Raciocínio."
            )
            assert inspection.movie_id == movie.id
            assert inspection.checked_tmdb_id == 42
            assert inspection.pipeline_run_id == request.pipeline_run_id
            assert inspection.previous_snapshot is None
            assert inspection.new_snapshot is None
            closed = movie_inspection_requests.get_by_id(request.id)
            assert closed.status == "done"
            assert closed.finished_at is not None
            assert closed.movie_inspection_id == inspection.id
            assert db_session.get(Movie, movie.id).tmdb_id == 42

    def test_fixed_with_an_observed_id_rematches_and_records_snapshots(self, app):
        with app.app_context():
            movie, request = _create_request(tmdb_id=1, observed=[573412])

            with patch.object(
                tools.TMDBClient, "get_movie_details", return_value=TMDB_DETAILS
            ):
                result = tools.apply_verdict(
                    request.id, "fixed", "Diretor e ano batem.", 573412
                )

            [inspection] = _inspections()
            assert result.status == "fixed"
            assert inspection.status == "fixed"
            assert inspection.checked_tmdb_id == 1
            assert inspection.pipeline_run_id == request.pipeline_run_id
            assert json.loads(inspection.previous_snapshot)["tmdb_id"] == 1
            assert json.loads(inspection.new_snapshot)["tmdb_id"] == 573412
            assert db_session.get(Movie, movie.id).tmdb_id == 573412
            assert movie_inspection_requests.get_by_id(request.id).status == "done"

    @pytest.mark.parametrize("new_tmdb_id", [None, 999999])
    def test_fixed_without_an_observed_id_is_downgraded_to_needs_review(
        self, app, new_tmdb_id
    ):
        with app.app_context():
            movie, request = _create_request(tmdb_id=1, observed=[573412])

            result = tools.apply_verdict(request.id, "fixed", "Confio.", new_tmdb_id)

            [inspection] = _inspections()
            assert result.status == inspection.status == "needs_review"
            assert inspection.reasoning.endswith("Raciocínio original: Confio.")
            assert db_session.get(Movie, movie.id).tmdb_id == 1
            assert movie_inspection_requests.get_by_id(request.id).status == "done"

    def test_fixed_after_the_link_changed_records_an_error_and_applies_nothing(
        self, app
    ):
        with app.app_context():
            movie, request = _create_request(tmdb_id=1, observed=[573412])
            movie.tmdb_id = 7
            db_session.add(movie)
            db_session.commit()

            with patch.object(tools.TMDBClient, "get_movie_details") as details:
                result = tools.apply_verdict(request.id, "fixed", "Batem.", 573412)

            details.assert_not_called()
            [inspection] = _inspections()
            assert result.status == inspection.status == "error"
            assert "mudou desde a criação do pedido (de 1 para 7)" in (
                inspection.reasoning
            )
            assert inspection.checked_tmdb_id == 1
            assert inspection.pipeline_run_id == request.pipeline_run_id
            assert inspection.new_snapshot is None
            assert db_session.get(Movie, movie.id).tmdb_id == 7
            assert movie_inspection_requests.get_by_id(request.id).status == "done"

    def test_a_tmdb_failure_during_the_rematch_records_an_error(self, app):
        with app.app_context():
            movie, request = _create_request(tmdb_id=1, observed=[573412])

            with patch.object(
                tools.TMDBClient,
                "get_movie_details",
                side_effect=requests.ConnectionError("fora do ar"),
            ):
                result = tools.apply_verdict(request.id, "fixed", "Batem.", 573412)

            [inspection] = _inspections()
            assert result.status == inspection.status == "error"
            assert "fora do ar" in inspection.reasoning
            assert inspection.checked_tmdb_id == 1
            assert inspection.pipeline_run_id == request.pipeline_run_id
            assert db_session.get(Movie, movie.id).tmdb_id == 1
            assert movie_inspection_requests.get_by_id(request.id).status == "done"

    def test_refuses_an_invalid_status(self, app):
        with app.app_context():
            _, request = _create_request()

            with pytest.raises(tools.InspectionRequestError, match="'reverted'"):
                tools.apply_verdict(request.id, "reverted", "Hm.", None)

            assert _inspections() == []
            assert (
                movie_inspection_requests.get_by_id(request.id).status == "dispatched"
            )

    def test_refuses_an_expired_request(self, app):
        with app.app_context():
            _, request = _create_request()
            _set_request_status(request, "expired")

            with pytest.raises(
                tools.InspectionRequestError,
                match=f"Pedido de inspeção #{request.id} não está mais ativo",
            ):
                tools.apply_verdict(request.id, "consistent", "Ok.", None)

            assert _inspections() == []

    def test_refuses_an_unknown_request(self, app):
        with app.app_context(), pytest.raises(
            tools.InspectionRequestError, match="Pedido de inspeção #999 não existe"
        ):
            tools.apply_verdict(999, "consistent", "Ok.", None)

    def test_a_second_call_returns_the_recorded_result_and_writes_nothing(self, app):
        with app.app_context():
            movie, request = _create_request(tmdb_id=1, observed=[573412])
            with patch.object(
                tools.TMDBClient, "get_movie_details", return_value=TMDB_DETAILS
            ):
                first = tools.apply_verdict(request.id, "fixed", "Batem.", 573412)
            finished_at = movie_inspection_requests.get_by_id(request.id).finished_at

            with patch.object(tools.TMDBClient, "get_movie_details") as details:
                second = tools.apply_verdict(
                    request.id, "needs_review", "Outra resposta.", None
                )

            details.assert_not_called()
            assert second == first
            assert len(_inspections()) == 1
            closed = movie_inspection_requests.get_by_id(request.id)
            assert closed.finished_at == finished_at
            assert db_session.get(Movie, movie.id).tmdb_id == 573412

    def test_a_done_request_without_a_recorded_inspection_is_refused(self, app):
        with app.app_context():
            _, request = _create_request()
            _set_request_status(request, "done")

            with pytest.raises(
                tools.InspectionRequestError, match="sem veredito registrado"
            ):
                tools.apply_verdict(request.id, "consistent", "Ok.", None)

    def test_an_unexpected_failure_leaves_the_request_open_and_the_movie_intact(
        self, app
    ):
        with app.app_context():
            movie, request = _create_request(tmdb_id=1, observed=[573412])

            with patch.object(
                tools.TMDBClient, "get_movie_details", return_value=None
            ), pytest.raises(AttributeError):
                tools.apply_verdict(request.id, "fixed", "Batem.", 573412)

            assert _inspections() == []
            assert (
                movie_inspection_requests.get_by_id(request.id).status == "dispatched"
            )
            assert db_session.get(Movie, movie.id).tmdb_id == 1
