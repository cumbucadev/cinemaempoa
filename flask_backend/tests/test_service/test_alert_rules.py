from datetime import datetime

from flask_backend.db import db_session
from flask_backend.models import Collection, Director, Genre, Movie, Screening
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.alert_rules import (
    evaluate_director_debut,
    evaluate_mostra,
    evaluate_new_genre_combination,
    evaluate_new_movie,
    evaluate_returning_director,
    evaluate_sequel_or_franchise,
    evaluate_sessao_comentada,
    evaluate_single_screening,
)


def _create_movie(title, slug, created_at=None, **extra):
    movie = Movie(
        title=title, slug=slug, created_at=created_at or datetime.now(), **extra
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, cinema_slug, dates=None, created_at=None, **extra):
    cinema = get_cinema_by_slug(cinema_slug)
    defaults = {
        "description": "desc",
        "image": None,
        "image_alt": None,
        "image_width": None,
        "image_height": None,
        "draft": False,
        "url": None,
    }
    defaults.update(extra)
    screening = Screening(
        movie_id=movie.id,
        cinema_id=cinema.id,
        created_at=created_at or datetime.now(),
        **defaults,
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    from flask_backend.models import ScreeningDate

    for screening_date, screening_time in dates or [(datetime.now().date(), "20:00")]:
        db_session.add(
            ScreeningDate(
                screening_id=screening.id, date=screening_date, time=screening_time
            )
        )
    db_session.commit()
    db_session.refresh(screening)
    return screening


class TestEvaluateNewMovie:
    def test_fires_for_movies_first_screening(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie, "capitolio", created_at=datetime(2026, 1, 1)
            )

            candidate = evaluate_new_movie(screening)

            assert candidate is not None
            assert candidate.rule_name == "new_movie"
            assert candidate.dedup_key == f"new_movie:{movie.id}"

    def test_does_not_fire_for_a_later_screening_of_the_same_movie(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            _create_screening(movie, "capitolio", created_at=datetime(2026, 1, 1))
            later_screening = _create_screening(
                movie, "cinebancarios", created_at=datetime(2026, 1, 2)
            )

            candidate = evaluate_new_movie(later_screening)

            assert candidate is None


class TestEvaluateSingleScreening:
    def test_fires_when_exactly_one_date(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie, "capitolio", dates=[(datetime(2026, 1, 1).date(), "20:00")]
            )

            candidate = evaluate_single_screening(screening)

            assert candidate is not None
            assert candidate.dedup_key == f"single_screening:{screening.id}"

    def test_does_not_fire_when_multiple_dates(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie,
                "capitolio",
                dates=[
                    (datetime(2026, 1, 1).date(), "20:00"),
                    (datetime(2026, 1, 2).date(), "20:00"),
                ],
            )

            assert evaluate_single_screening(screening) is None


class TestEvaluateSessaoComentadaAndMostra:
    def test_sessao_comentada_fires_on_matching_rule(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie, "capitolio", title_cleaning_rules="sessao_comentada_suffix"
            )

            assert evaluate_sessao_comentada(screening) is not None
            assert evaluate_mostra(screening) is None

    def test_mostra_fires_on_matching_rule(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie, "capitolio", title_cleaning_rules="sessao_strand,cinema_pipe"
            )

            assert evaluate_mostra(screening) is not None
            assert evaluate_sessao_comentada(screening) is None

    def test_neither_fires_without_matching_rules(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie, "capitolio", title_cleaning_rules="cinema_pipe"
            )

            assert evaluate_mostra(screening) is None
            assert evaluate_sessao_comentada(screening) is None


class TestEvaluateDirectorRules:
    def test_debut_fires_for_the_earlier_movie_only(self, client, app, setup_cinemas):
        with client.application.app_context():
            director = Director(tmdb_id=1, name="Jane Director")
            db_session.add(director)
            db_session.commit()

            earlier = _create_movie(
                "Primeiro", "primeiro", created_at=datetime(2020, 1, 1)
            )
            earlier.directors.append(director)
            later = _create_movie("Segundo", "segundo", created_at=datetime(2021, 1, 1))
            later.directors.append(director)
            db_session.commit()

            assert evaluate_director_debut(earlier) is not None
            assert evaluate_director_debut(later) is None

    def test_returning_fires_for_the_later_movie_only(self, client, app, setup_cinemas):
        with client.application.app_context():
            director = Director(tmdb_id=1, name="Jane Director")
            db_session.add(director)
            db_session.commit()

            earlier = _create_movie(
                "Primeiro", "primeiro", created_at=datetime(2020, 1, 1)
            )
            earlier.directors.append(director)
            later = _create_movie("Segundo", "segundo", created_at=datetime(2021, 1, 1))
            later.directors.append(director)
            db_session.commit()

            assert evaluate_returning_director(earlier) is None
            candidate = evaluate_returning_director(later)
            assert candidate is not None
            assert candidate.dedup_key == f"returning_director:{later.id}"


class TestEvaluateNewGenreCombination:
    def test_fires_for_the_first_movie_with_a_given_combination_only(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            drama = Genre(tmdb_id=1, name="Drama")
            comedy = Genre(tmdb_id=2, name="Comédia")
            db_session.add_all([drama, comedy])
            db_session.commit()

            first = _create_movie(
                "Primeiro", "primeiro", created_at=datetime(2020, 1, 1)
            )
            first.genres.append(drama)
            second = _create_movie(
                "Segundo", "segundo", created_at=datetime(2021, 1, 1)
            )
            second.genres.append(drama)
            third = _create_movie(
                "Terceiro", "terceiro", created_at=datetime(2022, 1, 1)
            )
            third.genres.append(comedy)
            db_session.commit()

            assert evaluate_new_genre_combination(first) is not None
            assert evaluate_new_genre_combination(second) is None
            assert evaluate_new_genre_combination(third) is not None

    def test_does_not_fire_for_movie_without_genres(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            assert evaluate_new_genre_combination(movie) is None


class TestEvaluateSequelOrFranchise:
    def test_fires_only_for_the_later_movie_in_a_shared_collection(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            collection = Collection(tmdb_id=1, name="Bacurau Collection")
            db_session.add(collection)
            db_session.commit()

            earlier = _create_movie(
                "Bacurau",
                "bacurau",
                created_at=datetime(2020, 1, 1),
                collection_id=collection.id,
            )
            later = _create_movie(
                "Bacurau 2",
                "bacurau-2",
                created_at=datetime(2021, 1, 1),
                collection_id=collection.id,
            )

            assert evaluate_sequel_or_franchise(earlier) is None
            candidate = evaluate_sequel_or_franchise(later)
            assert candidate is not None
            assert candidate.dedup_key == f"sequel_or_franchise:{later.id}"

    def test_does_not_fire_without_a_collection(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            assert evaluate_sequel_or_franchise(movie) is None
