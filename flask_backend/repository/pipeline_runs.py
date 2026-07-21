from datetime import datetime, timedelta
from math import ceil
from typing import Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import PipelineRun

# A "running" run older than this is considered dead (its process was
# killed before it could write finished_at) rather than genuinely in
# progress. Display-only - never mutates the stored status.
INTERRUPTED_THRESHOLD = timedelta(hours=1)


def start(pipeline_name: str, source: Optional[str] = None) -> PipelineRun:
    run = PipelineRun(
        pipeline_name=pipeline_name,
        source=source,
        started_at=datetime.now(),
        status="running",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def set_source(run_id: int, source: str) -> None:
    db_session.query(PipelineRun).filter(PipelineRun.id == run_id).update(
        {"source": source}
    )
    db_session.commit()


def finish(
    run_id: int,
    status: str,
    summary: Optional[str] = None,
    error_message: Optional[str] = None,
) -> PipelineRun:
    run = db_session.query(PipelineRun).filter(PipelineRun.id == run_id).one()
    run.status = status
    run.finished_at = datetime.now()
    run.summary = summary
    run.error_message = error_message
    db_session.commit()
    db_session.refresh(run)
    return run


def get_by_id(run_id: int) -> Optional[PipelineRun]:
    return db_session.query(PipelineRun).filter(PipelineRun.id == run_id).first()


def get_latest_by_pipeline(
    pipeline_name: str, source: Optional[str] = None
) -> Optional[PipelineRun]:
    query = db_session.query(PipelineRun).filter(
        PipelineRun.pipeline_name == pipeline_name
    )
    if source is not None:
        query = query.filter(PipelineRun.source == source)
    return query.order_by(PipelineRun.started_at.desc()).first()


def get_paginated(
    pipeline_name: str,
    current_page: int,
    per_page: int,
    source: Optional[str] = None,
) -> Tuple[list[PipelineRun], int, int]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(PipelineRun).filter(
        PipelineRun.pipeline_name == pipeline_name
    )
    if source is not None:
        query = query.filter(PipelineRun.source == source)

    runs = (
        query.order_by(PipelineRun.started_at.desc())
        .limit(per_page)
        .offset(offset_value)
        .all()
    )

    count_query = db_session.query(func.count(PipelineRun.id)).filter(
        PipelineRun.pipeline_name == pipeline_name
    )
    if source is not None:
        count_query = count_query.filter(PipelineRun.source == source)
    total_count = count_query.scalar()
    total_pages = ceil(total_count / per_page) if total_count else 0

    return (runs, total_pages, total_count)


def is_interrupted(run: PipelineRun) -> bool:
    return run.status == "running" and (
        datetime.now() - run.started_at > INTERRUPTED_THRESHOLD
    )


def display_status(run: PipelineRun) -> str:
    """Status to show in the UI - "running" becomes "interrupted" once stale."""
    if is_interrupted(run):
        return "interrupted"
    return run.status
