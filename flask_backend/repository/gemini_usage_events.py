"""Data access for GeminiUsageEvent rows - one row per model attempted by
gemini_models.call_with_fallback, used by flask_backend/service/gemini_quota.py
to decide whether a model is currently available."""

from datetime import datetime
from typing import Optional

from sqlalchemy import or_

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
    """Counts attempts that may have used up the model's RPM/RPD quota. A
    server_unavailable attempt (a transient 5xx) is left out: Google turned
    it away for lack of capacity, so counting it would burn the 20 daily
    requests of a flash model on days Google is overloaded. If Google does
    count it after all, the worst case is a real 429, which the fallback
    already handles."""
    return (
        db_session.query(GeminiUsageEvent)
        .filter(
            GeminiUsageEvent.model_id == model_id,
            GeminiUsageEvent.occurred_at >= since,
            or_(
                GeminiUsageEvent.quota_metric.is_(None),
                GeminiUsageEvent.quota_metric != "server_unavailable",
            ),
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
