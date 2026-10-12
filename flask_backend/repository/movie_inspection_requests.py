"""Data access for MovieInspectionRequest rows - the per-inspection state
behind the MCP tools in flask_backend/mcp_server.py."""

import json
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select, update

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspection, MovieInspectionRequest


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


def _take_write_lock(request_id: int) -> None:
    """Commits whatever transaction the session has open, then starts a
    fresh one with a no-op UPDATE on the request row, which takes SQLite's
    write lock. A concurrent caller blocks on its own no-op UPDATE
    (busy_timeout) until this transaction commits, so every read made after
    this sees the latest committed state and nobody else can change it
    before the commit."""
    db_session.commit()
    db_session.execute(
        update(MovieInspectionRequest)
        .where(MovieInspectionRequest.id == request_id)
        .values(observed_tmdb_ids=MovieInspectionRequest.observed_tmdb_ids)
    )


def add_observed_tmdb_ids(request_id: int, tmdb_ids: Iterable[int]) -> list[int]:
    """Appends `tmdb_ids` to the request's observed ids, skipping those
    already there, and returns the resulting list. Commits.

    Atomic: the read-modify-write runs under the request's write lock, so
    two tool calls from the same agent turn running in parallel cannot drop
    each other's ids.
    """
    new_ids = list(tmdb_ids)
    by_id = MovieInspectionRequest.id == request_id
    _take_write_lock(request_id)
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


def get_for_update(request_id: int) -> Optional[MovieInspectionRequest]:
    """The request, freshly read under its write lock (see
    `_take_write_lock`), or None if it does not exist. The lock holds until
    the caller commits or rolls back - `close_as_done` commits."""
    _take_write_lock(request_id)
    return db_session.get(MovieInspectionRequest, request_id, populate_existing=True)


def close_as_done(
    request: MovieInspectionRequest, inspection: MovieInspection
) -> MovieInspectionRequest:
    """Saves `inspection` and closes `request` as `done`, pointing at it, in
    one commit - together with whatever else the open transaction carries
    (a rematch of the movie)."""
    request.status = "done"
    request.finished_at = datetime.now()
    request.inspection = inspection
    db_session.add_all([inspection, request])
    db_session.commit()
    return request
