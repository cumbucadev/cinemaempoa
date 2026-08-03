"""
Tests the detect-motifs CLI command in flask_backend/commands.py.
"""

import json
from datetime import date, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_sync import sync_graph


class TestDetectMotifsCommand:
    def _seed_two_movies_by_same_director(self):
        director = get_or_create_director(1, "Wim Wenders")
        movie_a = Movie(title="Paris, Texas", slug="paris-texas")
        movie_a.directors = [director]
        movie_a.screenings = [
            Screening(
                cinema_id=get_cinema_by_slug("capitolio").id,
                description="d",
                draft=False,
                dates=[
                    ScreeningDate(date=date.today() + timedelta(days=1), time="19:00")
                ],
            )
        ]
        movie_b = Movie(title="Perfect Days", slug="perfect-days")
        movie_b.directors = [director]
        movie_b.screenings = [
            Screening(
                cinema_id=get_cinema_by_slug("capitolio").id,
                description="d",
                draft=False,
                dates=[
                    ScreeningDate(date=date.today() + timedelta(days=2), time="19:00")
                ],
            )
        ]
        db_session.add_all([movie_a, movie_b])
        db_session.commit()

    def test_prints_ranked_observations_as_a_table(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            self._seed_two_movies_by_same_director()
            sync_graph()

        result = runner.invoke(args=["detect-motifs"])

        assert result.exit_code == 0
        assert "multiple_movies_same_director" in result.output
        assert "Wim Wenders" in result.output

    def test_json_flag_prints_full_observation_objects(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            self._seed_two_movies_by_same_director()
            sync_graph()

        result = runner.invoke(args=["detect-motifs", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["motif_name"] == "multiple_movies_same_director"
        assert "evidence" in payload[0]

    def test_limit_option_caps_the_number_of_results(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            self._seed_two_movies_by_same_director()
            sync_graph()

        result = runner.invoke(args=["detect-motifs", "--json", "--limit", "0"])

        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_no_observations_prints_no_results_message(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            sync_graph()

        result = runner.invoke(args=["detect-motifs"])

        assert result.exit_code == 0
        assert "Nenhuma observação." in result.output

    def test_missing_graph_file_raises_usage_error_naming_sync_graph(
        self, app, runner, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "never-synced.db")
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )

        result = runner.invoke(args=["detect-motifs"])

        assert result.exit_code != 0
        assert db_path in result.output
        assert "sync-graph" in result.output
