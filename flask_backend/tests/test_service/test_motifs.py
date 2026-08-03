"""
Tests flask_backend/service/motifs.py.
"""

from datetime import date, timedelta

from graphqlite import Graph

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.countries import get_or_create_by_iso_code
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_sync import sync_graph
from flask_backend.service.motifs import (
    CountryClusterMotif,
    MultipleMoviesSameDirectorMotif,
    _dedupe_preserve_order,
)


class TestDedupePreserveOrder:
    def test_removes_duplicates_keeping_first_occurrence_order(self):
        assert _dedupe_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_returns_empty_list_unchanged(self):
        assert _dedupe_preserve_order([]) == []

    def test_returns_list_with_no_duplicates_unchanged(self):
        assert _dedupe_preserve_order(["a", "b", "c"]) == ["a", "b", "c"]


def _screening(cinema_slug, days_from_today, draft=False):
    return Screening(
        cinema_id=get_cinema_by_slug(cinema_slug).id,
        description="d",
        draft=draft,
        dates=[
            ScreeningDate(
                date=date.today() + timedelta(days=days_from_today), time="19:00"
            )
        ],
    )


class TestMultipleMoviesSameDirectorMotif:
    def test_flags_director_with_two_currently_showing_movies(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie_a = Movie(title="Paris, Texas", slug="paris-texas")
            movie_a.directors = [director]
            movie_a.screenings = [_screening("capitolio", 1)]
            movie_b = Movie(title="Perfect Days", slug="perfect-days")
            movie_b.directors = [director]
            movie_b.screenings = [_screening("capitolio", 2)]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = MultipleMoviesSameDirectorMotif().detect(graph)

            assert len(observations) == 1
            obs = observations[0]
            assert obs.motif_name == "multiple_movies_same_director"
            assert obs.confidence == 1.0
            assert sorted(obs.metadata["movies"]) == sorted(
                ["Paris, Texas", "Perfect Days"]
            )
            assert obs.metadata["director"] == "Wim Wenders"
            assert (
                obs.metadata["next_screening_date"]
                == (date.today() + timedelta(days=1)).isoformat()
            )

    def test_does_not_flag_director_with_only_one_currently_showing_movie(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Agnès Varda")
            movie = Movie(title="Cléo de 5 à 7", slug="cleo-de-5-a-7")
            movie.directors = [director]
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert MultipleMoviesSameDirectorMotif().detect(graph) == []

    def test_excludes_draft_screenings_from_the_count(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Diretor")
            published = Movie(title="Publicado", slug="publicado")
            published.directors = [director]
            published.screenings = [_screening("capitolio", 1)]
            draft = Movie(title="Rascunho", slug="rascunho")
            draft.directors = [director]
            draft.screenings = [_screening("capitolio", 1, draft=True)]
            db_session.add_all([published, draft])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert MultipleMoviesSameDirectorMotif().detect(graph) == []


class TestCountryClusterMotif:
    def test_flags_country_with_two_currently_showing_movies(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            japan = get_or_create_by_iso_code("JP", "Japan")
            movie_a = Movie(title="Filme A", slug="filme-a")
            movie_a.countries = [japan]
            movie_a.screenings = [_screening("capitolio", 1)]
            movie_b = Movie(title="Filme B", slug="filme-b")
            movie_b.countries = [japan]
            movie_b.screenings = [_screening("capitolio", 2)]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = CountryClusterMotif().detect(graph)

            assert len(observations) == 1
            assert observations[0].motif_name == "country_cluster"
            assert observations[0].metadata["country"] == "Japan"
            assert sorted(observations[0].metadata["movies"]) == sorted(
                ["Filme A", "Filme B"]
            )

    def test_does_not_flag_country_with_only_one_currently_showing_movie(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            france = get_or_create_by_iso_code("FR", "France")
            movie = Movie(title="Filme Único", slug="filme-unico")
            movie.countries = [france]
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert CountryClusterMotif().detect(graph) == []
