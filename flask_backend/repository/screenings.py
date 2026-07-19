from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Alert, Cinema, Screening, ScreeningDate
from flask_backend.service.shared import get_weekend_dates


def get_screening_by_id(screening_id: int) -> Optional[Screening]:
    return db_session.query(Screening).filter(Screening.id == screening_id).first()


def get_days_screenings_by_cinema_id(cinema_id: int, day: date) -> List[Screening]:
    screening_dates = (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(Screening.cinema_id == cinema_id)
        .filter(func.date(ScreeningDate.date) == day)
        .order_by(func.time(ScreeningDate.time))
        .all()
    )

    return screening_dates


def get_month_screening_dates(
    cinema_slugs: Optional[List[str]] = None,
) -> List[ScreeningDate]:
    month = date.today().replace(day=1)
    if month.month in [4, 6, 9, 11]:
        last_day = month + timedelta(days=30)
    else:
        last_day = month + timedelta(days=31)
    screening_dates = (
        db_session.query(ScreeningDate)
        .join(Screening)
        .join(Cinema)
        .filter(func.date(ScreeningDate.date).between(month, last_day))
    )

    if cinema_slugs:
        screening_dates = screening_dates.filter(Cinema.slug.in_(cinema_slugs))

    screening_dates = (
        screening_dates.order_by(func.date(ScreeningDate.date))
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
    url_origin: Optional[str] = None,
    raw_title: Optional[str] = None,
    title_cleaning_rules: Optional[str] = None,
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
        url=url_origin,
        raw_title=raw_title,
        title_cleaning_rules=title_cleaning_rules,
        created_at=datetime.now(),
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening


def update_title_cleaning_info(
    screening: Screening, raw_title: str, matched_rule_names: List[str]
) -> Screening:
    """Refreshes raw_title to the latest scrape and unions matched_rule_names
    into the screening's existing title_cleaning_rules, never dropping a
    previously-detected annotation."""
    screening.raw_title = raw_title
    existing_rules = set((screening.title_cleaning_rules or "").split(",")) - {""}
    all_rules = existing_rules | set(matched_rule_names)
    screening.title_cleaning_rules = ",".join(sorted(all_rules)) or None
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening


def get_screenings_due_for_core_alert_evaluation() -> List[Screening]:
    """Non-draft screenings whose core alert rules (new movie, single
    screening, sessão comentada, mostra) haven't been evaluated yet."""
    return (
        db_session.query(Screening)
        .filter(Screening.core_alerts_evaluated_at.is_(None))
        .filter(Screening.draft == False)  # noqa: E712
        .all()
    )


def mark_core_alerts_evaluated(screening_id: int) -> None:
    screening = get_screening_by_id(screening_id)
    if screening is None:
        return
    screening.core_alerts_evaluated_at = datetime.now()
    db_session.add(screening)
    db_session.commit()


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
    # screening-scoped alerts (new_movie, single_screening, sessao_comentada,
    # mostra) don't make sense once their screening is gone
    db_session.query(Alert).filter(Alert.screening_id == screening.id).delete(
        synchronize_session=False
    )
    db_session.delete(screening)
    db_session.commit()


def get_weekend_screening_dates() -> Tuple[List[ScreeningDate], date, date, date]:
    current_date = date.today()
    friday_date, saturday_date, sunday_date = get_weekend_dates(current_date)
    return (
        db_session.query(ScreeningDate)
        .join(Screening)
        .filter(Screening.draft == False)  # noqa: E712
        .filter(func.date(ScreeningDate.date).between(friday_date, sunday_date))
        .order_by(func.date(ScreeningDate.date))
        .order_by(func.time(ScreeningDate.time))
        .all(),
        friday_date,
        saturday_date,
        sunday_date,
    )
