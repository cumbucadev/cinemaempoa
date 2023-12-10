from datetime import date
from sqlalchemy import func
from typing import Optional, List, Tuple

from flask_backend.db import db_session
from flask_backend.models import Screening, ScreeningDate


def get_screening_by_id(screening_id: int) -> Optional[Screening]:
    return db_session.query(Screening).filter(Screening.id == screening_id).first()


def get_days_screenings_by_cinema_id(
    cinema_id: int, day: date
) -> Tuple[ScreeningDate, str]:
    screening_dates = (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(Screening.cinema_id == cinema_id)
        .filter(func.date(ScreeningDate.date) == day)
        .all()
    )

    return screening_dates


def create(
    movie_id: int,
    description: str,
    cinema_id: int,
    screening_dates: List[ScreeningDate],
    image: Optional[str],
    image_width: Optional[int],
    image_height: Optional[int],
    is_draft: Optional[bool] = False,
) -> Screening:
    screening = Screening(
        movie_id=movie_id,
        cinema_id=cinema_id,
        dates=screening_dates,
        image=image,
        image_width=image_width,
        image_height=image_height,
        description=description,
        draft=is_draft,
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening


def update_screening_dates(
    screening: Screening, screening_dates: List[ScreeningDate]
) -> Screening:
    """Deletes all existing dates for a screening and substitute for the received dates."""
    for date in screening.dates:
        db_session.delete(date)

    screening.dates = screening_dates
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening


def update(
    screening: Screening,
    movie_id: int,
    description: str,
    image: Optional[str],
    image_width: Optional[int],
    image_height: Optional[int],
    is_draft: Optional[bool] = False,
) -> None:
    screening.movie_id = movie_id
    screening.description = description
    screening.draft = is_draft
    if image:
        screening.image = image
        screening.image_width = image_width
        screening.image_height = image_height
    db_session.add(screening)
    db_session.commit()
