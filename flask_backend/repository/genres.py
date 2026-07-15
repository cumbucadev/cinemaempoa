from flask_backend.db import db_session
from flask_backend.models import Genre


def get_or_create_by_tmdb_id(tmdb_id: int, name: str) -> Genre:
    genre = db_session.query(Genre).filter(Genre.tmdb_id == tmdb_id).first()
    if genre is None:
        genre = Genre(tmdb_id=tmdb_id, name=name)
        db_session.add(genre)
        db_session.commit()
        db_session.refresh(genre)
    return genre
