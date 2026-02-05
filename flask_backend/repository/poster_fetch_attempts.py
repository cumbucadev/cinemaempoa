from datetime import datetime
from typing import List, Optional, Set

from flask_backend.db import db_session
from flask_backend.models import POSTER_SOURCES, PosterFetchAttempt, Screening


def create(
    screening_id: int,
    source: str,
    status: str,
    error_message: Optional[str] = None,
) -> PosterFetchAttempt:
    attempt = PosterFetchAttempt(
        screening_id=screening_id,
        source=source,
        status=status,
        attempted_at=datetime.now(),
        error_message=error_message,
    )
    db_session.add(attempt)
    db_session.commit()
    db_session.refresh(attempt)
    return attempt


def get_attempted_sources(screening_id: int) -> Set[str]:
    """Return the set of source names already attempted for a given screening."""
    rows = (
        db_session.query(PosterFetchAttempt.source)
        .filter(PosterFetchAttempt.screening_id == screening_id)
        .all()
    )
    return {row[0] for row in rows}


def get_next_source(screening_id: int) -> Optional[str]:
    """Return the next source to try for a screening, or None if all were tried."""
    attempted = get_attempted_sources(screening_id)
    for source in POSTER_SOURCES:
        if source not in attempted:
            return source
    return None


def get_screenings_without_poster() -> List[Screening]:
    """Return screenings that have no image set."""
    return (
        db_session.query(Screening)
        .filter(
            (Screening.image == None) | (Screening.image == "")  # noqa: E711
        )
        .all()
    )


def get_screenings_needing_manual_review() -> List[Screening]:
    """Return screenings that have no image and have exhausted all poster sources.

    A screening needs manual review when:
    - It has no image
    - It has at least one attempt for every source in POSTER_SOURCES
    - None of them resulted in 'success'
    """
    screenings_without_poster = get_screenings_without_poster()
    result = []
    for screening in screenings_without_poster:
        attempted = get_attempted_sources(screening.id)
        if all(source in attempted for source in POSTER_SOURCES):
            result.append(screening)
    return result
