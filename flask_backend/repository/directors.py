from flask_backend.db import db_session
from flask_backend.models import Director


def get_or_create_by_tmdb_id(tmdb_id: int, name: str) -> Director:
    director = db_session.query(Director).filter(Director.tmdb_id == tmdb_id).first()
    if director is None:
        director = Director(tmdb_id=tmdb_id, name=name)
        db_session.add(director)
        db_session.commit()
        db_session.refresh(director)
    return director
