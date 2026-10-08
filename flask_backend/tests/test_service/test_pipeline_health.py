import json
from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import (
    Cinema,
    Movie,
    PipelineRun,
    Screening,
    ScreeningDate,
)
from flask_backend.service.pipeline_health import (
    LAST_IMPORT_FAILED,
    NO_FEATURES_SCRAPED,
    NO_RECENT_IMPORT,
    NO_UPCOMING_SCREENINGS,
    check_import_health,
)

NOW = datetime(2026, 10, 8, 12, 0)


def _add_run(
    source,
    status="success",
    started_at=NOW - timedelta(hours=1),
    features_by_cinema=None,
    error_message=None,
):
    summary = None
    if features_by_cinema is not None:
        summary = json.dumps(
            {
                "movies_created": 0,
                "screenings_created": 0,
                "dates_registered": 0,
                "features_by_cinema": features_by_cinema,
            }
        )
    run = PipelineRun(
        pipeline_name="import-json",
        source=source,
        started_at=started_at,
        finished_at=None if status == "running" else started_at,
        status=status,
        summary=summary,
        error_message=error_message,
    )
    db_session.add(run)
    db_session.commit()
    return run


def _add_screening_date(slug, day):
    cinema = db_session.query(Cinema).filter_by(slug=slug).one()
    movie = Movie(title=f"Filme {slug} {day}", slug=f"filme-{slug}-{day}")
    db_session.add(movie)
    db_session.flush()
    screening = Screening(movie_id=movie.id, cinema_id=cinema.id, description="")
    db_session.add(screening)
    db_session.flush()
    db_session.add(ScreeningDate(screening_id=screening.id, date=day))
    db_session.commit()


def _cinema(report, slug):
    return next(c for c in report.cinemas if c.slug == slug)


class TestCheckImportHealth:
    def test_healthy_cinema_has_no_issues(self, app, setup_cinemas):
        with app.app_context():
            _add_run("capitolio", features_by_cinema={"capitolio": 5})
            _add_screening_date("capitolio", date(2026, 10, 10))

            report = check_import_health(now=NOW)

            assert report.healthy
            capitolio = _cinema(report, "capitolio")
            assert capitolio.features_scraped == 5
            assert capitolio.upcoming_dates == 1
            assert capitolio.last_import_status == "success"

    def test_one_empty_cinema_in_multi_cinema_run_is_flagged(self, app, setup_cinemas):
        with app.app_context():
            _add_run(
                "capitolio,sala-redencao",
                features_by_cinema={"capitolio": 5, "sala-redencao": 0},
            )
            _add_screening_date("capitolio", date(2026, 10, 10))

            report = check_import_health(now=NOW)

            assert not report.healthy
            assert _cinema(report, "capitolio").issues == []
            assert _cinema(report, "sala-redencao").issues == [
                NO_FEATURES_SCRAPED,
                NO_UPCOMING_SCREENINGS,
            ]

    def test_zero_new_records_with_scraped_features_is_healthy(
        self, app, setup_cinemas
    ):
        # The 12h re-import of an unchanged schedule: nothing new, but fine.
        with app.app_context():
            _add_run("capitolio", features_by_cinema={"capitolio": 3})
            _add_screening_date("capitolio", NOW.date())

            assert check_import_health(now=NOW).healthy

    def test_only_latest_run_per_cinema_counts(self, app, setup_cinemas):
        with app.app_context():
            _add_run(
                "capitolio",
                started_at=NOW - timedelta(hours=13),
                features_by_cinema={"capitolio": 0},
            )
            _add_run("capitolio", features_by_cinema={"capitolio": 4})
            _add_screening_date("capitolio", date(2026, 10, 9))

            assert check_import_health(now=NOW).healthy

    def test_stale_import_is_flagged(self, app, setup_cinemas):
        with app.app_context():
            _add_run(
                "cinebancarios",
                started_at=NOW - timedelta(days=9),
                features_by_cinema={"cinebancarios": 2},
            )
            _add_screening_date("cinebancarios", date(2026, 10, 9))

            report = check_import_health(now=NOW)

            assert _cinema(report, "cinebancarios").issues == [NO_RECENT_IMPORT]

    def test_failed_import_is_flagged(self, app, setup_cinemas):
        with app.app_context():
            _add_run("cine-cinco", status="error", error_message="boom")
            _add_screening_date("cine-cinco", date(2026, 10, 9))

            report = check_import_health(now=NOW)

            cine_cinco = _cinema(report, "cine-cinco")
            assert cine_cinco.issues == [LAST_IMPORT_FAILED]
            assert cine_cinco.features_scraped is None

    def test_screenings_outside_horizon_dont_count(self, app, setup_cinemas):
        with app.app_context():
            _add_run("capitolio", features_by_cinema={"capitolio": 1})
            _add_screening_date("capitolio", date(2026, 10, 1))
            _add_screening_date("capitolio", date(2026, 10, 30))

            report = check_import_health(now=NOW, horizon_days=7)

            assert _cinema(report, "capitolio").issues == [NO_UPCOMING_SCREENINGS]

    def test_run_without_per_cinema_counts_skips_features_check(
        self, app, setup_cinemas
    ):
        # Runs from before features_by_cinema was recorded.
        with app.app_context():
            _add_run("capitolio")
            _add_screening_date("capitolio", date(2026, 10, 9))

            report = check_import_health(now=NOW)

            assert report.healthy
            assert _cinema(report, "capitolio").features_scraped is None

    def test_explicit_slug_with_no_runs_is_flagged(self, app, setup_cinemas):
        with app.app_context():
            report = check_import_health(["paulo-amorim"], now=NOW)

            paulo_amorim = _cinema(report, "paulo-amorim")
            assert paulo_amorim.last_import_at is None
            assert paulo_amorim.issues == [NO_RECENT_IMPORT, NO_UPCOMING_SCREENINGS]

    def test_explicit_slugs_limit_which_cinemas_are_checked(self, app, setup_cinemas):
        with app.app_context():
            _add_run("capitolio", features_by_cinema={"capitolio": 0})
            _add_run("cine-cinco", features_by_cinema={"cine-cinco": 2})
            _add_screening_date("cine-cinco", date(2026, 10, 9))

            report = check_import_health(["cine-cinco"], now=NOW)

            assert [c.slug for c in report.cinemas] == ["cine-cinco"]
            assert report.healthy

    def test_still_running_import_is_ignored(self, app, setup_cinemas):
        with app.app_context():
            _add_run("capitolio", features_by_cinema={"capitolio": 2})
            _add_run("capitolio", status="running", started_at=NOW)
            _add_screening_date("capitolio", date(2026, 10, 9))

            assert check_import_health(now=NOW).healthy
