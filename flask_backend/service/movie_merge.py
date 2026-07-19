"""Merges a set of duplicate Movie rows into a single survivor.

Used by flask_backend.scripts.title_cleaning_backfill when cleaning titles
causes two or more previously-distinct Movie rows to collapse onto the same
slug. Reassigns/merges screenings, unions shared metadata (genres/directors/
countries), backfills empty scalar fields onto the survivor, and removes the
losing rows.

None of the functions here call db_session.commit() - callers are expected
to commit once after applying a whole batch of merges, so a failure partway
through can be rolled back instead of leaving a half-migrated database.
"""

from typing import List

from flask_backend.db import db_session
from flask_backend.models import (
    Alert,
    Movie,
    MovieMetadataFetchAttempt,
    PosterFetchAttempt,
    Screening,
)
from flask_backend.repository.screenings import (
    get_by_movie_id_and_cinema_id as get_screening_by_movie_id_and_cinema_id,
)

_SCALAR_FIELDS = ("original_title", "release_year", "original_language")
_SCREENING_BACKFILL_FIELDS = (
    "image",
    "image_alt",
    "image_width",
    "image_height",
    "description",
    "url",
    "raw_title",
)


def _completeness_score(movie: Movie) -> tuple:
    has_image = any(screening.image for screening in movie.screenings)
    return (
        bool(movie.directors),
        bool(movie.genres),
        bool(movie.countries),
        bool(movie.original_title),
        movie.release_year is not None,
        bool(movie.original_language),
        has_image,
    )


def pick_survivor(movies: List[Movie]) -> Movie:
    """Picks the movie with the most complete data as the merge survivor.

    Ties are broken by lowest id (oldest row)."""
    return max(movies, key=lambda movie: (_completeness_score(movie), -movie.id))


def _merge_scalar_fields(survivor: Movie, duplicate: Movie) -> None:
    for field in _SCALAR_FIELDS:
        if not getattr(survivor, field) and getattr(duplicate, field):
            setattr(survivor, field, getattr(duplicate, field))


def _merge_associations(survivor: Movie, duplicate: Movie) -> None:
    for genre in duplicate.genres:
        if genre not in survivor.genres:
            survivor.genres.append(genre)
    for director in duplicate.directors:
        if director not in survivor.directors:
            survivor.directors.append(director)
    for country in duplicate.countries:
        if country not in survivor.countries:
            survivor.countries.append(country)


def _merge_screening_dates(existing: Screening, losing: Screening) -> None:
    existing_pairs = {(date.date, date.time) for date in existing.dates}
    for date in list(losing.dates):
        pair = (date.date, date.time)
        if pair in existing_pairs:
            db_session.delete(date)
        else:
            # append (not a raw screening_id write) so SQLAlchemy also drops
            # `date` from `losing.dates` in memory - otherwise deleting
            # `losing` later tries to null out this NOT NULL FK column
            existing.dates.append(date)
            existing_pairs.add(pair)


def _backfill_screening_fields(existing: Screening, losing: Screening) -> None:
    for field in _SCREENING_BACKFILL_FIELDS:
        if not getattr(existing, field) and getattr(losing, field):
            setattr(existing, field, getattr(losing, field))
    existing_rules = set((existing.title_cleaning_rules or "").split(",")) - {""}
    losing_rules = set((losing.title_cleaning_rules or "").split(",")) - {""}
    union_rules = existing_rules | losing_rules
    existing.title_cleaning_rules = ",".join(sorted(union_rules)) or None


def _merge_screenings(survivor: Movie, duplicate: Movie) -> None:
    for screening in list(duplicate.screenings):
        existing = get_screening_by_movie_id_and_cinema_id(
            survivor.id, screening.cinema_id
        )
        if existing is None:
            # append (not a raw movie_id write) so SQLAlchemy also drops
            # `screening` from `duplicate.screenings` in memory - otherwise
            # deleting `duplicate` later tries to null out this NOT NULL FK
            survivor.screenings.append(screening)
            continue
        _merge_screening_dates(existing, screening)
        _backfill_screening_fields(existing, screening)
        db_session.query(PosterFetchAttempt).filter(
            PosterFetchAttempt.screening_id == screening.id
        ).delete(synchronize_session=False)
        # repoint alerts referencing the screening about to be deleted -
        # dedup_key strings may go slightly stale (e.g. still mention the
        # old screening_id), which is harmless since dedup_key is only
        # consulted at alert-creation time, never re-derived.
        db_session.query(Alert).filter(Alert.screening_id == screening.id).update(
            {"screening_id": existing.id}
        )
        db_session.delete(screening)


def merge_movies(survivor: Movie, duplicates: List[Movie]) -> None:
    """Merges `duplicates` into `survivor` and deletes the duplicate rows.

    `survivor` must not be included in `duplicates`."""
    for duplicate in duplicates:
        _merge_scalar_fields(survivor, duplicate)
        _merge_associations(survivor, duplicate)
        _merge_screenings(survivor, duplicate)
        survivor.created_at = min(survivor.created_at, duplicate.created_at)
        db_session.query(Alert).filter(Alert.movie_id == duplicate.id).update(
            {"movie_id": survivor.id}
        )
        db_session.query(MovieMetadataFetchAttempt).filter(
            MovieMetadataFetchAttempt.movie_id == duplicate.id
        ).delete(synchronize_session=False)
        db_session.delete(duplicate)


def reset_fetch_attempts(movie: Movie) -> None:
    """Clears exhausted metadata/poster fetch-attempt history for `movie`,
    so the enrichment pipelines get a fresh shot at its (now different)
    title on their next run."""
    db_session.query(MovieMetadataFetchAttempt).filter(
        MovieMetadataFetchAttempt.movie_id == movie.id
    ).delete(synchronize_session=False)
    screening_ids = [screening.id for screening in movie.screenings]
    if screening_ids:
        db_session.query(PosterFetchAttempt).filter(
            PosterFetchAttempt.screening_id.in_(screening_ids)
        ).delete(synchronize_session=False)
