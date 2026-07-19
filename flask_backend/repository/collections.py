from flask_backend.db import db_session
from flask_backend.models import Collection


def get_or_create_by_tmdb_id(tmdb_id: int, name: str) -> Collection:
    collection = (
        db_session.query(Collection).filter(Collection.tmdb_id == tmdb_id).first()
    )
    if collection is None:
        collection = Collection(tmdb_id=tmdb_id, name=name)
        db_session.add(collection)
        db_session.commit()
        db_session.refresh(collection)
    return collection
