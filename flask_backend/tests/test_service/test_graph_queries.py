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
    screenings_since_release,
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

    def test_excludes_directors_whose_only_upcoming_screening_is_a_draft(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(2, "Diretor Rascunho")
            movie = Movie(title="Filme Rascunho", slug="filme-rascunho")
            movie.directors = [director]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=True,
                    dates=[
                        ScreeningDate(
                            date=date.today() + timedelta(days=1), time="19:00"
                        )
                    ],
                )
            ]
            db_session.add(movie)

            # A published director/movie so the assertion proves the draft
            # is excluded rather than the query returning empty regardless.
            published_director = get_or_create_director(3, "Diretor Publicado")
            published_movie = Movie(title="Filme Publicado", slug="filme-publicado")
            published_movie.directors = [published_director]
            published_movie.screenings = [
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
            db_session.add(published_movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = directors_currently_showing(db_path=db_path)

            assert results == [{"name": "Diretor Publicado"}]

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
            germany = get_or_create_by_iso_code("DE", "Germany")
            mid_month_movie = Movie(title="Asas do Desejo", slug="asas-do-desejo")
            mid_month_movie.countries = [germany]
            today = date.today()
            last_day = calendar.monthrange(today.year, today.month)[1]
            mid_month = today.replace(day=min(15, last_day))
            mid_month_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=mid_month, time="19:00")],
                )
            ]
            db_session.add(mid_month_movie)

            # Boundary case: last day of the current month is inclusive.
            japan = get_or_create_by_iso_code("JP", "Japan")
            last_day_movie = Movie(
                title="Tóquio no Fim do Mês", slug="toquio-no-fim-do-mes"
            )
            last_day_movie.countries = [japan]
            last_day_date = today.replace(day=last_day)
            last_day_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=last_day_date, time="19:00")],
                )
            ]
            db_session.add(last_day_movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert countries_this_month(db_path=db_path) == [
                {"name": "Germany"},
                {"name": "Japan"},
            ]

    def test_excludes_countries_whose_only_screening_this_month_is_a_draft(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            country = get_or_create_by_iso_code("IT", "Italy")
            movie = Movie(title="Filme Rascunho", slug="filme-rascunho")
            movie.countries = [country]
            today = date.today()
            last_day = calendar.monthrange(today.year, today.month)[1]
            mid_month = today.replace(day=min(15, last_day))
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=True,
                    dates=[ScreeningDate(date=mid_month, time="19:00")],
                )
            ]
            db_session.add(movie)

            # A published country so the assertion proves the draft is
            # excluded rather than the query returning empty regardless.
            published_country = get_or_create_by_iso_code("ES", "Spain")
            published_movie = Movie(title="Filme Publicado", slug="filme-publicado")
            published_movie.countries = [published_country]
            published_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=mid_month, time="19:00")],
                )
            ]
            db_session.add(published_movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert countries_this_month(db_path=db_path) == [{"name": "Spain"}]

    def test_excludes_countries_with_only_next_month_screenings(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            country = get_or_create_by_iso_code("FR", "France")
            movie = Movie(title="Filme Futuro", slug="filme-futuro")
            movie.countries = [country]
            today = date.today()
            # Boundary case: the day right after the current month ends
            # (first day of next month) must be excluded.
            next_month_year = today.year + (1 if today.month == 12 else 0)
            next_month = 1 if today.month == 12 else today.month + 1
            first_day_next_month = date(next_month_year, next_month, 1)
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=first_day_next_month, time="19:00")],
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

    def test_excludes_draft_screenings(self, app, setup_cinemas, tmp_path):
        with app.app_context():
            draft_genre = get_or_create_genre(10, "Rascunho")
            draft_movie = Movie(title="Filme Rascunho", slug="filme-rascunho")
            draft_movie.genres = [draft_genre]
            draft_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=True,
                    dates=[ScreeningDate(date=date(2025, 6, 10), time="19:00")],
                )
            ]
            db_session.add(draft_movie)

            # A published movie/genre so the assertion proves the draft is
            # excluded rather than the query returning empty regardless.
            published_genre = get_or_create_genre(11, "Publicado")
            published_movie = Movie(title="Filme Publicado", slug="filme-publicado")
            published_movie.genres = [published_genre]
            published_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2025, 6, 10), time="19:00")],
                )
            ]
            db_session.add(published_movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert genres_at_cinema("capitolio", 2025, db_path=db_path) == [
                {"name": "Publicado"}
            ]

    def test_excludes_screenings_from_other_years_or_cinemas(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            other_year_genre = get_or_create_genre(1, "Terror")
            other_year_movie = Movie(
                title="Filme de Outro Ano", slug="filme-de-outro-ano"
            )
            other_year_movie.genres = [other_year_genre]
            other_year_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2024, 6, 10), time="19:00")],
                )
            ]
            db_session.add(other_year_movie)

            # Same year, but a different cinema: exercises the ci.slug filter
            # discriminating behavior, not just the year filter.
            other_cinema_genre = get_or_create_genre(2, "Suspense")
            other_cinema_movie = Movie(
                title="Filme de Outro Cinema", slug="filme-de-outro-cinema"
            )
            other_cinema_movie.genres = [other_cinema_genre]
            other_cinema_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("sala-redencao").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2025, 6, 10), time="19:00")],
                )
            ]
            db_session.add(other_cinema_movie)

            # A screening that actually matches cinema and year, so the
            # assertion below proves the other two are excluded rather
            # than the query just returning an empty result regardless.
            matching_genre = get_or_create_genre(3, "Aventura")
            matching_movie = Movie(title="Filme Certo", slug="filme-certo")
            matching_movie.genres = [matching_genre]
            matching_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2025, 7, 1), time="19:00")],
                )
            ]
            db_session.add(matching_movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert genres_at_cinema("capitolio", 2025, db_path=db_path) == [
                {"name": "Aventura"}
            ]

    def test_includes_screening_on_the_last_day_of_the_target_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            genre = get_or_create_genre(4, "Comédia")
            movie = Movie(title="Fim de Ano", slug="fim-de-ano")
            movie.genres = [genre]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2025, 12, 31), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert genres_at_cinema("capitolio", 2025, db_path=db_path) == [
                {"name": "Comédia"}
            ]

    def test_excludes_screening_on_the_first_day_of_the_next_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            genre = get_or_create_genre(5, "Drama")
            movie = Movie(title="Início de Ano", slug="inicio-de-ano")
            movie.genres = [genre]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2026, 1, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert genres_at_cinema("capitolio", 2025, db_path=db_path) == []


