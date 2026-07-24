"""Computes the admin's two alert categories (Sessão única / Recorrente)
live from the current schedule (issue #258), replacing the old detection-
rule pipeline in service/alert_rules.py + service/alert_pipeline.py. Pure
functions, no DB writes.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from dateutil.relativedelta import relativedelta

from flask_backend.models import AlertAction, Screening

UNICA = "unica"
RECORRENTE = "recorrente"

# How far back to look when counting a screening's dates for
# classification, so a long-running screening doesn't misclassify as
# "unica" on its last scheduled day (only 1 future date left) - see the
# design doc's "Classification rule". Code constant, not user-configurable.
RECORRENTE_GRACE_PERIOD = relativedelta(months=6)


def classify(screening: Screening, today: Optional[date] = None) -> str:
    """Sessão única vs. recorrente: counts ScreeningDates within
    [today - RECORRENTE_GRACE_PERIOD, +inf), combining recent-past and
    future dates. Exactly 1 -> unica; more -> recorrente."""
    today = today or date.today()
    window_start = today - RECORRENTE_GRACE_PERIOD
    count = sum(
        1 for screening_date in screening.dates if screening_date.date >= window_start
    )
    return UNICA if count == 1 else RECORRENTE


def last_upcoming_date(
    screening: Screening, today: Optional[date] = None
) -> Optional[date]:
    """The screening's last ScreeningDate that is still upcoming (>= today),
    or None if it has none. Unaffected by the grace period."""
    today = today or date.today()
    upcoming = [
        screening_date.date
        for screening_date in screening.dates
        if screening_date.date >= today
    ]
    return max(upcoming) if upcoming else None


CATEGORY_EMOJIS = {UNICA: "⏳", RECORRENTE: "🔁"}


def build_drafted_text(screening: Screening, today: Optional[date] = None) -> str:
    """Copyable post text for a Screening row on the Pendentes tab - title,
    release year, director(s), and this screening's own next upcoming date
    at its own cinema (not the movie's next showing at any cinema, since a
    row is scoped to one screening/cinema)."""
    today = today or date.today()
    movie = screening.movie
    emoji = CATEGORY_EMOJIS[classify(screening, today)]

    title_line = f"{emoji} {movie.title}".strip()
    if movie.release_year:
        title_line += f" ({movie.release_year})"
    if movie.directors:
        names = ", ".join(director.name for director in movie.directors)
        title_line += f" de {names}"

    upcoming = sorted(
        (d for d in screening.dates if d.date >= today),
        key=lambda d: (d.date, d.time or ""),
    )
    if not upcoming:
        body = "Sem sessão futura agendada"
    else:
        next_date = upcoming[0]
        when = f"{next_date.date.strftime('%d/%m')} {next_date.time}"
        body = f"{when}\nNa {screening.cinema.name}"

    return f"{title_line}\n\n{body}"


@dataclass(frozen=True)
class PendingRow:
    screening: Screening
    category: str
    last_upcoming_date: date
    drafted_text: str


def get_pending_rows(
    screenings: List[Screening],
    latest_actions: Dict[int, AlertAction],
    today: Optional[date] = None,
) -> List[PendingRow]:
    """Builds and sorts the Pendentes rows from `screenings` (expected to
    already be filtered to non-draft, has-an-upcoming-date, e.g. via
    repository.screenings.get_screenings_with_upcoming_dates), excluding
    any screening whose most recent action's remind_at hasn't arrived yet.
    Sorted ascending by nearest upcoming ScreeningDate."""
    today = today or date.today()
    rows = []
    for screening in screenings:
        latest_action = latest_actions.get(screening.id)
        if latest_action is not None and (
            latest_action.remind_at is None or latest_action.remind_at > today
        ):
            continue
        rows.append(
            PendingRow(
                screening=screening,
                category=classify(screening, today),
                last_upcoming_date=last_upcoming_date(screening, today),
                drafted_text=build_drafted_text(screening, today),
            )
        )
    rows.sort(
        key=lambda row: min(d.date for d in row.screening.dates if d.date >= today)
    )
    return rows
