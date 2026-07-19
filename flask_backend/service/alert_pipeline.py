"""Pipeline that evaluates the alert rules (flask_backend/service/alert_rules.py)
against screenings/movies that haven't been checked yet, and records any
matches as pending Alert rows for review at /admin/alerts (issue #209).

Usage (via CLI):
    flask generate-alerts                # process everything due
    flask generate-alerts --limit 10     # process at most 10 subjects total
    flask generate-alerts --dry-run      # only report what would be created
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from flask_backend.db import db_session
from flask_backend.repository.alerts import create as create_alert, exists_by_dedup_key
from flask_backend.repository.movies import (
    get_movies_due_for_metadata_alert_evaluation,
)
from flask_backend.repository.screenings import (
    get_screenings_due_for_core_alert_evaluation,
)
from flask_backend.service.alert_rules import CORE_SCREENING_RULES, METADATA_MOVIE_RULES

logger = logging.getLogger(__name__)


@dataclass
class AlertPipelineResult:
    screenings_evaluated: int = 0
    movies_evaluated: int = 0
    alerts_created: int = 0
    alerts_by_rule: Dict[str, int] = field(default_factory=dict)


def _record_candidate(candidate, dry_run: bool, result: AlertPipelineResult) -> None:
    if exists_by_dedup_key(candidate.dedup_key):
        return
    if not dry_run:
        create_alert(
            rule_name=candidate.rule_name,
            movie_id=candidate.movie_id,
            screening_id=candidate.screening_id,
            dedup_key=candidate.dedup_key,
            drafted_text=candidate.drafted_text,
            context=json.dumps(candidate.context) if candidate.context else None,
        )
    result.alerts_created += 1
    result.alerts_by_rule[candidate.rule_name] = (
        result.alerts_by_rule.get(candidate.rule_name, 0) + 1
    )
    logger.info(
        "Alerta '%s' gerado para filme %d%s",
        candidate.rule_name,
        candidate.movie_id,
        f" (sessão {candidate.screening_id})" if candidate.screening_id else "",
    )


def run_pipeline(
    limit: Optional[int] = None, dry_run: bool = False
) -> AlertPipelineResult:
    result = AlertPipelineResult()

    screenings = get_screenings_due_for_core_alert_evaluation()
    if limit is not None:
        screenings = screenings[:limit]

    for screening in screenings:
        for rule_fn in CORE_SCREENING_RULES:
            candidate = rule_fn(screening)
            if candidate is not None:
                _record_candidate(candidate, dry_run, result)
        if not dry_run:
            screening.core_alerts_evaluated_at = datetime.now()
            db_session.add(screening)
        result.screenings_evaluated += 1

    if not dry_run and screenings:
        db_session.commit()

    remaining_limit = None
    if limit is not None:
        remaining_limit = limit - len(screenings)

    if remaining_limit is None or remaining_limit > 0:
        movies = get_movies_due_for_metadata_alert_evaluation()
        if remaining_limit is not None:
            movies = movies[:remaining_limit]

        for movie in movies:
            for rule_fn in METADATA_MOVIE_RULES:
                candidate = rule_fn(movie)
                if candidate is not None:
                    _record_candidate(candidate, dry_run, result)
            if not dry_run:
                movie.metadata_alerts_evaluated_at = datetime.now()
                db_session.add(movie)
            result.movies_evaluated += 1

        if not dry_run and movies:
            db_session.commit()

    return result
