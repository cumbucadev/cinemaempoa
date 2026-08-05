import pytest

from flask_backend.db import db_session, init_db
from flask_backend.models import GeminiUsageEvent


@pytest.fixture(autouse=True)
def _gemini_quota_db():
    """tests/scrapers has no Flask app fixture, so this creates the schema
    directly (init_db() is plain Alembic code - it doesn't need a Flask
    app context) and clears gemini_usage_events between tests, mirroring
    flask_backend/tests/conftest.py's clean_db for this one table."""
    init_db()
    yield
    db_session.query(GeminiUsageEvent).delete()
    db_session.commit()
