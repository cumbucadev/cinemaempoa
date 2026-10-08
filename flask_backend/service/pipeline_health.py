"""Detects scraper/import breakage that import-json itself can't see.

A run that registers nothing new is usually fine (run-spiders re-imports the
same schedule every 12h), so the import's own counters aren't a breakage
signal. Instead, per cinema, this checks whether the latest import actually
scraped anything, whether it failed, whether imports stopped arriving, and
whether the DB has any upcoming screenings left. Read-only.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, List, Optional

from flask_backend.models import PipelineRun
from flask_backend.repository import pipeline_runs
from flask_backend.repository.screenings import count_dates_by_cinema_slug

IMPORT_PIPELINE = "import-json"

# How far back to look for import runs. Also bounds which cinemas are
# discovered when no slugs are given: a cinema with no import in this
# window is no longer considered scraped.
LOOKBACK = timedelta(days=90)
# cinebancarios and cine-cinco import weekly, so anything shorter would flag
# them between runs.
DEFAULT_STALE_AFTER = timedelta(days=8)
DEFAULT_HORIZON_DAYS = 7

NO_RECENT_IMPORT = "no_recent_import"
LAST_IMPORT_FAILED = "last_import_failed"
NO_FEATURES_SCRAPED = "no_features_scraped"
NO_UPCOMING_SCREENINGS = "no_upcoming_screenings"
# The latest import failed before the JSON was parsed (e.g. the scraper
# crashed and wrote an empty file), so it can't be attributed to a cinema.
UNATTRIBUTED_IMPORT_FAILED = "unattributed_import_failed"

_FAILED_STATUSES = ("error", "interrupted")


@dataclass
class CinemaHealth:
    slug: str
    last_import_at: Optional[datetime]
    last_import_status: Optional[str]
    # None when the latest run predates per-cinema feature counts.
    features_scraped: Optional[int]
    upcoming_dates: int
    issues: List[str] = field(default_factory=list)


@dataclass
class HealthReport:
    cinemas: List[CinemaHealth]
    issues: List[str] = field(default_factory=list)
    last_error_message: Optional[str] = None

    @property
    def healthy(self) -> bool:
        return not self.issues and not any(c.issues for c in self.cinemas)


def check_import_health(
    slugs: Optional[Iterable[str]] = None,
    now: Optional[datetime] = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> HealthReport:
    now = now or datetime.now()
    finished_runs = [
        run
        for run in pipeline_runs.get_started_since(IMPORT_PIPELINE, now - LOOKBACK)
        if pipeline_runs.display_status(run) != "running"
    ]

    latest_by_slug = _latest_run_by_slug(finished_runs)
    slugs = sorted(slugs) if slugs is not None else sorted(latest_by_slug)
    today = now.date()
    upcoming = count_dates_by_cinema_slug(today, today + timedelta(days=horizon_days))

    report = HealthReport(
        cinemas=[
            _check_cinema(
                slug, latest_by_slug.get(slug), upcoming.get(slug, 0), now, stale_after
            )
            for slug in slugs
        ]
    )

    if finished_runs and _is_unattributed_failure(finished_runs[0]):
        report.issues.append(UNATTRIBUTED_IMPORT_FAILED)
        report.last_error_message = finished_runs[0].error_message
    return report


def _latest_run_by_slug(runs_newest_first: List[PipelineRun]) -> dict:
    latest_by_slug: dict[str, PipelineRun] = {}
    for run in runs_newest_first:
        for slug in filter(None, (run.source or "").split(",")):
            latest_by_slug.setdefault(slug, run)
    return latest_by_slug


def _is_unattributed_failure(run: PipelineRun) -> bool:
    return run.source is None and pipeline_runs.display_status(run) in _FAILED_STATUSES


def _check_cinema(
    slug: str,
    run: Optional[PipelineRun],
    upcoming_dates: int,
    now: datetime,
    stale_after: timedelta,
) -> CinemaHealth:
    health = CinemaHealth(
        slug=slug,
        last_import_at=run.started_at if run else None,
        last_import_status=pipeline_runs.display_status(run) if run else None,
        features_scraped=_features_scraped(run, slug) if run else None,
        upcoming_dates=upcoming_dates,
    )

    if run is None or now - run.started_at > stale_after:
        health.issues.append(NO_RECENT_IMPORT)
    if health.last_import_status in _FAILED_STATUSES:
        health.issues.append(LAST_IMPORT_FAILED)
    if health.features_scraped == 0:
        health.issues.append(NO_FEATURES_SCRAPED)
    if upcoming_dates == 0:
        health.issues.append(NO_UPCOMING_SCREENINGS)
    return health


def _features_scraped(run: PipelineRun, slug: str) -> Optional[int]:
    if not run.summary:
        return None
    by_cinema = json.loads(run.summary).get("features_by_cinema") or {}
    return by_cinema.get(slug)
