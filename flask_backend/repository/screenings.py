from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import func

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
        .order_by(func.time(ScreeningDate.time))
        .all()
    )

    return screening_dates


def get_by_movie_id_and_cinema_id(movie_id: int, cinema_id: int) -> Optional[Screening]:
    screening = (
        db_session.query(Screening)
        .filter(Screening.movie_id == movie_id)
        .filter(Screening.cinema_id == cinema_id)
        .first()
    )
    return screening


def create(
    movie_id: int,
    description: str,
    cinema_id: int,
    screening_dates: List[ScreeningDate],
    image: Optional[str],
    image_width: Optional[int],
    image_height: Optional[int],
    is_draft: Optional[bool] = False,
    image_alt: Optional[bool] = None,
) -> Screening:
    screening = Screening(
        movie_id=movie_id,
        cinema_id=cinema_id,
        dates=screening_dates,
        image=image,
        image_alt=image_alt,
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
    for _date in screening.dates:
        db_session.delete(_date)

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
    image_alt: Optional[str] = None,
) -> None:
    screening.movie_id = movie_id
    screening.description = description
    screening.draft = is_draft
    if image_alt:
        screening.image_alt = image_alt
    if image:
        screening.image = image
        screening.image_width = image_width
        screening.image_height = image_height
    db_session.add(screening)
    db_session.commit()


def delete(
    screening: Screening,
) -> None:
    # delete all related dates to maintain integrity
    for _date in screening.dates:
        db_session.delete(_date)
    db_session.delete(screening)
    db_session.commit()
