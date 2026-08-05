import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from flask_backend.db import db_session
from flask_backend.models import Director, Movie
from flask_backend.service import movie_inspector


def _create_movie(tmdb_id=None):
    movie = Movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


@pytest.fixture(autouse=True)
def tmdb_api_token(monkeypatch):
    """TMDBClient() is instantiated without an explicit token throughout
    movie_inspector.py, so it falls back to TMDB_API_TOKEN. That env var
    isn't set in CI, so stub it here rather than relying on a real .env."""
    monkeypatch.setattr("flask_backend.service.tmdb.TMDB_API_TOKEN", "fake-token")


@pytest.fixture(autouse=True)
def _reenable_movie_inspector_logger(app):
    # migrations/env.py calls logging.config.fileConfig(...) on every `app`
    # fixture setup (via init_db's alembic upgrade), which disables any
    # logger that already existed at that point - including this module's,
    # imported at collection time. Re-enable it post-setup so caplog can
    # actually observe log calls in these tests.
    movie_inspector.logger.disabled = False


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

            snapshot = movie_inspector._snapshot(movie)

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
                movie_inspector.TMDBClient,
                "get_movie_details",
                return_value=details,
            ):
                movie_inspector._apply_rematch(movie, 42)

            assert movie.tmdb_id == 42
            assert movie.original_title == "New Original"
            assert [d.name for d in movie.directors] == ["Jane Director"]

    def test_clears_metadata_when_tmdb_id_is_none(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            movie.original_title = "Something"
            db_session.add(movie)
            db_session.commit()

            movie_inspector._apply_rematch(movie, None)

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
            with patch.object(
                movie_inspector.TMDBClient, "search_movies", return_value=results
            ):
                observation, ids = movie_inspector._run_search_tmdb_candidates(
                    "A Capela"
                )

            assert "tmdb_id=573412" in observation
            assert "ano=1979" in observation
            assert "tmdb_id=999" in observation
            assert ids == [573412, 999]

    def test_reports_no_results(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient, "search_movies", return_value=[]
            ):
                observation, ids = movie_inspector._run_search_tmdb_candidates("Xyz")

            assert "Nenhum resultado" in observation
            assert ids == []

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient,
                "search_movies",
                side_effect=requests.RequestException("timeout"),
            ):
                observation, ids = movie_inspector._run_search_tmdb_candidates("Xyz")

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
                movie_inspector.TMDBClient, "get_movie_details", return_value=details
            ):
                observation, ids = movie_inspector._run_get_tmdb_details(573412)

            assert "Jean-Michel Tchissoukou" in observation
            assert "1979" in observation
            assert "Congo" in observation
            assert ids == [573412]

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient,
                "get_movie_details",
                side_effect=requests.RequestException("timeout"),
            ):
                observation, ids = movie_inspector._run_get_tmdb_details(1)

            assert "Erro" in observation
            assert ids == []


class TestRunFetchScreeningSource:
    def test_reports_missing_screening(self, app):
        with app.app_context():
            observation = movie_inspector._run_fetch_screening_source(99999)

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

            observation = movie_inspector._run_fetch_screening_source(screening.id)

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
                "flask_backend.service.movie_inspector.requests.get",
                return_value=response,
            ):
                observation = movie_inspector._run_fetch_screening_source(screening.id)

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
                "flask_backend.service.movie_inspector.requests.get",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = movie_inspector._run_fetch_screening_source(screening.id)

            assert "Erro" in observation


