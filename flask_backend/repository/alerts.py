from datetime import datetime
from math import ceil
from typing import List, Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Alert


def create(
    rule_name: str,
    movie_id: int,
    screening_id: Optional[int],
    dedup_key: str,
    drafted_text: str,
    context: Optional[str] = None,
    commit: bool = True,
    pipeline_run_id: Optional[int] = None,
) -> Alert:
    alert = Alert(
        rule_name=rule_name,
        movie_id=movie_id,
        screening_id=screening_id,
        dedup_key=dedup_key,
        drafted_text=drafted_text,
        context=context,
        status="pending",
        created_at=datetime.now(),
        pipeline_run_id=pipeline_run_id,
    )
    db_session.add(alert)
    if commit:
        db_session.commit()
        db_session.refresh(alert)
    return alert


def exists_by_dedup_key(dedup_key: str) -> bool:
    return (
        db_session.query(Alert.id).filter(Alert.dedup_key == dedup_key).first()
        is not None
    )


def get_by_id(alert_id: int) -> Optional[Alert]:
    return db_session.query(Alert).filter(Alert.id == alert_id).first()


def get_all_paginated(
    current_page: int, per_page: int, status: Optional[str] = "pending"
) -> Tuple[list[Alert], int, int]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(Alert)
    if status is not None:
        query = query.filter(Alert.status == status)

    query = query.order_by(Alert.created_at.desc()).limit(per_page).offset(offset_value)
    alerts = query.all()

    count_query = db_session.query(func.count(Alert.id))
    if status is not None:
        count_query = count_query.filter(Alert.status == status)

    total_count = count_query.scalar()
    total_pages = ceil(total_count / per_page) if total_count else 0

    return (alerts, total_pages, total_count)


def _resolve(alert_id: int, status: str, user_id: Optional[int]) -> Optional[Alert]:
    alert = get_by_id(alert_id)
    if alert is None:
        return None
    alert.status = status
    alert.resolved_at = datetime.now()
    alert.resolved_by_user_id = user_id
    db_session.commit()
    db_session.refresh(alert)
    return alert


def mark_posted(alert_id: int, user_id: Optional[int] = None) -> Optional[Alert]:
    return _resolve(alert_id, "posted", user_id)


def dismiss(alert_id: int, user_id: Optional[int] = None) -> Optional[Alert]:
    return _resolve(alert_id, "dismissed", user_id)


def get_pending_count() -> int:
    return (
        db_session.query(func.count(Alert.id))
        .filter(Alert.status == "pending")
        .scalar()
    )


def delete_for_movie(movie_id: int) -> None:
    """Deletes every alert for `movie_id`. Alert.movie_id is non-nullable and
    always set (even for screening-scoped rules), so this also covers alerts
    tied to that movie's screenings."""
    db_session.query(Alert).filter(Alert.movie_id == movie_id).delete(
        synchronize_session=False
    )


def delete_for_screening(screening_id: int) -> None:
    """Deletes screening-scoped alerts (new_movie, single_screening,
    sessao_comentada, mostra) - they don't make sense once their screening
    is gone."""
    db_session.query(Alert).filter(Alert.screening_id == screening_id).delete(
        synchronize_session=False
    )


def repoint_to_movie(old_movie_id: int, new_movie_id: int) -> None:
    """Repoints alerts referencing `old_movie_id` to `new_movie_id`, e.g.
    when merging duplicate movies."""
    db_session.query(Alert).filter(Alert.movie_id == old_movie_id).update(
        {"movie_id": new_movie_id}
    )


def repoint_to_screening(old_screening_id: int, new_screening_id: int) -> None:
    """Repoints alerts referencing `old_screening_id` to `new_screening_id` -
    dedup_key strings may go slightly stale (e.g. still mention the old
    screening_id), which is harmless since dedup_key is only consulted at
    alert-creation time, never re-derived."""
    db_session.query(Alert).filter(Alert.screening_id == old_screening_id).update(
        {"screening_id": new_screening_id}
    )


def get_by_pipeline_run_id(pipeline_run_id: int) -> List[Alert]:
    return (
        db_session.query(Alert)
        .filter(Alert.pipeline_run_id == pipeline_run_id)
        .order_by(Alert.id)
        .all()
    )
