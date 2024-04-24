from typing import List, Optional

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening


def create(title: str) -> Movie:
    movie = Movie(title=title)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def get_all(include_drafts: bool = False) -> List[Optional[Movie]]:
    query = db_session.query(Movie).join(Screening)
    if include_drafts is False:
        query = query.filter(Screening.draft is False)
    return query.all()


def get_by_title(title: str) -> Optional[Movie]:
    return db_session.query(Movie).filter(Movie.title == title).first()


def get_by_title_or_create(title: str) -> Movie:
    movie = get_by_title(title)
    if not movie:
        movie = create(title=title)
    return movie


def get_movies_with_similar_titles(title: str) -> List[Movie]:
    return db_session.query(Movie).filter(Movie.title.ilike(f"%{title}%")).limit(3).all()
