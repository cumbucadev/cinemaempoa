from datetime import datetime
from typing import List, Optional, Set

from flask_backend.db import db_session
from flask_backend.models import (
    MOVIE_METADATA_SOURCES,
    Movie,
    MovieMetadataFetchAttempt,
)


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


def get_attempted_sources(movie_id: int) -> Set[str]:
    """Return the set of source names already attempted for a given movie."""
    rows = (
        db_session.query(MovieMetadataFetchAttempt.source)
        .filter(MovieMetadataFetchAttempt.movie_id == movie_id)
        .all()
    )
    return {row[0] for row in rows}


def get_next_source(movie_id: int) -> Optional[str]:
    """Return the next source to try for a movie, or None if all were tried."""
    attempted = get_attempted_sources(movie_id)
    for source in MOVIE_METADATA_SOURCES:
        if source not in attempted:
            return source
    return None


def get_movies_without_metadata() -> List[Movie]:
    """Return movies that have no director set."""
    return db_session.query(Movie).filter(~Movie.directors.any()).all()


def get_movies_needing_manual_review() -> List[Movie]:
    """Return movies that have no director and have exhausted all metadata sources.

    A movie needs manual review when:
    - It has no director
    - It has at least one attempt for every source in MOVIE_METADATA_SOURCES
    - None of them resulted in 'success'
    """
    movies_without_metadata = get_movies_without_metadata()
    result = []
    for movie in movies_without_metadata:
        attempted = get_attempted_sources(movie.id)
        if all(source in attempted for source in MOVIE_METADATA_SOURCES):
            result.append(movie)
    return result


def get_by_pipeline_run_id(pipeline_run_id: int) -> List[MovieMetadataFetchAttempt]:
    return (
        db_session.query(MovieMetadataFetchAttempt)
        .filter(MovieMetadataFetchAttempt.pipeline_run_id == pipeline_run_id)
        .order_by(MovieMetadataFetchAttempt.id)
        .all()
    )
