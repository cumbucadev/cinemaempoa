from typing import List, Optional

from sqlalchemy import asc

from flask_backend.db import db_session
from flask_backend.models import Cinema


def get_all() -> List[Cinema]:
    cinemas = db_session.query(Cinema).order_by(asc(Cinema.name)).all()
    return cinemas


def get_cinemas_with_photo() -> List[Cinema]:
    """Return cinemas that have a photo set. Used by the resize-images
    backfill (flask_backend.service.image_resize_pipeline) to find
    candidates for reprocessing."""
    return (
        db_session.query(Cinema)
        .filter(Cinema.photo.isnot(None), Cinema.photo != "")
        .order_by(Cinema.id)
        .all()
    )


def get_by_id(cinema_id: int) -> Optional[Cinema]:
    return db_session.query(Cinema).filter(Cinema.id == cinema_id).first()


def get_by_slug(cinema_slug: str) -> Optional[Cinema]:
    return db_session.query(Cinema).filter(Cinema.slug == cinema_slug).first()


def update(
    cinema: Cinema,
    name: str,
    url: str,
    address: Optional[str] = None,
    opening_hours: Optional[str] = None,
    instagram_url: Optional[str] = None,
    map_embed_url: Optional[str] = None,
    photo: Optional[str] = None,
    photo_width: Optional[int] = None,
    photo_height: Optional[int] = None,
) -> Cinema:
    cinema.name = name
    cinema.url = url
    cinema.address = address
    cinema.opening_hours = opening_hours
    cinema.instagram_url = instagram_url
    cinema.map_embed_url = map_embed_url
    if photo:
        cinema.photo = photo
        cinema.photo_width = photo_width
        cinema.photo_height = photo_height
    db_session.add(cinema)
    db_session.commit()
    db_session.refresh(cinema)
    return cinema
