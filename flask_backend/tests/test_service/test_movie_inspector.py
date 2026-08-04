from unittest.mock import MagicMock, patch

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
                observation = movie_inspector._run_search_tmdb_candidates("A Capela")

            assert "tmdb_id=573412" in observation
            assert "ano=1979" in observation
            assert "tmdb_id=999" in observation

    def test_reports_no_results(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient, "search_movies", return_value=[]
            ):
                observation = movie_inspector._run_search_tmdb_candidates("Xyz")

            assert "Nenhum resultado" in observation

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient,
                "search_movies",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = movie_inspector._run_search_tmdb_candidates("Xyz")

            assert "Erro" in observation


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
                observation = movie_inspector._run_get_tmdb_details(573412)

            assert "Jean-Michel Tchissoukou" in observation
            assert "1979" in observation
            assert "Congo" in observation

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient,
                "get_movie_details",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = movie_inspector._run_get_tmdb_details(1)

            assert "Erro" in observation


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
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(
                    status="fixed",
                    reasoning="Diretor e ano batem com o TMDB id 573412.",
                    new_tmdb_id=573412,
                )
            )
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
