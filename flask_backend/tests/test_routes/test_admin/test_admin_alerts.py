"""
Tests the basic functionality of /admin/alerts/* endpoints.
"""

from datetime import datetime

from flask_backend.db import db_session
from flask_backend.models import Alert, Movie


def _create_movie(app):
    with app.app_context():
        movie = Movie(title="Filme", slug="filme", created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        return movie.id


def _create_alert(app, movie_id, status="pending", rule_name="new_movie"):
    with app.app_context():
        alert = Alert(
            rule_name=rule_name,
            movie_id=movie_id,
            screening_id=None,
            dedup_key=f"{rule_name}:{movie_id}:{status}",
            drafted_text="Texto sugerido para postar",
            status=status,
            created_at=datetime.now(),
        )
        db_session.add(alert)
        db_session.commit()
        return alert.id


class TestAdminAlertsIndex:
    def test_admin_alerts_index_requires_login(self, client):
        response = client.get("/admin/alerts")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_admin_alerts_index_with_auth_returns_200(self, auth_headers):
        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200

    def test_admin_alerts_index_invalid_pagination_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?page=invalid&limit=10")
        assert response.status_code == 400

    def test_admin_alerts_index_invalid_status_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?status=bogus")
        assert response.status_code == 400

    def test_admin_alerts_index_zero_limit_returns_400(
        self, app, auth_headers, setup_cinemas
    ):
        movie_id = _create_movie(app)
        _create_alert(app, movie_id, status="pending")

        response = auth_headers.get("/admin/alerts?limit=0")
        assert response.status_code == 400

    def test_admin_alerts_index_zero_page_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?page=0")
        assert response.status_code == 400

    def test_admin_alerts_index_negative_page_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?page=-1")
        assert response.status_code == 400

    def test_admin_alerts_index_defaults_to_pending(
        self, app, auth_headers, setup_cinemas
    ):
        movie_id = _create_movie(app)
        _create_alert(app, movie_id, status="pending")
        _create_alert(app, movie_id, status="posted")

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Texto sugerido para postar" in response.data

    def test_admin_alerts_index_status_all_shows_everything(
        self, app, auth_headers, setup_cinemas
    ):
        movie_id = _create_movie(app)
        _create_alert(app, movie_id, status="posted")

        response = auth_headers.get("/admin/alerts?status=all")
        assert response.status_code == 200
        assert b"Texto sugerido para postar" in response.data


class TestAdminAlertsMarkPosted:
    def test_mark_posted_requires_login(self, app, client, setup_cinemas):
        movie_id = _create_movie(app)
        alert_id = _create_alert(app, movie_id)

        response = client.post(f"/admin/alerts/{alert_id}/mark-posted")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_mark_posted_nonexistent_alert_returns_404(self, auth_headers):
        response = auth_headers.post("/admin/alerts/99999/mark-posted")
        assert response.status_code == 404

    def test_mark_posted_with_auth_updates_status(
        self, app, auth_headers, setup_cinemas
    ):
        movie_id = _create_movie(app)
        alert_id = _create_alert(app, movie_id)

        response = auth_headers.post(
            f"/admin/alerts/{alert_id}/mark-posted", follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            alert = db_session.query(Alert).filter_by(id=alert_id).one()
            assert alert.status == "posted"
            assert alert.resolved_at is not None
            assert alert.resolved_by_user_id is not None


class TestAdminAlertsDismiss:
    def test_dismiss_requires_login(self, app, client, setup_cinemas):
        movie_id = _create_movie(app)
        alert_id = _create_alert(app, movie_id)

        response = client.post(f"/admin/alerts/{alert_id}/dismiss")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_dismiss_nonexistent_alert_returns_404(self, auth_headers):
        response = auth_headers.post("/admin/alerts/99999/dismiss")
        assert response.status_code == 404

    def test_dismiss_with_auth_updates_status(self, app, auth_headers, setup_cinemas):
        movie_id = _create_movie(app)
        alert_id = _create_alert(app, movie_id)

        response = auth_headers.post(
            f"/admin/alerts/{alert_id}/dismiss", follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            alert = db_session.query(Alert).filter_by(id=alert_id).one()
            assert alert.status == "dismissed"
