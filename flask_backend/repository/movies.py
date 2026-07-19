from datetime import datetime
from math import ceil
from typing import FrozenSet, List, Optional, Set, Tuple

from slugify import slugify
from sqlalchemy import and_, func, or_

from flask_backend.db import db_session
from flask_backend.models import (
    Alert,
    Movie,
    MovieMetadataFetchAttempt,
    PosterFetchAttempt,
    Screening,
    movie_directors,
    movie_genres,
)


def create(title: str, slug: Optional[str] = None) -> Movie:
    if slug is None:
        slug = slugify(title)
    movie = Movie(title=title, slug=slug, created_at=datetime.now())
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def get_all(include_drafts: bool = False) -> List[Optional[Movie]]:
    query = db_session.query(Movie).join(Screening).distinct()
    if include_drafts is False:
        query = query.filter(Screening.draft == False)  # noqa: E712
    query = query.order_by(Movie.slug)
    return query.all()


def get_all_paginated(
    movie: str, current_page: int, per_page: int, include_drafts: bool = False
) -> Tuple[List[Optional[Movie]], int]:
    offset_value = (current_page - 1) * per_page
    # includes the `distinct` clause both on the select and the count queries
    # to avoid mismatches on pagination
    query = db_session.query(Movie).join(Screening).distinct()

    if include_drafts is False:
        query = query.filter(Screening.draft == False)  # noqa: E712

    query = (
        query.order_by(Movie.slug)
        .filter(Movie.title.ilike(f"%{movie}%"))
        .limit(per_page)
        .offset(offset_value)
    )

    movies = query.all()

    count_query = (
        db_session.query(func.count(func.distinct(Movie.id)))
        .filter(Movie.title.ilike(f"%{movie}%"))
        .join(Screening)
    )

    if include_drafts is False:
        count_query = count_query.filter(Screening.draft == False)  # noqa: E712

    total_count = count_query.scalar()

    total_pages = ceil(total_count / per_page)

    return (movies, total_pages, total_count)


def get_paginated(
    current_page: int, per_page: int, include_drafts: bool = False
) -> List[Optional[Movie]]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(Screening).order_by(Screening.id.desc())

    if not include_drafts:
        query = query.filter(Screening.draft == False)  # noqa: E712

    query = query.limit(per_page).offset(offset_value)

    return query.all()


def get_by_id(movie_id: int) -> Optional[Movie]:
    return db_session.query(Movie).filter(Movie.id == movie_id).first()


def get_by_slug(slug: str) -> Optional[Movie]:
    return db_session.query(Movie).filter(Movie.slug == slug).first()


def get_by_title_or_create(title: str) -> Movie:
    slug = slugify(title)
    movie = get_by_slug(slug)
    if not movie:
        movie = create(title=title, slug=slug)
    return movie


def get_movies_with_similar_titles(title: str) -> List[Movie]:
    return (
        db_session.query(Movie).filter(Movie.title.ilike(f"%{title}%")).limit(3).all()
    )


def delete(movie: Movie) -> None:
    # delete all related screenings to maintain integrity
    for _scr in movie.screenings:
        db_session.query(PosterFetchAttempt).filter(
            PosterFetchAttempt.screening_id == _scr.id
        ).delete(synchronize_session=False)
        # delete all related dates
        for _dt in _scr.dates:
            db_session.delete(_dt)
        db_session.delete(_scr)
    db_session.query(MovieMetadataFetchAttempt).filter(
        MovieMetadataFetchAttempt.movie_id == movie.id
    ).delete(synchronize_session=False)
    # Alert.movie_id is non-nullable and is always set (even for
    # screening-scoped rules), so this also covers alerts tied to the
    # screenings deleted above.
    db_session.query(Alert).filter(Alert.movie_id == movie.id).delete(
        synchronize_session=False
    )
    db_session.delete(movie)
    db_session.commit()


def get_movies_due_for_metadata_alert_evaluation() -> List[Movie]:
    """Movies whose director/genre/collection alert rules haven't been
    evaluated yet: metadata_alerts_evaluated_at is NULL, and either the
    movie already has a director, or metadata fetching for it has exhausted
    every source in MOVIE_METADATA_SOURCES (so it will never get one)."""
    from flask_backend.repository.movie_metadata_fetch_attempts import get_next_source

    candidates = (
        db_session.query(Movie)
        .filter(Movie.metadata_alerts_evaluated_at.is_(None))
        .all()
    )
    return [
        movie
        for movie in candidates
        if movie.directors or get_next_source(movie.id) is None
    ]


def _earlier_than(before: datetime, exclude_movie_id: int):
    """Movie.created_at < before, with Movie.id as a tie-breaker for movies
    sharing the exact same created_at (e.g. rows backfilled with a single
    flat CURRENT_TIMESTAMP by a migration) - otherwise two movies tied on
    created_at would never see each other as "earlier"."""
    return or_(
        Movie.created_at < before,
        and_(Movie.created_at == before, Movie.id < exclude_movie_id),
    )


def get_earlier_movies_with_director(
    director_id: int, before: datetime, exclude_movie_id: int
) -> List[Movie]:
    return (
        db_session.query(Movie)
        .join(movie_directors, movie_directors.c.movie_id == Movie.id)
        .filter(movie_directors.c.director_id == director_id)
        .filter(_earlier_than(before, exclude_movie_id))
        .filter(Movie.id != exclude_movie_id)
        .all()
    )


def get_earlier_movies_with_collection(
    collection_id: int, before: datetime, exclude_movie_id: int
) -> List[Movie]:
    return (
        db_session.query(Movie)
        .filter(Movie.collection_id == collection_id)
        .filter(_earlier_than(before, exclude_movie_id))
        .filter(Movie.id != exclude_movie_id)
        .all()
    )


def get_earlier_genre_id_sets(
    before: datetime, exclude_movie_id: int
) -> Set[FrozenSet[int]]:
    """One frozenset of genre ids per movie created before `before` (or tied
    on created_at with a lower id than exclude_movie_id) that has at least
    one genre. Used to detect genre combinations not seen yet."""
    rows = (
        db_session.query(movie_genres.c.movie_id, movie_genres.c.genre_id)
        .join(Movie, Movie.id == movie_genres.c.movie_id)
        .filter(_earlier_than(before, exclude_movie_id))
        .all()
    )
    genre_ids_by_movie: dict[int, Set[int]] = {}
    for movie_id, genre_id in rows:
        genre_ids_by_movie.setdefault(movie_id, set()).add(genre_id)
    return {frozenset(genre_ids) for genre_ids in genre_ids_by_movie.values()}
