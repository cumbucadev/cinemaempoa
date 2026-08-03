"""
Tests flask_backend/service/graph_queries.py.
"""

import calendar
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
from flask_backend.service.graph_queries import (
    countries_this_month,
    directors_currently_showing,
    genres_at_cinema,
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


class TestCountriesThisMonth:
    def test_returns_countries_with_a_screening_this_month(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            country = get_or_create_by_iso_code("DE", "Germany")
            movie = Movie(title="Asas do Desejo", slug="asas-do-desejo")
            movie.countries = [country]
            today = date.today()
            last_day = calendar.monthrange(today.year, today.month)[1]
            mid_month = today.replace(day=min(15, last_day))
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=mid_month, time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert countries_this_month(db_path=db_path) == [{"name": "Germany"}]

    def test_excludes_countries_with_only_next_month_screenings(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            country = get_or_create_by_iso_code("FR", "France")
            movie = Movie(title="Filme Futuro", slug="filme-futuro")
            movie.countries = [country]
            today = date.today()
            next_month_year = today.year + (1 if today.month == 12 else 0)
            next_month = 1 if today.month == 12 else today.month + 1
            far_future_date = date(next_month_year + 1, next_month, 1)
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=far_future_date, time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert countries_this_month(db_path=db_path) == []


class TestGenresAtCinema:
    def test_returns_genres_shown_at_a_cinema_in_a_given_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            genre = get_or_create_genre(1, "Documentário")
            movie = Movie(title="Sans Soleil", slug="sans-soleil")
            movie.genres = [genre]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2025, 6, 10), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = genres_at_cinema("capitolio", 2025, db_path=db_path)

            assert results == [{"name": "Documentário"}]

    def test_excludes_screenings_from_other_years_or_cinemas(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            genre = get_or_create_genre(1, "Terror")
            movie = Movie(title="Filme de Outro Ano", slug="filme-de-outro-ano")
            movie.genres = [genre]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2024, 6, 10), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert genres_at_cinema("capitolio", 2025, db_path=db_path) == []
