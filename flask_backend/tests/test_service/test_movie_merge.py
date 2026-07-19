from datetime import date, datetime

from flask_backend.db import db_session
from flask_backend.models import (
    Alert,
    Genre,
    Movie,
    MovieMetadataFetchAttempt,
    PosterFetchAttempt,
    Screening,
    ScreeningDate,
)
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.movie_merge import (
    merge_movies,
    pick_survivor,
    reset_fetch_attempts,
)


def _create_movie(title, slug, **extra):
    movie = Movie(title=title, slug=slug, **extra)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, cinema_slug, dates=None, **extra):
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
    screening = Screening(movie_id=movie.id, cinema_id=cinema.id, **defaults)
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


class TestPickSurvivor:
    def test_more_complete_movie_wins_over_older_id(self, client, app, setup_cinemas):
        with client.application.app_context():
            older = _create_movie("Filme", "filme")
            newer = _create_movie("Cinema | Filme", "cinema-filme")
            newer.original_title = "Original Title"
            db_session.commit()

            survivor = pick_survivor([older, newer])
            assert survivor.id == newer.id

    def test_tie_breaks_to_lowest_id(self, client, app, setup_cinemas):
        with client.application.app_context():
            first = _create_movie("A", "a")
            second = _create_movie("Cinema | A", "cinema-a")

            survivor = pick_survivor([second, first])
            assert survivor.id == first.id


