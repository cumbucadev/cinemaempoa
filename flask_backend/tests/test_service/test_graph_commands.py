"""
Tests the sync-graph and graph-query CLI commands in flask_backend/commands.py.
"""

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_sync import sync_graph


class TestSyncGraphCommand:
    def test_reports_node_and_edge_counts(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "flask_backend.service.graph_sync.GRAPH_DB_PATH", str(tmp_path / "graph.db")
        )

        result = runner.invoke(args=["sync-graph"])

        assert result.exit_code == 0
        assert "nós" in result.output
        assert "arestas" in result.output


class TestGraphQueryCommand:
    def test_movies_by_director_prints_matching_titles(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.graph_queries.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie = Movie(title="Paris, Texas", slug="paris-texas")
            movie.directors = [director]
            db_session.add(movie)
            db_session.commit()
            sync_graph()

        result = runner.invoke(
            args=["graph-query", "movies-by-director", "--director", "Wim Wenders"]
        )

        assert result.exit_code == 0
        assert "Paris, Texas" in result.output

    def test_unknown_query_name_shows_usage_error(self, app, runner):
        result = runner.invoke(args=["graph-query", "not-a-real-query"])

        assert result.exit_code != 0
        assert "not-a-real-query" in result.output

    def test_missing_required_option_shows_usage_error(self, app, runner):
        result = runner.invoke(args=["graph-query", "movies-by-director"])

        assert result.exit_code != 0
        assert "--director" in result.output
