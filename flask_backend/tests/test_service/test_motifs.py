"""
Tests flask_backend/service/motifs.py.
"""

import calendar
from datetime import date, timedelta

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
from flask_backend.service.graph_sync import sync_graph
from flask_backend.service.motifs import (
    MOTIF_REGISTRY,
    AnniversaryMotif,
    CinemaGenreFocusMotif,
    CountryClusterMotif,
    DirectorReturnMotif,
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


class TestDirectorReturnMotif:
    def test_flags_director_returning_after_a_long_gap(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Agnès Varda")
            old_movie = Movie(title="Filme Antigo", slug="filme-antigo")
            old_movie.directors = [director]
            old_movie.screenings = [_screening("capitolio", -200)]
            new_movie = Movie(title="Filme Novo", slug="filme-novo")
            new_movie.directors = [director]
            new_movie.screenings = [_screening("capitolio", 1)]
            db_session.add_all([old_movie, new_movie])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = DirectorReturnMotif().detect(graph)

            assert len(observations) == 1
            obs = observations[0]
            assert obs.motif_name == "director_return"
            assert obs.confidence == 0.7
            assert obs.metadata["director"] == "Agnès Varda"
            assert obs.metadata["movies"] == ["Filme Novo"]
            assert obs.metadata["gap_days"] >= 180

    def test_does_not_flag_director_with_a_short_gap(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Diretor Recente")
            old_movie = Movie(title="Filme Antigo", slug="filme-antigo")
            old_movie.directors = [director]
            old_movie.screenings = [_screening("capitolio", -30)]
            new_movie = Movie(title="Filme Novo", slug="filme-novo")
            new_movie.directors = [director]
            new_movie.screenings = [_screening("capitolio", 1)]
            db_session.add_all([old_movie, new_movie])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert DirectorReturnMotif().detect(graph) == []

    def test_does_not_flag_director_with_no_prior_screening_history(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Diretor Estreante")
            movie = Movie(title="Primeiro Filme", slug="primeiro-filme")
            movie.directors = [director]
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert DirectorReturnMotif().detect(graph) == []


def _this_month_date(day_offset=0):
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    day = min(15 + day_offset, last_day)
    return today.replace(day=day)


class TestCinemaGenreFocusMotif:
    def test_flags_genre_with_no_historical_precedent_and_min_count_met(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            cinema = get_cinema_by_slug("capitolio")
            for i in range(3):
                movie = Movie(title=f"Doc {i}", slug=f"doc-{i}")
                movie.genres = [doc_genre]
                movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = CinemaGenreFocusMotif().detect(graph)

            assert len(observations) == 1
            assert observations[0].motif_name == "cinema_genre_focus"
            assert observations[0].metadata["cinema"] == "Cinemateca Capitólio"
            assert observations[0].metadata["genre"] == "Documentário"

    def test_does_not_flag_genre_below_the_minimum_count(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            cinema = get_cinema_by_slug("capitolio")
            for i in range(2):
                movie = Movie(title=f"Doc {i}", slug=f"doc-{i}")
                movie.genres = [doc_genre]
                movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert CinemaGenreFocusMotif().detect(graph) == []

    def test_does_not_flag_genre_matching_its_historical_share(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            drama_genre = get_or_create_genre(2, "Drama")
            cinema = get_cinema_by_slug("capitolio")

            # Historical baseline: 3 documentaries, 3 dramas, all in the past
            # (outside this month) so current-period counts don't also
            # inflate the baseline disproportionately.
            for i in range(3):
                doc_movie = Movie(title=f"Doc Antigo {i}", slug=f"doc-antigo-{i}")
                doc_movie.genres = [doc_genre]
                doc_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=date(2025, 1, i + 1), time="19:00")],
                    )
                ]
                db_session.add(doc_movie)

                drama_movie = Movie(title=f"Drama Antigo {i}", slug=f"drama-antigo-{i}")
                drama_movie.genres = [drama_genre]
                drama_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=date(2025, 1, i + 1), time="19:00")],
                    )
                ]
                db_session.add(drama_movie)

            # Current period: same 1:1 ratio, at the minimum count.
            for i in range(3):
                doc_movie = Movie(title=f"Doc Novo {i}", slug=f"doc-novo-{i}")
                doc_movie.genres = [doc_genre]
                doc_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(doc_movie)

                drama_movie = Movie(title=f"Drama Novo {i}", slug=f"drama-novo-{i}")
                drama_movie.genres = [drama_genre]
                drama_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(drama_movie)

            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert CinemaGenreFocusMotif().detect(graph) == []


class TestAnniversaryMotif:
    def test_flags_movie_at_a_recognized_anniversary_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            anniversary_year = date.today().year - 50
            movie = Movie(
                title="Filme Clássico",
                slug="filme-classico",
                release_year=anniversary_year,
            )
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = AnniversaryMotif().detect(graph)

            assert len(observations) == 1
            assert observations[0].motif_name == "anniversary"
            assert observations[0].metadata["movie"] == "Filme Clássico"
            assert observations[0].metadata["years"] == 50

    def test_does_not_flag_movie_at_a_non_recognized_anniversary_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(
                title="Filme Comum",
                slug="filme-comum",
                release_year=date.today().year - 13,
            )
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert AnniversaryMotif().detect(graph) == []

    def test_does_not_flag_movie_with_no_release_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(title="Sem Ano", slug="sem-ano")
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert AnniversaryMotif().detect(graph) == []


class TestMotifRegistry:
    def test_contains_one_instance_of_each_motif(self):
        names = {motif.name for motif in MOTIF_REGISTRY}
        assert names == {
            "multiple_movies_same_director",
            "country_cluster",
            "director_return",
            "cinema_genre_focus",
            "anniversary",
        }
        assert len(MOTIF_REGISTRY) == 5
