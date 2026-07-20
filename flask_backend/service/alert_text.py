"""Builds the standardized "Texto sugerido" shown on /admin/alerts.

Regenerated live from the current schedule every time the alerts page
loads (see flask_backend/routes/admin/alerts.py), so the copyable text
always reflects the movie's true next showing rather than whatever was
true when the pipeline first drafted it (flask_backend/service/alert_rules.py).
"""

from typing import List

from flask_backend.db import db_session
from flask_backend.models import Alert
from flask_backend.repository.screenings import get_next_screening_date_for_movie

# Mirrors the emoji already embedded in each rule's f-string in
# alert_rules.py - kept here since drafted_text is now standardized and no
# longer holds the emoji itself.
RULE_EMOJIS = {
    "new_movie": "🎬",
    "single_screening": "⏳",
    "sessao_comentada": "💬",
    "mostra": "🎪",
    "director_debut": "🌟",
    "returning_director": "🔁",
    "new_genre_combination": "🎭",
    "sequel_or_franchise": "🎞️",
}

NO_UPCOMING_SCREENING_TEXT = "Sem sessão futura agendada"


def build_drafted_text(alert: Alert) -> str:
    movie = alert.movie
    emoji = RULE_EMOJIS.get(alert.rule_name, "")

    title_line = f"{emoji} {movie.title}".strip()
    if movie.release_year:
        title_line += f" ({movie.release_year})"
    if movie.directors:
        names = ", ".join(director.name for director in movie.directors)
        title_line += f" de {names}"

    next_date = get_next_screening_date_for_movie(movie.id)
    if next_date is None:
        body = NO_UPCOMING_SCREENING_TEXT
    else:
        when = f"{next_date.date.strftime('%d/%m')} {next_date.time}"
        body = f"{when}\nNa {next_date.screening.cinema.name}"

    return f"{title_line}\n\n{body}"


def refresh_pending(alerts: List[Alert]) -> None:
    """Regenerates and persists drafted_text for every pending alert in
    `alerts`. Posted/dismissed alerts are left untouched, as a historical
    record of the text that was actually used."""
    changed = False
    for alert in alerts:
        if alert.status != "pending":
            continue
        new_text = build_drafted_text(alert)
        if alert.drafted_text != new_text:
            alert.drafted_text = new_text
            changed = True
    if changed:
        db_session.commit()
