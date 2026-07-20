"""
Tests the basic functionality of /admin/alerts/* endpoints.
"""

from datetime import datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Alert, Director, Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


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
        # Pending alerts get their drafted_text regenerated on page load
        # (see flask_backend.service.alert_text) - "Filme" has no
        # year/director/upcoming screening in this fixture.
        assert "🎬 Filme".encode() in response.data
        assert "Sem sessão futura agendada".encode() in response.data

    def test_admin_alerts_index_status_all_shows_everything(
        self, app, auth_headers, setup_cinemas
    ):
        movie_id = _create_movie(app)
        _create_alert(app, movie_id, status="posted")

        response = auth_headers.get("/admin/alerts?status=all")
        assert response.status_code == 200
        assert b"Texto sugerido para postar" in response.data

    def test_admin_alerts_index_regenerates_and_persists_full_format(
        self, app, auth_headers, setup_cinemas
    ):
        with app.app_context():
            movie = Movie(
                title="Duna",
                slug="duna",
                release_year=2021,
                created_at=datetime.now(),
            )
            db_session.add(movie)
            db_session.commit()

            director = Director(tmdb_id=1, name="Denis Villeneuve")
            db_session.add(director)
            movie.directors.append(director)

            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                created_at=datetime.now(),
            )
            db_session.add(screening)
            db_session.commit()

            future_date = (datetime.now() + timedelta(days=1)).date()
            db_session.add(
                ScreeningDate(screening_id=screening.id, date=future_date, time="20:00")
            )
            db_session.commit()

            alert = Alert(
                rule_name="new_movie",
                movie_id=movie.id,
                screening_id=screening.id,
                dedup_key=f"new_movie:{movie.id}",
                drafted_text="texto desatualizado",
                status="pending",
                created_at=datetime.now(),
            )
            db_session.add(alert)
            db_session.commit()
            alert_id = alert.id

            expected_text = (
                f"🎬 Duna (2021) de Denis Villeneuve\n\n"
                f"{future_date.strftime('%d/%m')} 20:00\n"
                f"Na {cinema.name}"
            )

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert expected_text.encode() in response.data

        with app.app_context():
            refreshed = db_session.query(Alert).filter_by(id=alert_id).one()
            assert refreshed.drafted_text == expected_text

    def test_admin_alerts_index_shows_image_from_first_screening_that_has_one(
        self, app, auth_headers, setup_cinemas
    ):
        with app.app_context():
            movie = Movie(title="Duna", slug="duna", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()

            cinema = get_cinema_by_slug("capitolio")
            no_image_screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                image=None,
                created_at=datetime.now(),
            )
            with_image_screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                image="https://example.com/duna.jpg",
                image_alt="Cartaz de Duna",
                created_at=datetime.now(),
            )
            db_session.add_all([no_image_screening, with_image_screening])
            db_session.commit()

            alert = Alert(
                rule_name="new_movie",
                movie_id=movie.id,
                screening_id=with_image_screening.id,
                dedup_key=f"new_movie:{movie.id}",
                drafted_text="texto",
                status="pending",
                created_at=datetime.now(),
            )
            db_session.add(alert)
            db_session.commit()

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b'src="https://example.com/duna.jpg"' in response.data
        assert b'alt="Cartaz de Duna"' in response.data

    def test_admin_alerts_index_shows_warning_when_no_screening_has_image(
        self, app, auth_headers, setup_cinemas
    ):
        movie_id = _create_movie(app)
        _create_alert(app, movie_id, status="pending")

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert "Sem imagem disponível".encode() in response.data


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