class TestScreeningsSinceRelease:
    def test_returns_every_screening_date_for_the_movie_in_order(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(title="Alice nas Cidades", slug="alice-nas-cidades")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(date=date(2026, 8, 10), time="21:00"),
                        ScreeningDate(date=date(2026, 8, 5), time="19:00"),
                    ],
                )
            ]
            db_session.add(movie)

            # A second movie with its own screening, so the assertion below
            # proves the movie_slug filter actually excludes it, rather than
            # the result happening to match because only one movie exists.
            other_movie = Movie(title="Outro Filme", slug="outro-filme")
            other_movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("sala-redencao").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(date=date(2026, 8, 1), time="20:00"),
                    ],
                )
            ]
            db_session.add(other_movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = screenings_since_release("alice-nas-cidades", db_path=db_path)

            assert results == [
                {
                    "date": "2026-08-05",
                    "time": "19:00",
                    "cinema_name": "Cinemateca Capitólio",
                },
                {
                    "date": "2026-08-10",
                    "time": "21:00",
                    "cinema_name": "Cinemateca Capitólio",
                },
            ]

    def test_returns_empty_list_for_a_movie_with_no_screenings(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(title="Sem Sessões", slug="sem-sessoes")
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert screenings_since_release("sem-sessoes", db_path=db_path) == []
