"""
Tests the sync-graph and graph-query CLI commands in flask_backend/commands.py.
"""

from datetime import date, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.countries import get_or_create_by_iso_code
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.repository.genres import (
    get_or_create_by_tmdb_id as get_or_create_genre,
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

    def test_directors_currently_showing_prints_matching_director(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.graph_queries.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            director = get_or_create_director(1, "Agnès Varda")
            movie = Movie(title="Cléo de 5 à 7", slug="cleo-de-5-a-7")
            movie.directors = [director]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(
                            date=date.today() + timedelta(days=1), time="19:00"
                        )
                    ],
                )
            ]
            db_session.add(movie)
            db_session.commit()
            sync_graph()

        result = runner.invoke(args=["graph-query", "directors-currently-showing"])

        assert result.exit_code == 0
        assert "Agnès Varda" in result.output

    def test_countries_this_month_prints_matching_country(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.graph_queries.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            germany = get_or_create_by_iso_code("DE", "Germany")
            movie = Movie(title="Asas do Desejo", slug="asas-do-desejo")
            movie.countries = [germany]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date.today(), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()
            sync_graph()

        result = runner.invoke(args=["graph-query", "countries-this-month"])

        assert result.exit_code == 0
        assert "Germany" in result.output

    def test_genres_at_cinema_prints_matching_genre(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.graph_queries.GRAPH_DB_PATH", db_path
        )
        year = date.today().year
        with app.app_context():
            genre = get_or_create_genre(1, "Documentário")
            movie = Movie(title="Sans Soleil", slug="sans-soleil")
            movie.genres = [genre]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(year, 6, 10), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()
            sync_graph()

        result = runner.invoke(
            args=[
                "graph-query",
                "genres-at-cinema",
                "--cinema",
                "capitolio",
                "--year",
                str(year),
            ]
        )

        assert result.exit_code == 0
        assert "Documentário" in result.output

    def test_screenings_since_release_prints_matching_date(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.graph_queries.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            movie = Movie(title="Alice nas Cidades", slug="alice-nas-cidades")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2026, 8, 5), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()
            sync_graph()

        result = runner.invoke(
            args=[
                "graph-query",
                "screenings-since-release",
                "--movie",
                "alice-nas-cidades",
            ]
        )

        assert result.exit_code == 0
        assert "2026-08-05" in result.output

    def test_unknown_query_name_shows_usage_error(self, app, runner):
        result = runner.invoke(args=["graph-query", "not-a-real-query"])

        assert result.exit_code != 0
        assert "not-a-real-query" in result.output

    def test_missing_required_option_shows_usage_error(self, app, runner):
        result = runner.invoke(args=["graph-query", "movies-by-director"])

        assert result.exit_code != 0
        assert "--director" in result.output

    def test_genres_at_cinema_missing_options_shows_usage_error(self, app, runner):
        result = runner.invoke(args=["graph-query", "genres-at-cinema"])

        assert result.exit_code != 0
        assert "--cinema" in result.output
        assert "--year" in result.output

    def test_screenings_since_release_missing_movie_shows_usage_error(
        self, app, runner
    ):
        result = runner.invoke(args=["graph-query", "screenings-since-release"])

        assert result.exit_code != 0
        assert "--movie" in result.output

    def test_query_with_no_matching_rows_prints_no_results_message(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.graph_queries.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            get_or_create_director(1, "Diretor Sem Filmes")
            sync_graph()

        result = runner.invoke(
            args=[
                "graph-query",
                "movies-by-director",
                "--director",
                "Diretor Sem Filmes",
            ]
        )

        assert result.exit_code == 0
        assert "Nenhum resultado." in result.output
