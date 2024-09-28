from typing import List, Optional

from sqlalchemy import asc

from flask_backend.db import db_session
from flask_backend.models import Cinema


def get_all() -> List[Cinema]:
    cinemas = db_session.query(Cinema).order_by(asc(Cinema.name)).all()
    return cinemas


def get_by_id(cinema_id: int) -> Optional[Cinema]:
    return db_session.query(Cinema).filter(Cinema.id == cinema_id).first()


def get_by_slug(cinema_slug: str) -> Optional[Cinema]:
    return db_session.query(Cinema).filter(Cinema.slug == cinema_slug).first()
