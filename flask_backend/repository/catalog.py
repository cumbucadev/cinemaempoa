"""Read-only queries behind the catalog tools in
flask_backend/service/catalog_tools.py. Every one of them only sees published
screenings (`Screening.draft == False`) and takes its dates as arguments:
nothing here reads the clock.
"""

from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate


def catalog_period() -> tuple[Optional[date], Optional[date]]:
    """The earliest and the latest published session date, or
    `(None, None)` when nothing is published."""
    since, until = (
        db_session.query(func.min(ScreeningDate.date), func.max(ScreeningDate.date))
        .join(Screening)
        .filter(Screening.draft == False)  # noqa: E712
        .one()
    )
    return since, until


def published_movies() -> list[Movie]:
    """The movies with at least one published screening, with their
    directors, genres and countries loaded."""
    published_ids = select(Screening.movie_id).where(Screening.draft.is_(False))
    return (
        db_session.query(Movie)
        .filter(Movie.id.in_(published_ids))
        .options(
            selectinload(Movie.directors),
            selectinload(Movie.genres),
            selectinload(Movie.countries),
        )
        .all()
    )
