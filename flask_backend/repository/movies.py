from typing import List, Optional
from sqlalchemy.orm import aliased

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening


def create(title: str) -> Movie:
    movie = Movie(title=title)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def get_all(show_drafts: bool = False) -> List[Optional[Movie]]:
    return (
        db_session.query(Movie)
        .join(Movie.screenings)
        .filter(Screening.draft == show_drafts)
        .all()
    )


def get_by_title(title: str) -> Optional[Movie]:
    return db_session.query(Movie).filter(Movie.title == title).first()


def get_by_title_or_create(title: str) -> Movie:
    movie = get_by_title(title)
    if not movie:
        movie = create(title=title)
    return movie
