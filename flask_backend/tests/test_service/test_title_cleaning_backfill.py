from datetime import datetime

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieMetadataFetchAttempt, Screening
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.scripts.title_cleaning_backfill import title_cleaning_backfill


def _create_movie(title, slug, **extra):
    movie = Movie(title=title, slug=slug, **extra)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, cinema_slug):
    cinema = get_cinema_by_slug(cinema_slug)
    screening = Screening(movie_id=movie.id, cinema_id=cinema.id, description="desc")
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening


class TestTitleCleaningBackfillDryRun:
    def test_dry_run_makes_no_writes(self, client, app, setup_cinemas):
        with client.application.app_context():
            _create_movie("Cinema | Filme", "cinema-filme")
            before = [
                (m.id, m.title, m.slug)
                for m in db_session.query(Movie).order_by(Movie.id).all()
            ]

            title_cleaning_backfill(apply=False)

            after = [
                (m.id, m.title, m.slug)
                for m in db_session.query(Movie).order_by(Movie.id).all()
            ]
            assert before == after


class TestTitleCleaningBackfillRename:
    def test_renames_title_without_collision(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Cinema | Lobo e Cão", "cinema-lobo-e-cao")
            movie_id = movie.id

            title_cleaning_backfill(apply=True)

            movie = db_session.query(Movie).filter_by(id=movie_id).one()
            assert movie.title == "Lobo e Cão"
            assert movie.slug == "lobo-e-cao"


class TestTitleCleaningBackfillMerge:
    def test_merges_colliding_movies_keeping_most_complete_data(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            thin = _create_movie("Cinema | Lobo e Cão", "cinema-lobo-e-cao")
            rich = _create_movie(
                "Lobo e Cão", "lobo-e-cao", original_title="Wolf and Dog"
            )
            _create_screening(thin, "capitolio")
            _create_screening(rich, "sala-redencao")
            thin_id = thin.id
            rich_id = rich.id

            title_cleaning_backfill(apply=True)

            remaining = db_session.query(Movie).filter_by(slug="lobo-e-cao").all()
            assert len(remaining) == 1
            survivor = remaining[0]
            assert survivor.id == rich_id
            assert survivor.original_title == "Wolf and Dog"
            cinema_slugs = {screening.cinema.slug for screening in survivor.screenings}
            assert cinema_slugs == {"capitolio", "sala-redencao"}
            assert db_session.query(Movie).filter_by(id=thin_id).first() is None


class TestTitleCleaningBackfillFetchAttemptReset:
    def test_resets_fetch_attempts_for_renamed_movie(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Cinema | Filme", "cinema-filme")
            db_session.add(
                MovieMetadataFetchAttempt(
                    movie_id=movie.id,
                    source="tmdb",
                    status="not_found",
                    attempted_at=datetime.now(),
                )
            )
            db_session.commit()
            movie_id = movie.id

            title_cleaning_backfill(apply=True)

            assert (
                db_session.query(MovieMetadataFetchAttempt)
                .filter_by(movie_id=movie_id)
                .count()
                == 0
            )
