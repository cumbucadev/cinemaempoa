from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import Movie


def create(title: str) -> Movie:
    movie = Movie(title=title)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def get_by_title(title: str) -> Optional[Movie]:
    return db_session.query(Movie).filter(Movie.title == title).first()


def get_by_title_or_create(title: str) -> Movie:
    movie = get_by_title(title)
    if not movie:
        movie = create(title=title)
    return movie
