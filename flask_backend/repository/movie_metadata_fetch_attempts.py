from datetime import datetime
from typing import List, Optional

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieMetadataFetchAttempt


def create(
    movie_id: int,
    source: str,
    status: str,
    error_message: Optional[str] = None,
    pipeline_run_id: Optional[int] = None,
) -> MovieMetadataFetchAttempt:
    attempt = MovieMetadataFetchAttempt(
        movie_id=movie_id,
        source=source,
        status=status,
        attempted_at=datetime.now(),
        error_message=error_message,
        pipeline_run_id=pipeline_run_id,
    )
    db_session.add(attempt)
    db_session.commit()
    db_session.refresh(attempt)
    return attempt


def has_attempt(movie_id: int) -> bool:
    """Return whether a TMDB fetch has already been attempted for this movie."""
    return (
        db_session.query(MovieMetadataFetchAttempt.id)
        .filter(MovieMetadataFetchAttempt.movie_id == movie_id)
        .first()
        is not None
    )


def get_latest_attempt(movie_id: int) -> Optional[MovieMetadataFetchAttempt]:
    """Return the most recent fetch attempt for a movie, if any."""
    return (
        db_session.query(MovieMetadataFetchAttempt)
        .filter(MovieMetadataFetchAttempt.movie_id == movie_id)
        .order_by(MovieMetadataFetchAttempt.id.desc())
        .first()
    )


def get_movies_needing_enrichment() -> List[Movie]:
    """Return movies that aren't linked to a TMDB entry and aren't excluded
    from automatic TMDB enrichment."""
    return (
        db_session.query(Movie)
        .filter(Movie.tmdb_id.is_(None), ~Movie.tmdb_excluded)
        .all()
    )


def get_movies_needing_manual_review() -> List[Movie]:
    """Return movies that need manual TMDB review: not linked, not excluded,
    and already attempted (so the pipeline won't retry them automatically)."""
    return [movie for movie in get_movies_needing_enrichment() if has_attempt(movie.id)]


def get_by_pipeline_run_id(pipeline_run_id: int) -> List[MovieMetadataFetchAttempt]:
    return (
        db_session.query(MovieMetadataFetchAttempt)
        .filter(MovieMetadataFetchAttempt.pipeline_run_id == pipeline_run_id)
        .order_by(MovieMetadataFetchAttempt.id)
        .all()
    )
