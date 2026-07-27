from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate
from flask_backend.repository import alert_actions
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


def get_screenings_in_date_range(start_date: date, end_date: date) -> List[Screening]:
    """Screenings (draft included) with at least one ScreeningDate between
    start_date and end_date, inclusive. Powers the mobile reels feed - the
    caller decides whether to keep drafts based on login state."""
    return (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(func.date(ScreeningDate.date).between(start_date, end_date))
        .distinct()
        .all()
    )


def get_screenings_for_movies_with_dates_in_range(
    movie_ids: List[int], start_date: date, end_date: date
) -> List[Screening]:
    """Screenings (draft included) for the given movie IDs with at least
    one ScreeningDate between start_date and end_date, inclusive. Powers
    the /favoritos feed - the caller decides whether to keep drafts based
    on login state, same as get_screenings_in_date_range."""
    if not movie_ids:
        return []
    return (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(Screening.movie_id.in_(movie_ids))
        .filter(func.date(ScreeningDate.date).between(start_date, end_date))
        .distinct()
        .all()
    )


def get_screening_dates_for_movies(
    movie_ids: List[int],
    start_date: date,
    end_date: date,
    include_drafts: bool = False,
) -> List[ScreeningDate]:
    """Every ScreeningDate between start_date and end_date (inclusive) for
    the given movie IDs, across all cinemas. Drafts are excluded unless
    include_drafts is True - callers must pass True only for logged-in
    requests, otherwise a movie with an unpublished screening at one cinema
    would leak that draft's dates via another cinema's published card."""
    if not movie_ids:
        return []
    query = (
        db_session.query(ScreeningDate)
        .join(Screening)
        .filter(Screening.movie_id.in_(movie_ids))
        .filter(func.date(ScreeningDate.date).between(start_date, end_date))
    )
    if not include_drafts:
        query = query.filter(Screening.draft == False)  # noqa: E712
    return query.all()


def get_by_movie_id_and_cinema_id(movie_id: int, cinema_id: int) -> Optional[Screening]:
    screening = (
        db_session.query(Screening)
        .filter(Screening.movie_id == movie_id)
        .filter(Screening.cinema_id == cinema_id)
        .first()
    )
    return screening


def get_next_screening_date_for_movie(
    movie_id: int, on_or_after: Optional[date] = None
) -> Optional[ScreeningDate]:
    """Earliest published (non-draft) ScreeningDate for a movie on or after
    `on_or_after` (defaults to today) - the movie's "next showing"."""
    on_or_after = on_or_after or date.today()
    return (
        db_session.query(ScreeningDate)
        .join(Screening)
        .filter(Screening.movie_id == movie_id)
        .filter(Screening.draft == False)  # noqa: E712
        .filter(func.date(ScreeningDate.date) >= on_or_after)
        .order_by(func.date(ScreeningDate.date))
        .order_by(func.time(ScreeningDate.time))
        .first()
    )


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
    pipeline_run_id: Optional[int] = None,
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
        pipeline_run_id=pipeline_run_id,
        created_at=datetime.now(),
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening


def merge_title_cleaning_rules(
    existing_rules: Optional[str], incoming_rules: Optional[str]
) -> Optional[str]:
    """Unions two comma-joined title_cleaning_rules strings, dropping empties."""
    existing = set((existing_rules or "").split(",")) - {""}
    incoming = set((incoming_rules or "").split(",")) - {""}
    return ",".join(sorted(existing | incoming)) or None


def update_title_cleaning_info(
    screening: Screening, raw_title: str, matched_rule_names: List[str]
) -> Screening:
    """Refreshes raw_title to the latest scrape and unions matched_rule_names
    into the screening's existing title_cleaning_rules, never dropping a
    previously-detected annotation."""
    screening.raw_title = raw_title
    screening.title_cleaning_rules = merge_title_cleaning_rules(
        screening.title_cleaning_rules, ",".join(matched_rule_names)
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening


def get_screenings_with_upcoming_dates(
    cinema_id: Optional[int] = None,
) -> List[Screening]:
    """Non-draft screenings with at least one ScreeningDate >= today -
    candidates for the live-computed Pendentes view (issue #258, see
    flask_backend/service/screening_alerts.py)."""
    today = date.today()
    query = (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(Screening.draft == False)  # noqa: E712
        .filter(func.date(ScreeningDate.date) >= today)
    )
    if cinema_id is not None:
        query = query.filter(Screening.cinema_id == cinema_id)
    return query.distinct().all()


def get_latest_screening_for_movie(
    movie_id: int, include_drafts: bool = False
) -> Optional[Screening]:
    """Most recently created Screening row for a movie, regardless of its
    dates. Used as a fallback source of poster/description/cinema data on
    /favoritos for a marked movie with no upcoming session. Excludes drafts
    by default so an anonymous visitor's stale-pick fallback never resolves
    to a newer unpublished draft while an older published screening exists -
    callers must pass include_drafts=True only for logged-in requests."""
    query = db_session.query(Screening).filter(Screening.movie_id == movie_id)
    if not include_drafts:
        query = query.filter(Screening.draft == False)  # noqa: E712
    return query.order_by(Screening.created_at.desc()).first()


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
    alert_actions.delete_for_screening(screening.id)
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


def get_by_pipeline_run_id(pipeline_run_id: int) -> List[Screening]:
    return (
        db_session.query(Screening)
        .filter(Screening.pipeline_run_id == pipeline_run_id)
        .order_by(Screening.id)
        .all()
    )


def get_past_movies_for_cinema(cinema_id: int) -> List[Tuple[Movie, bool]]:
    """Distinct movies with a Screening at this cinema and no upcoming
    ScreeningDate here, paired with whether the movie has ever screened
    at another cinema too (False) or only ever at this one (True)."""
    today = date.today()

    upcoming_movie_ids = {
        movie_id
        for (movie_id,) in (
            db_session.query(Screening.movie_id)
            .join(ScreeningDate)
            .filter(Screening.cinema_id == cinema_id)
            .filter(Screening.draft == False)  # noqa: E712
            .filter(func.date(ScreeningDate.date) >= today)
            .distinct()
        )
    }

    past_movie_rows = (
        db_session.query(Movie, func.max(ScreeningDate.date).label("last_shown"))
        .join(Screening, Screening.movie_id == Movie.id)
        .join(ScreeningDate, ScreeningDate.screening_id == Screening.id)
        .filter(Screening.cinema_id == cinema_id)
        .filter(Screening.draft == False)  # noqa: E712
        .group_by(Movie.id)
        .order_by(func.max(ScreeningDate.date).desc())
        .all()
    )

    exclusive_movie_ids = {
        movie_id
        for (movie_id,) in (
            db_session.query(Screening.movie_id)
            .filter(Screening.draft == False)  # noqa: E712
            .group_by(Screening.movie_id)
            .having(func.count(func.distinct(Screening.cinema_id)) == 1)
        )
    }

    return [
        (movie, movie.id in exclusive_movie_ids)
        for movie, _last_shown in past_movie_rows
        if movie.id not in upcoming_movie_ids
    ]
