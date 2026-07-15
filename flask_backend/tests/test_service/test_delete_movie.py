from datetime import date, datetime
from unittest.mock import patch

from flask_backend.db import db_session
from flask_backend.models import (
    Director,
    Genre,
    Movie,
    MovieMetadataFetchAttempt,
    PosterFetchAttempt,
    Screening,
    ScreeningDate,
)
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.scripts.delete_movie import delete_movie


def _create_movie(title, slug, **extra):
    movie = Movie(title=title, slug=slug, **extra)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, cinema_slug, dates=None):
    cinema = get_cinema_by_slug(cinema_slug)
    screening = Screening(movie_id=movie.id, cinema_id=cinema.id, description="desc")
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    for screening_date, screening_time in dates or []:
        db_session.add(
            ScreeningDate(
                screening_id=screening.id, date=screening_date, time=screening_time
            )
        )
    db_session.commit()
    db_session.refresh(screening)
    return screening


class TestDeleteMovieWithoutScreenings:
    def test_deletes_movie(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            movie_id = movie.id

            deleted = delete_movie(movie_id, skip_confirmation=True)

            assert deleted is True
            assert db_session.query(Movie).filter_by(id=movie_id).first() is None


class TestDeleteMovieWithRelatedRows:
    def test_deletes_screenings_dates_and_fetch_attempts(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie, "capitolio", dates=[(date(2026, 1, 1), "20:00")]
            )
            screening_id = screening.id
            db_session.add(
                MovieMetadataFetchAttempt(
                    movie_id=movie.id,
                    source="tmdb",
                    status="not_found",
                    attempted_at=datetime.now(),
                )
            )
            db_session.add(
                PosterFetchAttempt(
                    screening_id=screening.id,
                    source="tmdb",
                    status="not_found",
                    attempted_at=datetime.now(),
                )
            )
            db_session.commit()
            movie_id = movie.id

            deleted = delete_movie(movie_id, skip_confirmation=True)

            assert deleted is True
            assert db_session.query(Movie).filter_by(id=movie_id).first() is None
            assert (
                db_session.query(Screening).filter_by(id=screening_id).first() is None
            )
            assert (
                db_session.query(ScreeningDate)
                .filter_by(screening_id=screening_id)
                .count()
                == 0
            )
            assert (
                db_session.query(MovieMetadataFetchAttempt)
                .filter_by(movie_id=movie_id)
                .count()
                == 0
            )
            assert (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .count()
                == 0
            )

    def test_removes_associations_without_deleting_shared_rows(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            genre = Genre(tmdb_id=1, name="Drama")
            director = Director(tmdb_id=1, name="Someone")
            db_session.add_all([genre, director])
            db_session.commit()

            movie = _create_movie("Filme", "filme")
            movie.genres.append(genre)
            movie.directors.append(director)
            db_session.commit()
            movie_id = movie.id
            genre_id = genre.id
            director_id = director.id

            deleted = delete_movie(movie_id, skip_confirmation=True)

            assert deleted is True
            assert db_session.query(Movie).filter_by(id=movie_id).first() is None
            assert db_session.query(Genre).filter_by(id=genre_id).first() is not None
            assert (
                db_session.query(Director).filter_by(id=director_id).first() is not None
            )


class TestDeleteMovieNotFound:
    def test_returns_false_without_changing_the_database(self, client, app):
        with client.application.app_context():
            deleted = delete_movie(999999, skip_confirmation=True)

            assert deleted is False


class TestDeleteMovieConfirmation:
    def test_declining_confirmation_keeps_the_movie(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            movie_id = movie.id

            with patch("click.confirm", return_value=False):
                deleted = delete_movie(movie_id)

            assert deleted is False
            assert db_session.query(Movie).filter_by(id=movie_id).first() is not None

    def test_accepting_confirmation_deletes_the_movie(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            movie_id = movie.id

            with patch("click.confirm", return_value=True):
                deleted = delete_movie(movie_id)

            assert deleted is True
            assert db_session.query(Movie).filter_by(id=movie_id).first() is None
