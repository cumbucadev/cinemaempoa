"""Data access for MovieInspectionRequest rows - the per-inspection state
behind the MCP tools in flask_backend/mcp_server.py."""

from datetime import datetime
from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspectionRequest


def create_for_movie(
    movie: Movie, pipeline_run_id: Optional[int] = None
) -> MovieInspectionRequest:
    """Opens a `dispatched` request that checks the movie's current tmdb_id."""
    request = MovieInspectionRequest(
        movie_id=movie.id,
        checked_tmdb_id=movie.tmdb_id,
        observed_tmdb_ids="[]",
        pipeline_run_id=pipeline_run_id,
        status="dispatched",
        created_at=datetime.now(),
    )
    db_session.add(request)
    db_session.commit()
    db_session.refresh(request)
    return request


def get_by_id(request_id: int) -> Optional[MovieInspectionRequest]:
    return (
        db_session.query(MovieInspectionRequest)
        .filter(MovieInspectionRequest.id == request_id)
        .first()
    )
