import re
from datetime import datetime
from math import ceil
from typing import List, Optional, Tuple

from slugify import slugify
from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import (
    Movie,
    MovieMetadataFetchAttempt,
    PosterFetchAttempt,
    Screening,
)
from flask_backend.repository import alert_actions
from flask_backend.repository.screenings import (
    get_by_movie_id_and_cinema_id as get_screening_by_movie_id_and_cinema_id,
)


def create(
    title: str, slug: Optional[str] = None, pipeline_run_id: Optional[int] = None
) -> Movie:
    if slug is None:
        slug = slugify(title)
    movie = Movie(
        title=title,
        slug=slug,
        created_at=datetime.now(),
        pipeline_run_id=pipeline_run_id,
    )
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


def get_paginated_screenings_with_image(
    current_page: int, per_page: int, include_drafts: bool = False
) -> List[Screening]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(Screening).filter(Screening.image.isnot(None))
    query = query.order_by(Screening.id.desc())

    if not include_drafts:
        query = query.filter(Screening.draft == False)  # noqa: E712

    query = query.limit(per_page).offset(offset_value)

    return query.all()


def get_by_id(movie_id: int) -> Optional[Movie]:
    return db_session.query(Movie).filter(Movie.id == movie_id).first()


def get_by_slug(slug: str) -> Optional[Movie]:
    return db_session.query(Movie).filter(Movie.slug == slug).first()


def get_by_title_or_create(
    title: str, pipeline_run_id: Optional[int] = None
) -> Tuple[Movie, bool]:
    slug = slugify(title)
    movie = get_by_slug(slug)
    if movie:
        return movie, False
    movie = create(title=title, slug=slug, pipeline_run_id=pipeline_run_id)
    return movie, True


def create_distinct(title: str, pipeline_run_id: Optional[int] = None) -> Movie:
    base_slug = slugify(title)
    slug = base_slug
    suffix = 2
    while get_by_slug(slug) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return create(title=title, slug=slug, pipeline_run_id=pipeline_run_id)


def _get_disambiguated_siblings(base_slug: str) -> List[Movie]:
    """Movies whose slug is `base_slug` followed by a numeric suffix - the
    exact pattern create_distinct() produces (e.g. `noite-2`, `noite-3`).
    Deliberately not the fuzzy ilike match used by
    get_movies_with_similar_titles, which also matches unrelated titles
    that merely contain the same substring.

    Slug shape alone isn't enough: an unrelated numbered title (e.g. "Toy
    Story 2") can coincidentally slugify to `{base_slug}-2`. create_distinct()
    always copies the base movie's exact title onto every sibling it
    creates, so a genuine disambiguation's title slugifies back to
    base_slug - require that too."""
    candidates = db_session.query(Movie).filter(Movie.slug.like(f"{base_slug}-%")).all()
    pattern = re.compile(rf"^{re.escape(base_slug)}-\d+$")
    return [
        movie
        for movie in candidates
        if pattern.match(movie.slug) and slugify(movie.title) == base_slug
    ]


def resolve_for_screening(
    title: str, cinema_id: int, pipeline_run_id: Optional[int] = None
) -> Tuple[Movie, bool, bool, List[int]]:
    """Resolves a scraped title to a Movie for a given cinema, aware of
    disambiguated slug siblings created via create_distinct (e.g. a title
    collides with an existing `noite` slug, but a separate `noite-2` movie
    already exists for a different film).

    Returns (movie, created, ambiguous, candidate_movie_ids):
    - created: True only when no movie existed for this slug at all.
    - ambiguous: True when the title collides with a disambiguated family
      and cinema_id doesn't unambiguously pick one of them (zero or more
      than one candidate already has a screening at that cinema). The
      base-slug movie is still returned in that case - same fallback as
      before this function existed, just flagged.
    - candidate_movie_ids: the colliding family's movie ids, populated only
      when ambiguous is True.
    """
    slug = slugify(title)
    base_movie = get_by_slug(slug)
    if base_movie is None:
        movie = create(title=title, slug=slug, pipeline_run_id=pipeline_run_id)
        return movie, True, False, []

    siblings = _get_disambiguated_siblings(slug)
    if not siblings:
        return base_movie, False, False, []

    candidates = [base_movie, *siblings]
    matches = [
        candidate
        for candidate in candidates
        if get_screening_by_movie_id_and_cinema_id(candidate.id, cinema_id) is not None
    ]
    if len(matches) == 1:
        return matches[0], False, False, []

    return base_movie, False, True, [candidate.id for candidate in candidates]


def get_movies_with_similar_titles(
    title: str, exclude_movie_id: Optional[int] = None
) -> List[Movie]:
    query = db_session.query(Movie).filter(Movie.title.ilike(f"%{title}%"))
    if exclude_movie_id is not None:
        query = query.filter(Movie.id != exclude_movie_id)
    return query.limit(3).all()


def delete(movie: Movie) -> None:
    # delete all related screenings to maintain integrity
    for _scr in movie.screenings:
        db_session.query(PosterFetchAttempt).filter(
            PosterFetchAttempt.screening_id == _scr.id
        ).delete(synchronize_session=False)
        alert_actions.delete_for_screening(_scr.id)
        # delete all related dates
        for _dt in _scr.dates:
            db_session.delete(_dt)
        db_session.delete(_scr)
    db_session.query(MovieMetadataFetchAttempt).filter(
        MovieMetadataFetchAttempt.movie_id == movie.id
    ).delete(synchronize_session=False)
    db_session.delete(movie)
    db_session.commit()
