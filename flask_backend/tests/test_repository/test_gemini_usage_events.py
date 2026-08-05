from datetime import datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import GeminiUsageEvent
from flask_backend.repository import gemini_usage_events


class TestCreate:
    def test_persists_all_fields(self, app):
        with app.app_context():
            now = datetime(2026, 8, 5, 12, 0, 0)

            event = gemini_usage_events.create(
                model_id="gemini-2.5-flash",
                occurred_at=now,
                outcome="rate_limited",
                quota_metric="requests_per_day",
                unavailable_until=now + timedelta(hours=6),
            )

            assert event.id is not None
            stored = db_session.query(GeminiUsageEvent).filter_by(id=event.id).one()
            assert stored.model_id == "gemini-2.5-flash"
            assert stored.occurred_at == now
            assert stored.outcome == "rate_limited"
            assert stored.quota_metric == "requests_per_day"
            assert stored.unavailable_until == now + timedelta(hours=6)

    def test_defaults_quota_metric_and_unavailable_until_to_none(self, app):
        with app.app_context():
            event = gemini_usage_events.create(
                model_id="gemini-2.5-flash",
                occurred_at=datetime(2026, 8, 5, 12, 0, 0),
                outcome="success",
            )

            assert event.quota_metric is None
            assert event.unavailable_until is None


class TestCountSince:
    def test_counts_only_matching_model_on_or_after_since(self, app):
        with app.app_context():
            base = datetime(2026, 8, 5, 12, 0, 0)
            gemini_usage_events.create(
                "model-a", base - timedelta(seconds=1), "success"
            )
            gemini_usage_events.create("model-a", base, "success")
            gemini_usage_events.create(
                "model-a", base + timedelta(seconds=1), "success"
            )
            gemini_usage_events.create(
                "model-b", base + timedelta(seconds=1), "success"
            )

            assert gemini_usage_events.count_since("model-a", base) == 2

    def test_returns_zero_when_no_events(self, app):
        with app.app_context():
            assert gemini_usage_events.count_since("model-a", datetime(2026, 8, 5)) == 0


class TestMostRecent:
    def test_returns_the_latest_event_for_the_model(self, app):
        with app.app_context():
            base = datetime(2026, 8, 5, 12, 0, 0)
            gemini_usage_events.create("model-a", base, "success")
            latest = gemini_usage_events.create(
                "model-a", base + timedelta(seconds=1), "rate_limited"
            )
            gemini_usage_events.create(
                "model-b", base + timedelta(seconds=2), "success"
            )

            result = gemini_usage_events.most_recent("model-a")

            assert result.id == latest.id

    def test_returns_none_when_no_events(self, app):
        with app.app_context():
            assert gemini_usage_events.most_recent("model-a") is None
