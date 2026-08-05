"""Data access for GeminiUsageEvent rows - one row per model attempted by
gemini_models.call_with_fallback, used by flask_backend/service/gemini_quota.py
to decide whether a model is currently available."""

from datetime import datetime
from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import GeminiUsageEvent


def create(
    model_id: str,
    occurred_at: datetime,
    outcome: str,
    quota_metric: Optional[str] = None,
    unavailable_until: Optional[datetime] = None,
) -> GeminiUsageEvent:
    event = GeminiUsageEvent(
        model_id=model_id,
        occurred_at=occurred_at,
        outcome=outcome,
        quota_metric=quota_metric,
        unavailable_until=unavailable_until,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def count_since(model_id: str, since: datetime) -> int:
    return (
        db_session.query(GeminiUsageEvent)
        .filter(
            GeminiUsageEvent.model_id == model_id,
            GeminiUsageEvent.occurred_at >= since,
        )
        .count()
    )


def most_recent(model_id: str) -> Optional[GeminiUsageEvent]:
    return (
        db_session.query(GeminiUsageEvent)
        .filter(GeminiUsageEvent.model_id == model_id)
        .order_by(GeminiUsageEvent.id.desc())
        .first()
    )
