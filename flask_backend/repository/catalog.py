"""Read-only queries behind the catalog tools in
flask_backend/service/catalog_tools.py. Every one of them only sees published
screenings (`Screening.draft == False`) and takes its dates as arguments:
nothing here reads the clock.
"""

from datetime import date
from typing import Iterable, Optional

from sqlalchemy import Row, func, select
from sqlalchemy.orm import contains_eager, selectinload

from flask_backend.db import db_session
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate


def catalog_period() -> tuple[Optional[date], Optional[date]]:
    """The earliest and the latest published session date, or
    `(None, None)` when nothing is published."""
    since, until = (
        db_session.query(func.min(ScreeningDate.date), func.max(ScreeningDate.date))
        .join(Screening)
        .filter(Screening.draft.is_(False))
        .one()
    )
    return since, until


def session_dates(
    cinema_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[Row]:
    """One `(movie_id, cinema_id, screening_id, date, time)` row per
    published session date, optionally only those of one cinema and/or
    inside an inclusive date range."""
    query = (
        db_session.query(
            Screening.movie_id,
            Screening.cinema_id,
            ScreeningDate.screening_id,
            ScreeningDate.date,
            ScreeningDate.time,
        )
        .join(Screening)
        .filter(Screening.draft.is_(False))
    )
    if cinema_id is not None:
        query = query.filter(Screening.cinema_id == cinema_id)
    if date_from is not None:
        query = query.filter(ScreeningDate.date >= date_from)
    if date_to is not None:
        query = query.filter(ScreeningDate.date <= date_to)
    return query.all()


def _with_metadata(query):
    return query.options(
        selectinload(Movie.directors),
        selectinload(Movie.genres),
        selectinload(Movie.countries),
    )


def published_movies() -> list[Movie]:
    """The movies with at least one published screening, with their
    directors, genres and countries loaded."""
    published_ids = select(Screening.movie_id).where(Screening.draft.is_(False))
    return _with_metadata(
        db_session.query(Movie).filter(Movie.id.in_(published_ids))
    ).all()


def movies_by_ids(
    movie_ids: Iterable[int],
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> list[Movie]:
    """Those movies, with their directors, genres and countries loaded.
    A year bound leaves out the movies without a release year."""
    query = db_session.query(Movie).filter(Movie.id.in_(list(movie_ids)))
    if year_from is not None:
        query = query.filter(Movie.release_year >= year_from)
    if year_to is not None:
        query = query.filter(Movie.release_year <= year_to)
    return _with_metadata(query).all()


def published_screenings(movie_id: int) -> list[Screening]:
    """The movie's published screenings, ordered by cinema name, with their
    cinema and dates loaded."""
    return (
        db_session.query(Screening)
        .join(Cinema)
        .filter(Screening.movie_id == movie_id, Screening.draft.is_(False))
        .options(contains_eager(Screening.cinema), selectinload(Screening.dates))
        .order_by(Cinema.name, Screening.id)
        .all()
    )
