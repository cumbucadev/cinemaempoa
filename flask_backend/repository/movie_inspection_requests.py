"""Data access for MovieInspectionRequest rows - the per-inspection state
behind the MCP tools in flask_backend/mcp_server.py."""

import json
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select, update

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


def _merge_ids(current: list[int], new_ids: list[int]) -> list[int]:
    """`current` followed by the `new_ids` it lacks, in first-seen order."""
    return list(dict.fromkeys(current + new_ids))


def add_observed_tmdb_ids(request_id: int, tmdb_ids: Iterable[int]) -> list[int]:
    """Appends `tmdb_ids` to the request's observed ids, skipping those
    already there, and returns the resulting list. Commits.

    Atomic: the read-modify-write runs inside one write transaction, so two
    tool calls from the same agent turn running in parallel cannot drop each
    other's ids. A no-op UPDATE comes first to take SQLite's write lock
    before the read; a concurrent caller blocks on its own first UPDATE
    (busy_timeout) until this one commits, and then reads the merged list.
    """
    new_ids = list(tmdb_ids)
    by_id = MovieInspectionRequest.id == request_id
    # Close whatever transaction the session has open, so the lock below
    # starts a fresh one whose read sees the latest committed list.
    db_session.commit()
    db_session.execute(
        update(MovieInspectionRequest)
        .where(by_id)
        .values(observed_tmdb_ids=MovieInspectionRequest.observed_tmdb_ids)
    )
    current = db_session.execute(
        select(MovieInspectionRequest.observed_tmdb_ids).where(by_id)
    ).scalar_one()
    merged = _merge_ids(json.loads(current), new_ids)
    db_session.execute(
        update(MovieInspectionRequest)
        .where(by_id)
        .values(observed_tmdb_ids=json.dumps(merged))
    )
    db_session.commit()
    return merged
