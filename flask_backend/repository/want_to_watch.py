from typing import Set

from flask_backend.db import db_session
from flask_backend.models import WantToWatch


def toggle(movie_id: int, visitor_id: str) -> bool:
    """Inserts or deletes the (movie_id, visitor_id) mark. Returns the new
    state: True if now marked, False if now unmarked."""
    existing = (
        db_session.query(WantToWatch)
        .filter(WantToWatch.movie_id == movie_id)
        .filter(WantToWatch.visitor_id == visitor_id)
        .first()
    )
    if existing:
        db_session.delete(existing)
        db_session.commit()
        return False
    db_session.add(WantToWatch(movie_id=movie_id, visitor_id=visitor_id))
    db_session.commit()
    return True


def get_movie_ids_for_visitor(visitor_id: str) -> Set[int]:
    rows = (
        db_session.query(WantToWatch.movie_id)
        .filter(WantToWatch.visitor_id == visitor_id)
        .all()
    )
    return {row[0] for row in rows}
