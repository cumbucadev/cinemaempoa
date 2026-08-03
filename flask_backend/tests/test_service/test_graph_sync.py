"""
Tests flask_backend/service/graph_sync.py.
"""

from datetime import date

from graphqlite import Graph

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
from flask_backend.service.graph_sync import build_graph_data, sync_graph


class TestGraphqliteSmokeTest:
    def test_extension_loads_and_supports_basic_cypher(self, tmp_path):
        from graphqlite import Graph

        db_path = str(tmp_path / "smoke.db")
        graph = Graph(db_path)
        graph.upsert_node("a", {"name": "A"}, label="Thing")
        graph.upsert_node("b", {"name": "B"}, label="Thing")
        graph.upsert_edge("a", "b", {}, rel_type="RELATED")

        results = graph.query(
            "MATCH (x:Thing)-[:RELATED]->(y:Thing) "
            "RETURN x.name AS x_name, y.name AS y_name"
        )

        assert results == [{"x_name": "A", "y_name": "B"}]


class TestBuildGraphData:
    def test_builds_nodes_and_edges_for_a_full_movie_record(self, app, setup_cinemas):
        with app.app_context():
            genre = get_or_create_genre(1, "Drama")
            director = get_or_create_director(1, "Wim Wenders")
            country = get_or_create_by_iso_code("DE", "Germany")

            movie = Movie(
                title="Paris, Texas",
                slug="paris-texas",
                original_title="Paris, Texas",
                release_year=1984,
                original_language="en",
                tmdb_id=1071,
            )
            movie.genres = [genre]
            movie.directors = [director]
            movie.countries = [country]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()
            db_session.refresh(movie)
            screening = movie.screenings[0]
            screening_date = screening.dates[0]

            nodes, edges = build_graph_data()

            node_ids = {n[0] for n in nodes}
            assert f"movie:{movie.id}" in node_ids
            assert f"cinema:{get_cinema_by_slug('capitolio').id}" in node_ids
            assert f"genre:{genre.id}" in node_ids
            assert f"director:{director.id}" in node_ids
            assert f"country:{country.id}" in node_ids
            assert f"screening:{screening.id}" in node_ids
            assert f"screeningdate:{screening_date.id}" in node_ids

            movie_node = next(n for n in nodes if n[0] == f"movie:{movie.id}")
            assert movie_node == (
                f"movie:{movie.id}",
                {
                    "sqlite_id": movie.id,
                    "title": "Paris, Texas",
                    "slug": "paris-texas",
                    "original_title": "Paris, Texas",
                    "release_year": 1984,
                    "original_language": "en",
                    "tmdb_id": 1071,
                },
                "Movie",
            )

            screening_date_node = next(
                n for n in nodes if n[0] == f"screeningdate:{screening_date.id}"
            )
            assert screening_date_node == (
                f"screeningdate:{screening_date.id}",
                {"sqlite_id": screening_date.id, "date": "2026-08-01", "time": "19:00"},
                "ScreeningDate",
            )

            assert (
                f"movie:{movie.id}",
                f"genre:{genre.id}",
                {},
                "HAS_GENRE",
            ) in edges
            assert (
                f"movie:{movie.id}",
                f"director:{director.id}",
                {},
                "DIRECTED_BY",
            ) in edges
            assert (
                f"movie:{movie.id}",
                f"country:{country.id}",
                {},
                "PRODUCED_IN",
            ) in edges
            assert (
                f"movie:{movie.id}",
                f"screening:{screening.id}",
                {},
                "HAS_SCREENING",
            ) in edges
            assert (
                f"screening:{screening.id}",
                f"cinema:{get_cinema_by_slug('capitolio').id}",
                {},
                "AT_CINEMA",
            ) in edges
            assert (
                f"screening:{screening.id}",
                f"screeningdate:{screening_date.id}",
                {},
                "HAS_DATE",
            ) in edges

    def test_includes_movies_with_no_screenings_and_no_metadata(self, app):
        with app.app_context():
            movie = Movie(title="Sem Sessão", slug="sem-sessao")
            db_session.add(movie)
            db_session.commit()

            nodes, _edges = build_graph_data()

            node_ids = {n[0] for n in nodes}
            assert f"movie:{movie.id}" in node_ids

    def test_omits_null_props_instead_of_storing_the_string_none(self, app):
        """Regression test: nullable columns with no value (slug,
        original_title, release_year, original_language, tmdb_id are all
        None here) must be absent from the props dict entirely, not merely
        present with a None value - GraphQLite has no null support and
        serializes a present-but-None value as the literal text "None"."""
        with app.app_context():
            movie = Movie(title="Sem Metadados")
            db_session.add(movie)
            db_session.commit()

            nodes, _edges = build_graph_data()

            movie_node = next(n for n in nodes if n[0] == f"movie:{movie.id}")
            props = movie_node[1]

            assert props == {"sqlite_id": movie.id, "title": "Sem Metadados"}
            assert "slug" not in props
            assert "original_title" not in props
            assert "release_year" not in props
            assert "original_language" not in props
            assert "tmdb_id" not in props


class TestSyncGraph:
    def test_writes_nodes_and_edges_to_the_graph_file(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(title="Ariabescos", slug="ariabescos")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            result = sync_graph(db_path=db_path)

            assert result.nodes_created > 0
            assert result.edges_created > 0

            graph = Graph(db_path)
            rows = graph.query(
                "MATCH (m:Movie) WHERE m.slug = 'ariabescos' RETURN m.title AS title"
            )
            assert rows == [{"title": "Ariabescos"}]

    def test_null_props_come_back_as_real_nulls_not_the_string_none(
        self, app, tmp_path
    ):
        """End-to-end regression test for the "None" string bug: syncs a
        movie with no release_year to a real GraphQLite file and queries it
        back through the extension itself (not just build_graph_data's
        in-memory tuples)."""
        with app.app_context():
            movie = Movie(title="Sem Ano", slug="sem-ano")
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            graph = Graph(db_path)
            rows = graph.query(
                "MATCH (m:Movie) WHERE m.slug = 'sem-ano' "
                "RETURN m.release_year AS release_year"
            )
            assert rows == [{"release_year": None}]

            null_rows = graph.query(
                "MATCH (m:Movie) WHERE m.slug = 'sem-ano' AND "
                "m.release_year IS NULL RETURN m.title AS title"
            )
            assert null_rows == [{"title": "Sem Ano"}]

    def test_is_idempotent_and_removes_stale_data_on_rerun(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            db_path = str(tmp_path / "graph.db")

            # Seed a node that has no corresponding SQLite row.
            stale_graph = Graph(db_path)
            stale_graph.upsert_node("movie:999999", {"title": "Stale"}, label="Movie")

            movie = Movie(title="Filme Real", slug="filme-real")
            db_session.add(movie)
            db_session.commit()

            first = sync_graph(db_path=db_path)
            second = sync_graph(db_path=db_path)

            assert first.nodes_created == second.nodes_created
            assert first.edges_created == second.edges_created

            graph = Graph(db_path)
            rows = graph.query(
                "MATCH (m:Movie) WHERE m.title = 'Stale' RETURN m.title AS title"
            )
            assert rows == []
