"""
Tests the basic functionality of /admin/pipelines/* endpoints.
"""

from flask_backend.db import db_session
from flask_backend.repository import pipeline_runs


class TestAdminPipelinesIndex:
    def test_requires_login(self, client):
        response = client.get("/admin/pipelines")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200_with_no_runs(self, auth_headers):
        response = auth_headers.get("/admin/pipelines")
        assert response.status_code == 200
        assert b"Nunca executado" in response.data

    def test_shows_latest_status_per_group(self, app, auth_headers):
        with app.app_context():
            run = pipeline_runs.start(
                "import-json", source="capitolio,paulo-amorim,sala-redencao"
            )
            pipeline_runs.finish(run.id, status="success", summary='{"created": 3}')
            db_session.commit()

        response = auth_headers.get("/admin/pipelines")
        assert response.status_code == 200
        assert b"Sucesso" in response.data

    def test_shows_interrupted_for_stale_running_run(self, app, auth_headers):
        from datetime import datetime, timedelta

        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            run.started_at = datetime.now() - timedelta(hours=2)
            db_session.commit()

        response = auth_headers.get("/admin/pipelines")
        assert response.status_code == 200
        assert b"Interrompida" in response.data


class TestAdminPipelinesHistory:
    def test_requires_login(self, client):
        response = client.get("/admin/pipelines/fetch-posters")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200_with_no_runs(self, auth_headers):
        response = auth_headers.get("/admin/pipelines/fetch-posters")
        assert response.status_code == 200

    def test_invalid_pagination_returns_400(self, auth_headers):
        response = auth_headers.get(
            "/admin/pipelines/fetch-posters?page=invalid&limit=10"
        )
        assert response.status_code == 400

    def test_zero_limit_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/pipelines/fetch-posters?limit=0")
        assert response.status_code == 400

    def test_lists_runs_for_pipeline(self, app, auth_headers):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            pipeline_runs.finish(run.id, status="success", summary='{"processed": 4}')
            db_session.commit()

        response = auth_headers.get("/admin/pipelines/fetch-posters")
        assert response.status_code == 200
        assert b"Sucesso" in response.data

    def test_filters_by_source(self, app, auth_headers):
        with app.app_context():
            run_a = pipeline_runs.start("import-json", source="cinebancarios")
            pipeline_runs.finish(run_a.id, status="success", summary='{"created": 1}')
            run_b = pipeline_runs.start("import-json", source="cine-cinco")
            pipeline_runs.finish(run_b.id, status="success", summary='{"created": 2}')
            db_session.commit()

        response = auth_headers.get("/admin/pipelines/import-json?source=cinebancarios")
        assert response.status_code == 200
        assert b'"created": 1' in response.data
        assert b'"created": 2' not in response.data