class TestMergeMovies:
    def test_backfills_empty_scalar_fields_without_overwriting(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie(
                "Cinema | Filme",
                "cinema-filme",
                original_title="Original",
                release_year=2020,
                original_language="en",
            )

            merge_movies(survivor, [duplicate])
            db_session.commit()

            merged = db_session.query(Movie).filter_by(id=survivor.id).one()
            assert merged.original_title == "Original"
            assert merged.release_year == 2020
            assert merged.original_language == "en"

    def test_does_not_overwrite_existing_scalar_fields(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme", original_title="Keep Me")
            duplicate = _create_movie(
                "Cinema | Filme", "cinema-filme", original_title="Other"
            )

            merge_movies(survivor, [duplicate])
            db_session.commit()

            merged = db_session.query(Movie).filter_by(id=survivor.id).one()
            assert merged.original_title == "Keep Me"

    def test_unions_genres_without_duplicates(self, client, app, setup_cinemas):
        with client.application.app_context():
            shared_genre = Genre(tmdb_id=1, name="Drama")
            only_duplicate_genre = Genre(tmdb_id=2, name="Comédia")
            db_session.add_all([shared_genre, only_duplicate_genre])
            db_session.commit()

            survivor = _create_movie("Filme", "filme")
            survivor.genres.append(shared_genre)
            db_session.commit()

            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            duplicate.genres.extend([shared_genre, only_duplicate_genre])
            db_session.commit()

            merge_movies(survivor, [duplicate])
            db_session.commit()

            merged = db_session.query(Movie).filter_by(id=survivor.id).one()
            assert {genre.id for genre in merged.genres} == {
                shared_genre.id,
                only_duplicate_genre.id,
            }

    def test_reassigns_screening_at_cinema_survivor_lacks(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            screening = _create_screening(duplicate, "capitolio")
            screening_id = screening.id

            merge_movies(survivor, [duplicate])
            db_session.commit()

            moved = db_session.query(Screening).filter_by(id=screening_id).one()
            assert moved.movie_id == survivor.id

    def test_merges_dates_and_backfills_image_for_shared_cinema(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            survivor_screening = _create_screening(
                survivor, "capitolio", dates=[(date(2026, 1, 1), "20:00")]
            )
            duplicate_screening = _create_screening(
                duplicate,
                "capitolio",
                dates=[(date(2026, 1, 2), "20:00")],
                image="poster.jpg",
            )
            duplicate_screening_id = duplicate_screening.id

            merge_movies(survivor, [duplicate])
            db_session.commit()

            merged_screening = (
                db_session.query(Screening).filter_by(id=survivor_screening.id).one()
            )
            dates = {(d.date, d.time) for d in merged_screening.dates}
            assert dates == {
                (date(2026, 1, 1), "20:00"),
                (date(2026, 1, 2), "20:00"),
            }
            assert merged_screening.image == "poster.jpg"
            assert (
                db_session.query(Screening).filter_by(id=duplicate_screening_id).first()
                is None
            )

    def test_does_not_duplicate_dates_already_present(self, client, app, setup_cinemas):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            _create_screening(
                survivor, "capitolio", dates=[(date(2026, 1, 1), "20:00")]
            )
            _create_screening(
                duplicate, "capitolio", dates=[(date(2026, 1, 1), "20:00")]
            )

            merge_movies(survivor, [duplicate])
            db_session.commit()

            all_dates = db_session.query(ScreeningDate).all()
            assert len(all_dates) == 1

    def test_deletes_duplicate_movie_and_its_metadata_fetch_attempts(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            db_session.add(
                MovieMetadataFetchAttempt(
                    movie_id=duplicate.id,
                    source="tmdb",
                    status="not_found",
                    attempted_at=datetime.now(),
                )
            )
            db_session.commit()
            duplicate_id = duplicate.id

            merge_movies(survivor, [duplicate])
            db_session.commit()

            assert db_session.query(Movie).filter_by(id=duplicate_id).first() is None
            assert (
                db_session.query(MovieMetadataFetchAttempt)
                .filter_by(movie_id=duplicate_id)
                .count()
                == 0
            )

    def test_repoints_movie_scoped_alert_to_survivor(self, client, app, setup_cinemas):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            db_session.add(
                Alert(
                    rule_name="director_debut",
                    movie_id=duplicate.id,
                    screening_id=None,
                    dedup_key=f"director_debut:{duplicate.id}",
                    drafted_text="texto",
                    status="pending",
                    created_at=datetime.now(),
                )
            )
            db_session.commit()

            merge_movies(survivor, [duplicate])
            db_session.commit()

            alert = (
                db_session.query(Alert)
                .filter_by(dedup_key=f"director_debut:{duplicate.id}")
                .one()
            )
            assert alert.movie_id == survivor.id

    def test_repoints_screening_scoped_alert_on_fold_in(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            survivor_screening = _create_screening(survivor, "capitolio")
            duplicate_screening = _create_screening(duplicate, "capitolio")
            db_session.add(
                Alert(
                    rule_name="single_screening",
                    movie_id=duplicate.id,
                    screening_id=duplicate_screening.id,
                    dedup_key=f"single_screening:{duplicate_screening.id}",
                    drafted_text="texto",
                    status="pending",
                    created_at=datetime.now(),
                )
            )
            db_session.commit()

            merge_movies(survivor, [duplicate])
            db_session.commit()

            alert = (
                db_session.query(Alert)
                .filter_by(dedup_key=f"single_screening:{duplicate_screening.id}")
                .one()
            )
            assert alert.screening_id == survivor_screening.id

    def test_survivor_created_at_becomes_min_of_both(self, client, app, setup_cinemas):
        with client.application.app_context():
            older = datetime(2020, 1, 1)
            newer = datetime(2025, 1, 1)
            survivor = _create_movie("Filme", "filme", created_at=newer)
            duplicate = _create_movie(
                "Cinema | Filme", "cinema-filme", created_at=older
            )

            merge_movies(survivor, [duplicate])
            db_session.commit()

            merged = db_session.query(Movie).filter_by(id=survivor.id).one()
            assert merged.created_at == older

    def test_deletes_poster_fetch_attempts_for_discarded_screening(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            _create_screening(survivor, "capitolio")
            duplicate_screening = _create_screening(duplicate, "capitolio")
            db_session.add(
                PosterFetchAttempt(
                    screening_id=duplicate_screening.id,
                    source="tmdb",
                    status="not_found",
                    attempted_at=datetime.now(),
                )
            )
            db_session.commit()
            duplicate_screening_id = duplicate_screening.id

            merge_movies(survivor, [duplicate])
            db_session.commit()

            assert (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=duplicate_screening_id)
                .count()
                == 0
            )


class TestResetFetchAttempts:
    def test_clears_metadata_and_poster_attempts(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(movie, "capitolio")
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

            reset_fetch_attempts(movie)
            db_session.commit()

            assert (
                db_session.query(MovieMetadataFetchAttempt)
                .filter_by(movie_id=movie.id)
                .count()
                == 0
            )
            assert (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening.id)
                .count()
                == 0
            )
