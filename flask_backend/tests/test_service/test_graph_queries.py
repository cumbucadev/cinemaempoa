"""
Tests flask_backend/service/graph_queries.py.
"""

from datetime import date, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_queries import (
    directors_currently_showing,
    movies_by_director,
)
from flask_backend.service.graph_sync import sync_graph


class TestMoviesByDirector:
    def test_returns_movies_directed_by_the_given_name(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie = Movie(title="Paris, Texas", slug="paris-texas")
            movie.directors = [director]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = movies_by_director("Wim Wenders", db_path=db_path)

            assert results == [{"title": "Paris, Texas", "slug": "paris-texas"}]

    def test_returns_empty_list_for_unknown_director(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert movies_by_director("Ninguém", db_path=db_path) == []


class TestDirectorsCurrentlyShowing:
    def test_returns_directors_with_an_upcoming_screening(
        self, app, setup_cinemas, tmp_path
    ):
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

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = directors_currently_showing(db_path=db_path)

            assert results == [{"name": "Agnès Varda"}]

    def test_excludes_directors_whose_movies_have_only_past_screenings(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Diretor do Passado")
            movie = Movie(title="Filme Antigo", slug="filme-antigo")
            movie.directors = [director]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(
                            date=date.today() - timedelta(days=30), time="19:00"
                        )
                    ],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert directors_currently_showing(db_path=db_path) == []
