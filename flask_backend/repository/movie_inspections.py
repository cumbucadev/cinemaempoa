"""Data access for MovieInspection rows - the append-only audit log
behind the movie inspector agent and /admin/movies/inspections."""

from datetime import datetime
from math import ceil
from typing import List, Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspection


def create(
    movie_id: int,
    status: str,
    reasoning: str,
    checked_tmdb_id: Optional[int] = None,
    previous_snapshot: Optional[str] = None,
    new_snapshot: Optional[str] = None,
    pipeline_run_id: Optional[int] = None,
) -> MovieInspection:
    inspection = MovieInspection(
        movie_id=movie_id,
        status=status,
        reasoning=reasoning,
        checked_tmdb_id=checked_tmdb_id,
        previous_snapshot=previous_snapshot,
        new_snapshot=new_snapshot,
        pipeline_run_id=pipeline_run_id,
        created_at=datetime.now(),
    )
    db_session.add(inspection)
    db_session.commit()
    db_session.refresh(inspection)
    return inspection


def get_by_id(inspection_id: int) -> Optional[MovieInspection]:
    return (
        db_session.query(MovieInspection)
        .filter(MovieInspection.id == inspection_id)
        .first()
    )


def _get_latest_checked_tmdb_id(movie_id: int) -> Optional[int]:
    """Ignores `error` rows: a transient failure (Gemini rate limit, network
    blip) still records the id it was about to check, and counting it as
    "already checked" would retire the movie from the queue forever."""
    row = (
        db_session.query(MovieInspection.checked_tmdb_id)
        .filter(
            MovieInspection.movie_id == movie_id,
            MovieInspection.status != "error",
        )
        .order_by(MovieInspection.id.desc())
        .first()
    )
    return row[0] if row else None


def get_movies_needing_inspection() -> List[Movie]:
    """Movies linked to TMDB whose match hasn't been inspected yet, or has
    changed since the last inspection (e.g. a prior fix, or a manual
    re-match via /admin/movies/<id>)."""
    candidates = db_session.query(Movie).filter(Movie.tmdb_id.isnot(None)).all()
    return [
        movie
        for movie in candidates
        if _get_latest_checked_tmdb_id(movie.id) != movie.tmdb_id
    ]


def get_paginated(
    status: Optional[str], current_page: int, per_page: int
) -> Tuple[List[MovieInspection], int, int]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(MovieInspection)
    if status is not None:
        query = query.filter(MovieInspection.status == status)

    inspections = (
        query.order_by(MovieInspection.created_at.desc(), MovieInspection.id.desc())
        .limit(per_page)
        .offset(offset_value)
        .all()
    )

    count_query = db_session.query(func.count(MovieInspection.id))
    if status is not None:
        count_query = count_query.filter(MovieInspection.status == status)
    total_count = count_query.scalar()
    total_pages = ceil(total_count / per_page) if total_count else 0

    return (inspections, total_pages, total_count)
