from datetime import datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import PipelineRun
from flask_backend.repository import pipeline_runs


class TestStart:
    def test_creates_running_run(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")

            assert run.id is not None
            assert run.pipeline_name == "fetch-posters"
            assert run.source is None
            assert run.status == "running"
            assert run.started_at is not None
            assert run.finished_at is None

    def test_stores_source_when_given(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json", source="cine-cinco")
            assert run.source == "cine-cinco"


class TestSetSource:
    def test_updates_source_on_existing_run(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")
            pipeline_runs.set_source(run.id, "capitolio,paulo-amorim,sala-redencao")

            refreshed = db_session.query(PipelineRun).filter_by(id=run.id).one()
            assert refreshed.source == "capitolio,paulo-amorim,sala-redencao"


class TestFinish:
    def test_sets_status_finished_at_and_summary(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-movie-metadata")

            finished = pipeline_runs.finish(
                run.id, status="success", summary='{"processed": 5}'
            )

            assert finished.status == "success"
            assert finished.finished_at is not None
            assert finished.summary == '{"processed": 5}'
            assert finished.error_message is None

    def test_sets_error_message_on_error(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")

            finished = pipeline_runs.finish(
                run.id, status="error", error_message="boom"
            )

            assert finished.status == "error"
            assert finished.error_message == "boom"


class TestGetById:
    def test_returns_none_when_missing(self, app):
        with app.app_context():
            assert pipeline_runs.get_by_id(99999) is None

    def test_returns_run_when_present(self, app):
        with app.app_context():
            run = pipeline_runs.start("generate-alerts")
            found = pipeline_runs.get_by_id(run.id)
            assert found is not None
            assert found.id == run.id


class TestGetLatestByPipeline:
    def test_returns_none_when_no_runs(self, app):
        with app.app_context():
            assert pipeline_runs.get_latest_by_pipeline("fetch-posters") is None

    def test_returns_most_recent_run(self, app):
        with app.app_context():
            older = pipeline_runs.start("fetch-posters")
            older.started_at = datetime.now() - timedelta(hours=2)
            db_session.commit()

            newer = pipeline_runs.start("fetch-posters")

            latest = pipeline_runs.get_latest_by_pipeline("fetch-posters")
            assert latest.id == newer.id

    def test_filters_by_source(self, app):
        with app.app_context():
            run_a = pipeline_runs.start("import-json", source="cinebancarios")
            pipeline_runs.start("import-json", source="cine-cinco")

            latest = pipeline_runs.get_latest_by_pipeline(
                "import-json", source="cinebancarios"
            )
            assert latest.id == run_a.id


class TestGetPaginated:
    def test_paginates_and_orders_newest_first(self, app):
        with app.app_context():
            for i in range(3):
                run = pipeline_runs.start("fetch-posters")
                run.started_at = datetime.now() - timedelta(hours=3 - i)
                db_session.commit()

            runs, pages, total = pipeline_runs.get_paginated(
                "fetch-posters", current_page=1, per_page=2
            )

            assert total == 3
            assert pages == 2
            assert len(runs) == 2
            assert runs[0].started_at > runs[1].started_at

    def test_filters_by_source(self, app):
        with app.app_context():
            pipeline_runs.start("import-json", source="cinebancarios")
            pipeline_runs.start("import-json", source="cine-cinco")

            runs, pages, total = pipeline_runs.get_paginated(
                "import-json", current_page=1, per_page=20, source="cine-cinco"
            )

            assert total == 1
            assert runs[0].source == "cine-cinco"


class TestDisplayStatus:
    def test_running_recent_stays_running(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            assert pipeline_runs.display_status(run) == "running"

    def test_running_stale_shows_interrupted(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            run.started_at = datetime.now() - timedelta(hours=2)
            db_session.commit()

            assert pipeline_runs.is_interrupted(run) is True
            assert pipeline_runs.display_status(run) == "interrupted"

    def test_finished_status_passes_through(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            pipeline_runs.finish(run.id, status="warning")
            run = pipeline_runs.get_by_id(run.id)

            assert pipeline_runs.display_status(run) == "warning"
