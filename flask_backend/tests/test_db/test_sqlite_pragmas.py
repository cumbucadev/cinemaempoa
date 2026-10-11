from types import SimpleNamespace

from sqlalchemy import create_engine, event, make_url, text

import flask_backend.db
from flask_backend.db import (
    SQLITE_BUSY_TIMEOUT_MS,
    _set_sqlite_pragmas,
    configure_sqlite_pragmas,
)


def _pragma(engine, name):
    with engine.connect() as conn:
        return conn.execute(text(f"PRAGMA {name}")).scalar()


def test_file_sqlite_engine_uses_wal_and_busy_timeout(tmp_path):
    # timeout=0 overrides the driver's own 5s default, so the pragma is observable
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.sqlite'}", connect_args={"timeout": 0}
    )
    configure_sqlite_pragmas(engine)

    assert _pragma(engine, "journal_mode") == "wal"
    assert _pragma(engine, "busy_timeout") == SQLITE_BUSY_TIMEOUT_MS == 5000
    engine.dispose()


def test_in_memory_sqlite_engine_is_left_untouched():
    engine = create_engine("sqlite:///:memory:")

    assert configure_sqlite_pragmas(engine) is False
    assert not event.contains(engine, "connect", _set_sqlite_pragmas)
    assert _pragma(engine, "journal_mode") == "memory"


def test_non_sqlite_engine_gets_no_listener(monkeypatch):
    # No non-SQLite DBAPI driver is installed, so stand in for the engine.
    listened = []
    monkeypatch.setattr(flask_backend.db.event, "listen", lambda *a: listened.append(a))
    engine = SimpleNamespace(url=make_url("postgresql://user:pwd@localhost/db"))

    assert configure_sqlite_pragmas(engine) is False
    assert listened == []
