"""Computes the admin's two alert categories (Sessão única / Recorrente)
live from the current schedule (issue #258), replacing the old detection-
rule pipeline in service/alert_rules.py + service/alert_pipeline.py. Pure
functions, no DB writes.
"""

from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from flask_backend.models import Screening

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
    count = sum(1 for screening_date in screening.dates if screening_date.date >= window_start)
    return UNICA if count == 1 else RECORRENTE


def last_upcoming_date(screening: Screening, today: Optional[date] = None) -> Optional[date]:
    """The screening's last ScreeningDate that is still upcoming (>= today),
    or None if it has none. Unaffected by the grace period."""
    today = today or date.today()
    upcoming = [
        screening_date.date for screening_date in screening.dates if screening_date.date >= today
    ]
    return max(upcoming) if upcoming else None
