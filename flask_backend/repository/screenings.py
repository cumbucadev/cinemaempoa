from datetime import date
from sqlalchemy import func
from typing import Optional, List, Tuple

from flask_backend.db import db_session
from flask_backend.models import Screening, ScreeningDate


def get_screening_by_id(screening_id: int) -> Optional[Screening]:
    return db_session.query(Screening).filter(Screening.id == screening_id).first()


def get_todays_screenings_by_cinema_id(cinema_id: int) -> Tuple[ScreeningDate, str]:
    today = date.today()

    screening_dates = (
        db_session.query(
            ScreeningDate,
            func.group_concat(ScreeningDate.time),
        )
        .join(Screening)
        .filter(Screening.cinema_id == cinema_id)
        .filter(func.date(ScreeningDate.date) == today)
        .group_by(ScreeningDate.date)
        .all()
    )

    return screening_dates


def create(
    movie_id: int,
    description: str,
    cinema_id: int,
    screening_dates: List[ScreeningDate],
    image: Optional[str],
) -> Screening:
    screening = Screening(
        movie_id=movie_id,
        cinema_id=cinema_id,
        dates=screening_dates,
        image=image,
        description=description,
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
    screening: Screening, movie_id: int, description: str, image: Optional[str]
) -> None:
    screening.movie_id = movie_id
    screening.description = description
    if image:
        screening.image = image
    db_session.add(screening)
    db_session.commit()