class TestAttachDebugHooks:
    def _handler_for(self, fake_agent, event):
        for call in fake_agent.register_hook.call_args_list:
            if call.args[0] == event:
                return call.args[1]
        raise AssertionError(f"no handler registered for {event!r}")

    def test_registers_all_hook_events(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            fake_agent = MagicMock()

            movie_inspector._attach_debug_hooks(fake_agent, movie)

            registered_events = {
                call.args[0] for call in fake_agent.register_hook.call_args_list
            }
            assert registered_events == {
                "completion:kwargs",
                "completion:response",
                "completion:error",
                "completion:last_attempt",
                "parse:error",
            }

    def test_completion_kwargs_hook_logs_model_and_message_count(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            fake_agent = MagicMock()
            movie_inspector._attach_debug_hooks(fake_agent, movie)
            handler = self._handler_for(fake_agent, "completion:kwargs")

            with caplog.at_level("INFO", logger=movie_inspector.__name__):
                handler(
                    model="gemini-2.5-flash",
                    messages=[{"role": "user", "content": "oi"}],
                    response_model=movie_inspector.OrchestratorDecision,
                )

            message = caplog.records[-1].getMessage()
            assert str(movie.id) in message
            assert "gemini-2.5-flash" in message
            assert "mensagens=1" in message

    def test_completion_response_hook_logs_token_usage(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            fake_agent = MagicMock()
            movie_inspector._attach_debug_hooks(fake_agent, movie)
            handler = self._handler_for(fake_agent, "completion:response")

            response = MagicMock()
            response.usage_metadata.prompt_token_count = 100
            response.usage_metadata.candidates_token_count = 20
            response.usage_metadata.total_token_count = 120

            with caplog.at_level("INFO", logger=movie_inspector.__name__):
                handler(response)

            message = caplog.records[-1].getMessage()
            assert str(movie.id) in message
            assert "100" in message
            assert "20" in message
            assert "120" in message

    def test_completion_response_hook_without_usage_metadata_does_not_crash(
        self, app, caplog
    ):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            fake_agent = MagicMock()
            movie_inspector._attach_debug_hooks(fake_agent, movie)
            handler = self._handler_for(fake_agent, "completion:response")

            with caplog.at_level("INFO", logger=movie_inspector.__name__):
                handler(object())

            message = caplog.records[-1].getMessage()
            assert str(movie.id) in message

    def test_completion_error_hook_logs_warning(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            fake_agent = MagicMock()
            movie_inspector._attach_debug_hooks(fake_agent, movie)
            handler = self._handler_for(fake_agent, "completion:error")

            with caplog.at_level("WARNING", logger=movie_inspector.__name__):
                handler(RuntimeError("gemini indisponível"))

            record = caplog.records[-1]
            assert record.levelname == "WARNING"
            assert "gemini indisponível" in record.getMessage()
            assert str(movie.id) in record.getMessage()

    def test_completion_last_attempt_hook_logs_warning(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            fake_agent = MagicMock()
            movie_inspector._attach_debug_hooks(fake_agent, movie)
            handler = self._handler_for(fake_agent, "completion:last_attempt")

            with caplog.at_level("WARNING", logger=movie_inspector.__name__):
                handler(RuntimeError("timeout"))

            record = caplog.records[-1]
            assert record.levelname == "WARNING"
            assert "timeout" in record.getMessage()
            assert str(movie.id) in record.getMessage()

    def test_parse_error_hook_logs_warning(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            fake_agent = MagicMock()
            movie_inspector._attach_debug_hooks(fake_agent, movie)
            handler = self._handler_for(fake_agent, "parse:error")

            with caplog.at_level("WARNING", logger=movie_inspector.__name__):
                handler(ValueError("campo obrigatório ausente"))

            record = caplog.records[-1]
            assert record.levelname == "WARNING"
            assert "campo obrigatório ausente" in record.getMessage()
            assert str(movie.id) in record.getMessage()


class TestInspectMovie:
    def _decision(self, **kwargs):
        defaults = {
            "action": "conclude",
            "search_title": None,
            "tmdb_id": None,
            "screening_id": None,
            "verdict": None,
        }
        defaults.update(kwargs)
        return movie_inspector.OrchestratorDecision(**defaults)

    def _verdict(self, **kwargs):
        defaults = {
            "status": "consistent",
            "reasoning": "Bate tudo.",
            "new_tmdb_id": None,
        }
        defaults.update(kwargs)
        return movie_inspector.InspectionVerdict(**defaults)

    def test_attaches_debug_hooks_to_the_built_agent(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(status="consistent", reasoning="ok")
            )
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                patch.object(movie_inspector, "_attach_debug_hooks") as mock_attach,
            ):
                movie_inspector.inspect_movie(movie)

            mock_attach.assert_called_once_with(fake_agent, movie)

    def test_rate_limit_on_first_model_retries_whole_inspection_on_second(self, app):
        from google.genai.errors import ClientError

        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            rate_limited_agent = MagicMock()
            rate_limited_agent.run.side_effect = ClientError(code=429, response_json={})
            second_agent = MagicMock()
            second_agent.run.return_value = self._decision(
                verdict=self._verdict(status="consistent", reasoning="ok")
            )

            with patch.object(
                movie_inspector,
                "_build_agent",
                side_effect=[rate_limited_agent, second_agent],
            ) as mock_build_agent:
                outcome = movie_inspector.inspect_movie(movie)

            from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

            assert outcome.status == "consistent"
            assert mock_build_agent.call_args_list[0].args == (
                GEMINI_MODEL_PRIORITY[0],
            )
            assert mock_build_agent.call_args_list[1].args == (
                GEMINI_MODEL_PRIORITY[1],
            )

    def test_rate_limit_on_every_model_raises_all_exhausted(self, app):
        from google.genai.errors import ClientError

        from flask_backend.service.gemini_models import (
            GEMINI_MODEL_PRIORITY,
            AllGeminiModelsExhausted,
        )

        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            rate_limited_agent = MagicMock()
            rate_limited_agent.run.side_effect = ClientError(code=429, response_json={})

            with (
                patch.object(
                    movie_inspector, "_build_agent", return_value=rate_limited_agent
                ) as mock_build_agent,
                pytest.raises(AllGeminiModelsExhausted),
            ):
                movie_inspector.inspect_movie(movie)

            assert mock_build_agent.call_count == len(GEMINI_MODEL_PRIORITY)

    def test_consistent_verdict_leaves_movie_untouched(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie.original_title = "Original"
            db_session.add(movie)
            db_session.commit()

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(status="consistent", reasoning="Tudo ok.")
            )
            with patch.object(movie_inspector, "_build_agent", return_value=fake_agent):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "consistent"
            assert outcome.reasoning == "Tudo ok."
            assert movie.original_title == "Original"

    def test_fixed_verdict_applies_rematch_and_captures_snapshots(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            details = {
                "directors": [{"id": 1, "name": "Jean-Michel Tchissoukou"}],
                "genres": [],
                "countries": [],
                "collection": None,
                "original_title": "A Capela",
                "release_year": 1979,
                "original_language": "fr",
            }

            fake_agent = MagicMock()
            fake_agent.run.side_effect = [
                # The id must be observed via a tool call before a "fixed"
                # verdict is allowed to apply it.
                self._decision(action="get_tmdb_details", tmdb_id=573412),
                self._decision(
                    verdict=self._verdict(
                        status="fixed",
                        reasoning="Diretor e ano batem com o TMDB id 573412.",
                        new_tmdb_id=573412,
                    )
                ),
            ]
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                patch.object(
                    movie_inspector.TMDBClient,
                    "get_movie_details",
                    return_value=details,
                ),
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "fixed"
            assert movie.tmdb_id == 573412
            assert outcome.before_snapshot["tmdb_id"] == 1
            assert outcome.after_snapshot["tmdb_id"] == 573412

    def test_fixed_verdict_without_new_tmdb_id_becomes_needs_review(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(
                    status="fixed", reasoning="Sem id.", new_tmdb_id=None
                )
            )
            with patch.object(movie_inspector, "_build_agent", return_value=fake_agent):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert movie.tmdb_id == 1

    def test_fixed_verdict_with_unobserved_tmdb_id_becomes_needs_review(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(
                    status="fixed",
                    reasoning="Confio que é o id 999999.",
                    new_tmdb_id=999999,
                )
            )
            with patch.object(movie_inspector, "_build_agent", return_value=fake_agent):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert movie.tmdb_id == 1

    def test_unobserved_tmdb_id_guard_logs_warning(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(
                    status="fixed",
                    reasoning="Confio que é o id 999999.",
                    new_tmdb_id=999999,
                )
            )
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                caplog.at_level("WARNING", logger=movie_inspector.__name__),
            ):
                movie_inspector.inspect_movie(movie)

            messages = [r.getMessage() for r in caplog.records]
            assert any(
                str(movie.id) in m and "999999" in m and "não foi observado" in m
                for m in messages
            )

    def test_rejects_fetch_screening_source_for_a_different_movies_screening(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie(tmdb_id=1)
            other_movie = Movie(title="Outro Filme", slug="outro-filme", tmdb_id=2)
            db_session.add(other_movie)
            db_session.commit()
            other_screening = Screening(
                movie_id=other_movie.id,
                cinema_id=cinema.id,
                description="desc",
                url="https://example.com/outro",
            )
            db_session.add(other_screening)
            db_session.commit()

            fake_agent = MagicMock()
            fake_agent.run.side_effect = [
                self._decision(
                    action="fetch_screening_source", screening_id=other_screening.id
                ),
                self._decision(
                    verdict=self._verdict(status="needs_review", reasoning="Incerto.")
                ),
            ]
            with patch.object(movie_inspector, "_build_agent", return_value=fake_agent):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            second_call_input = fake_agent.run.call_args_list[1].args[0]
            assert any(
                "não pertence" in observation
                for observation in second_call_input.observations
            )

    def test_dispatches_search_tool_then_concludes(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.side_effect = [
                self._decision(
                    action="search_tmdb_candidates", search_title="A Capela"
                ),
                self._decision(
                    verdict=self._verdict(status="needs_review", reasoning="Incerto.")
                ),
            ]
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                patch.object(
                    movie_inspector.TMDBClient,
                    "search_movies",
                    return_value=[
                        {"id": 573412, "title": "A Capela", "release_date": "1979"}
                    ],
                ),
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert fake_agent.run.call_count == 2
            second_call_input = fake_agent.run.call_args_list[1].args[0]
            assert any(
                "573412" in observation
                for observation in second_call_input.observations
            )

    def test_logs_each_turns_decision_and_tool_dispatch_at_debug(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.side_effect = [
                self._decision(
                    action="search_tmdb_candidates", search_title="A Capela"
                ),
                self._decision(
                    verdict=self._verdict(status="needs_review", reasoning="Incerto.")
                ),
            ]
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                patch.object(
                    movie_inspector.TMDBClient,
                    "search_movies",
                    return_value=[
                        {"id": 573412, "title": "A Capela", "release_date": "1979"}
                    ],
                ),
                caplog.at_level("DEBUG", logger=movie_inspector.__name__),
            ):
                movie_inspector.inspect_movie(movie)

            messages = [r.getMessage() for r in caplog.records]
            assert any(
                "turno 1" in m and "search_tmdb_candidates" in m for m in messages
            )
            assert any(
                "search_tmdb_candidates" in m and "573412" in m for m in messages
            )
            assert any("turno 2" in m and "conclude" in m for m in messages)

    def test_dispatches_get_tmdb_details_tool_then_concludes(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            details = {
                "directors": [{"id": 1, "name": "Jean-Michel Tchissoukou"}],
                "genres": [],
                "countries": [],
                "collection": None,
                "original_title": "A Capela",
                "release_year": 1979,
                "original_language": "fr",
            }

            fake_agent = MagicMock()
            fake_agent.run.side_effect = [
                self._decision(action="get_tmdb_details", tmdb_id=573412),
                self._decision(
                    verdict=self._verdict(status="needs_review", reasoning="Incerto.")
                ),
            ]
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                patch.object(
                    movie_inspector.TMDBClient,
                    "get_movie_details",
                    return_value=details,
                ),
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert fake_agent.run.call_count == 2
            second_call_input = fake_agent.run.call_args_list[1].args[0]
            assert any(
                "Jean-Michel Tchissoukou" in observation or "573412" in observation
                for observation in second_call_input.observations
            )

    def test_conclude_without_verdict_retries_until_valid_verdict(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.side_effect = [
                self._decision(action="conclude", verdict=None),
                self._decision(
                    verdict=self._verdict(status="consistent", reasoning="ok")
                ),
            ]
            with patch.object(movie_inspector, "_build_agent", return_value=fake_agent):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "consistent"
            assert fake_agent.run.call_count == 2

    def test_stops_after_max_tool_calls_with_needs_review(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                action="fetch_screening_source", screening_id=1
            )
            with patch.object(movie_inspector, "_build_agent", return_value=fake_agent):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert fake_agent.run.call_count == movie_inspector.MAX_TOOL_CALLS


class TestRunPipeline:
    @pytest.fixture(autouse=True)
    def _gemini_key(self):
        # run_pipeline fails fast without a key, and CI has no .env, so
        # these tests must not depend on the ambient environment.
        with patch.object(movie_inspector, "GEMINI_API_KEY", "fake-key"):
            yield

    def test_records_one_row_per_movie_and_tallies_result(self, app):
        with app.app_context():
            movie_a = _create_movie(tmdb_id=1)
            movie_a.slug = "movie-a"
            movie_b = Movie(title="Filme B", slug="filme-b", tmdb_id=2)
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            outcomes = {
                movie_a.id: movie_inspector.InspectionOutcome(
                    status="consistent", reasoning="ok"
                ),
                movie_b.id: movie_inspector.InspectionOutcome(
                    status="needs_review", reasoning="incerto"
                ),
            }
            with patch.object(
                movie_inspector,
                "inspect_movie",
                side_effect=lambda movie: outcomes[movie.id],
            ):
                result = movie_inspector.run_pipeline()

            assert result.processed == 2
            assert result.consistent == 1
            assert result.needs_review == 1

            from flask_backend.repository import movie_inspections

            rows, _, total = movie_inspections.get_paginated(None, 1, 20)
            assert total == 2

    def test_respects_limit(self, app):
        with app.app_context():
            for i in range(3):
                movie = Movie(title=f"Filme {i}", slug=f"filme-{i}", tmdb_id=i + 1)
                db_session.add(movie)
            db_session.commit()

            with patch.object(
                movie_inspector,
                "inspect_movie",
                return_value=movie_inspector.InspectionOutcome(
                    status="consistent", reasoning="ok"
                ),
            ):
                result = movie_inspector.run_pipeline(limit=2)

            assert result.processed == 2

    def test_records_error_status_and_continues_on_exception(self, app):
        with app.app_context():
            movie_a = _create_movie(tmdb_id=1)
            movie_b = Movie(title="Filme B", slug="filme-b", tmdb_id=2)
            db_session.add(movie_b)
            db_session.commit()

            def fake_inspect(movie):
                if movie.id == movie_a.id:
                    raise RuntimeError("gemini indisponível")
                return movie_inspector.InspectionOutcome(
                    status="consistent", reasoning="ok"
                )

            with patch.object(
                movie_inspector, "inspect_movie", side_effect=fake_inspect
            ):
                result = movie_inspector.run_pipeline()

            assert result.errors == 1
            assert result.consistent == 1
            assert result.processed == 2

            from flask_backend.repository import movie_inspections

            rows, _, _ = movie_inspections.get_paginated("error", 1, 20)
            assert len(rows) == 1
            assert "gemini indisponível" in rows[0].reasoning

    def test_tags_rows_with_pipeline_run_id(self, app):
        with app.app_context():
            _create_movie(tmdb_id=1)

            with patch.object(
                movie_inspector,
                "inspect_movie",
                return_value=movie_inspector.InspectionOutcome(
                    status="consistent", reasoning="ok"
                ),
            ):
                movie_inspector.run_pipeline(pipeline_run_id=99)

            from flask_backend.repository import movie_inspections

            rows, _, _ = movie_inspections.get_paginated(None, 1, 20)
            assert rows[0].pipeline_run_id == 99

    def test_fixed_outcome_records_checked_tmdb_id_as_the_pre_fix_value(self, app):
        with app.app_context():
            _create_movie(tmdb_id=1)

            def fake_inspect(m):
                m.tmdb_id = 573412  # simulate inspect_movie having applied a fix
                return movie_inspector.InspectionOutcome(
                    status="fixed",
                    reasoning="ok",
                    before_snapshot={"tmdb_id": 1},
                    after_snapshot={"tmdb_id": 573412},
                )

            with patch.object(
                movie_inspector, "inspect_movie", side_effect=fake_inspect
            ):
                movie_inspector.run_pipeline()

            from flask_backend.repository import movie_inspections

            rows, _, _ = movie_inspections.get_paginated("fixed", 1, 20)
            assert rows[0].checked_tmdb_id == 1

    def test_raises_immediately_when_gemini_api_key_is_unset(self, app):
        with app.app_context():
            _create_movie(tmdb_id=1)
            with (
                patch.object(movie_inspector, "GEMINI_API_KEY", None),
                pytest.raises(ValueError),
            ):
                movie_inspector.run_pipeline()


class TestRevertInspection:
    def test_reverts_to_the_previous_tmdb_id(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=573412)
            movie.original_title = "A Capela"
            db_session.add(movie)
            db_session.commit()

            from flask_backend.repository import movie_inspections

            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Rematched.",
                checked_tmdb_id=573412,
                previous_snapshot=json.dumps({"tmdb_id": 1, "title": "Filme de Teste"}),
                new_snapshot=json.dumps({"tmdb_id": 573412, "title": "A Capela"}),
            )

            details = {
                "directors": [],
                "genres": [],
                "countries": [],
                "collection": None,
                "original_title": None,
                "release_year": None,
                "original_language": None,
            }
            with patch.object(
                movie_inspector.TMDBClient, "get_movie_details", return_value=details
            ):
                reverted = movie_inspector.revert_inspection(inspection.id)

            assert movie.tmdb_id == 1
            assert reverted.status == "reverted"
            assert reverted.movie_id == movie.id

    def test_reverting_to_previously_unmatched_clears_tmdb_id(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=573412)

            from flask_backend.repository import movie_inspections

            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Rematched.",
                checked_tmdb_id=573412,
                previous_snapshot=json.dumps({"tmdb_id": None}),
                new_snapshot=json.dumps({"tmdb_id": 573412}),
            )

            movie_inspector.revert_inspection(inspection.id)

            assert movie.tmdb_id is None

    def test_raises_for_non_fixed_inspection(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            from flask_backend.repository import movie_inspections

            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="ok",
                checked_tmdb_id=1,
            )

            with pytest.raises(ValueError):
                movie_inspector.revert_inspection(inspection.id)

    def test_raises_for_a_stale_fixed_inspection(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            from flask_backend.repository import movie_inspections

            # inspection #1: fixed 1 -> 42
            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Primeira correção.",
                checked_tmdb_id=1,
                previous_snapshot=json.dumps({"tmdb_id": 1}),
                new_snapshot=json.dumps({"tmdb_id": 42}),
            )
            # simulate a later, newer fix having moved the movie on again
            movie.tmdb_id = 99
            db_session.add(movie)
            db_session.commit()

            with pytest.raises(ValueError):
                movie_inspector.revert_inspection(inspection.id)

    def test_stale_inspection_rejection_logs_warning(self, app, caplog):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            from flask_backend.repository import movie_inspections

            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Primeira correção.",
                checked_tmdb_id=1,
                previous_snapshot=json.dumps({"tmdb_id": 1}),
                new_snapshot=json.dumps({"tmdb_id": 42}),
            )
            movie.tmdb_id = 99
            db_session.add(movie)
            db_session.commit()

            with (
                pytest.raises(ValueError),
                caplog.at_level("WARNING", logger=movie_inspector.__name__),
            ):
                movie_inspector.revert_inspection(inspection.id)

            messages = [r.getMessage() for r in caplog.records]
            assert any(str(inspection.id) in m and "recusado" in m for m in messages)

    def test_reverting_leaves_the_original_row_unchanged(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            from flask_backend.repository import movie_inspections

            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Rematched.",
                checked_tmdb_id=1,
                previous_snapshot=json.dumps({"tmdb_id": 1}),
                new_snapshot=json.dumps({"tmdb_id": 42}),
            )
            details = {
                "directors": [],
                "genres": [],
                "countries": [],
                "collection": None,
                "original_title": None,
                "release_year": None,
                "original_language": None,
            }
            with patch.object(
                movie_inspector.TMDBClient, "get_movie_details", return_value=details
            ):
                movie_inspector.revert_inspection(inspection.id)

            reloaded = movie_inspections.get_by_id(inspection.id)
            assert reloaded.status == "fixed"
