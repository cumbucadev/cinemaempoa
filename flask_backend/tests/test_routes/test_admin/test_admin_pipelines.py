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


class TestAdminPipelinesDetail:
    def test_requires_login(self, app, client):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            db_session.commit()
            run_id = run.id

        response = client.get(f"/admin/pipelines/fetch-posters/{run_id}")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_unknown_run(self, auth_headers):
        response = auth_headers.get("/admin/pipelines/fetch-posters/99999")
        assert response.status_code == 404

    def test_returns_404_when_pipeline_name_mismatches_run(self, app, auth_headers):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            db_session.commit()
            run_id = run.id

        response = auth_headers.get(f"/admin/pipelines/generate-alerts/{run_id}")
        assert response.status_code == 404

    def test_shows_screenings_created_for_import_json_run(
        self, app, auth_headers, setup_cinemas
    ):
        from flask_backend.models import Movie, Screening
        from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug

        with app.app_context():
            run = pipeline_runs.start(
                "import-json", source="capitolio,paulo-amorim,sala-redencao"
            )
            pipeline_runs.finish(run.id, status="success", summary='{"created": 1}')
            movie = Movie(title="Filme do Run", slug="filme-do-run")
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                pipeline_run_id=run.id,
            )
            db_session.add(screening)
            db_session.commit()
            run_id = run.id

        response = auth_headers.get(f"/admin/pipelines/import-json/{run_id}")
        assert response.status_code == 200
        assert b"Filme do Run" in response.data

    def test_shows_alerts_created_for_generate_alerts_run(self, app, auth_headers):
        from flask_backend.models import Alert, Movie

        with app.app_context():
            run = pipeline_runs.start("generate-alerts")
            pipeline_runs.finish(run.id, status="success")
            movie = Movie(title="Filme Alertado", slug="filme-alertado")
            db_session.add(movie)
            db_session.commit()
            alert = Alert(
                rule_name="new_movie",
                movie_id=movie.id,
                screening_id=None,
                dedup_key=f"new_movie:{movie.id}",
                drafted_text="texto",
                status="pending",
                pipeline_run_id=run.id,
            )
            db_session.add(alert)
            db_session.commit()
            run_id = run.id

        response = auth_headers.get(f"/admin/pipelines/generate-alerts/{run_id}")
        assert response.status_code == 200
        assert b"Filme Alertado" in response.data
