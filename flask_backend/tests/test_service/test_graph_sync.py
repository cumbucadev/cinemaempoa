"""
Tests flask_backend/service/graph_sync.py.
"""

from datetime import date

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
from flask_backend.service.graph_sync import build_graph_data


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
