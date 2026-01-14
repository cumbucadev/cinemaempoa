from math import ceil
from typing import List, Optional, Tuple

from slugify import slugify
from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening


def create(title: str, slug: Optional[str] = None) -> Movie:
    if slug is None:
        slug = slugify(title)
    movie = Movie(title=title, slug=slug)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def get_all(include_drafts: bool = False) -> List[Optional[Movie]]:
    query = db_session.query(Movie).join(Screening).distinct(Movie.id)
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
    query = db_session.query(Movie).join(Screening).distinct(Movie.id)

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
        # delete all related dates
        for _dt in _scr.dates:
            db_session.delete(_dt)
        db_session.delete(_scr)
    db_session.delete(movie)
    db_session.commit()
