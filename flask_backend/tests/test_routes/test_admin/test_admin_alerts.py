"""
Tests the basic functionality of /admin/alerts/* endpoints.
"""

from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import AlertAction, Movie, Screening, ScreeningDate
from flask_backend.repository import alert_actions
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


def _create_screening_with_future_date(
    app, title="Duna", slug="duna", days=1, cinema_slug="capitolio"
):
    with app.app_context():
        movie = Movie(title=title, slug=slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug(cinema_slug)
        screening = Screening(
            movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
        )
        db_session.add(screening)
        db_session.commit()
        db_session.add(
            ScreeningDate(
                screening_id=screening.id,
                date=date.today() + timedelta(days=days),
                time="20:00",
            )
        )
        db_session.commit()
        return screening.id


class TestAdminAlertsPendingView:
    def test_requires_login(self, client):
        response = client.get("/admin/alerts")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200(self, auth_headers):
        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200

    def test_invalid_pagination_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?page=invalid&limit=10")
        assert response.status_code == 400

    def test_invalid_status_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?status=bogus")
        assert response.status_code == 400

    def test_zero_limit_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?limit=0")
        assert response.status_code == 400

    def test_zero_page_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?page=0")
        assert response.status_code == 400

    def test_shows_unica_screening_with_cinema_column(
        self, app, auth_headers, setup_cinemas
    ):
        _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert "Sessão única".encode() in response.data
        assert "Cinemateca Capitólio".encode() in response.data

    def test_shows_recorrente_screening_with_until_date(
        self, app, auth_headers, setup_cinemas
    ):
        with app.app_context():
            movie = Movie(title="Duna", slug="duna", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
            )
            db_session.add(screening)
            db_session.commit()
            for offset in (1, 2, 3):
                db_session.add(
                    ScreeningDate(
                        screening_id=screening.id,
                        date=date.today() + timedelta(days=offset),
                        time="20:00",
                    )
                )
            db_session.commit()
        last_date = date.today() + timedelta(days=3)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Recorrente" in response.data
        assert f"até {last_date.strftime('%d/%m')}".encode() in response.data

    def test_excludes_screenings_with_only_past_dates(
        self, app, auth_headers, setup_cinemas
    ):
        _create_screening_with_future_date(
            app, title="Filme Antigo", slug="filme-antigo", days=-1
        )

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Filme Antigo" not in response.data

    def test_excludes_draft_screenings(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            movie = Movie(title="Rascunho", slug="rascunho", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=True
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() + timedelta(days=1),
                    time="20:00",
                )
            )
            db_session.commit()

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Rascunho" not in response.data

    def test_reminder_modal_trigger_carries_last_upcoming_date(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app, days=5)
        last_date = date.today() + timedelta(days=5)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert f'data-max-date="{last_date.isoformat()}"'.encode() in response.data
        assert screening_id is not None

    def test_shows_warning_when_no_image(self, app, auth_headers, setup_cinemas):
        _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert "Sem imagem disponível".encode() in response.data

    def test_shows_copyable_text(self, app, auth_headers, setup_cinemas):
        _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert "⏳ Duna\n\n".encode() in response.data

    def test_shows_edit_link(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert f"/screening/{screening_id}/update".encode() in response.data


class TestAdminAlertsMarkPosted:
    def test_requires_login(self, app, client, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = client.post(f"/admin/alerts/{screening_id}/mark-posted")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_nonexistent_screening_returns_404(self, auth_headers):
        response = auth_headers.post("/admin/alerts/99999/mark-posted")
        assert response.status_code == 404

    def test_records_action_without_reminder(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/mark-posted", follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            action = (
                db_session.query(AlertAction).filter_by(screening_id=screening_id).one()
            )
            assert action.action == "posted"
            assert action.remind_at is None
            assert action.created_by_user_id is not None

    def test_records_action_with_reminder(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app, days=10)
        remind_at = (date.today() + timedelta(days=5)).isoformat()

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/mark-posted",
            data={"remind_at": remind_at},
            follow_redirects=True,
        )
        assert response.status_code == 200

        with app.app_context():
            action = (
                db_session.query(AlertAction).filter_by(screening_id=screening_id).one()
            )
            assert action.remind_at == date.fromisoformat(remind_at)

    def test_invalid_reminder_format_returns_400(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/mark-posted",
            data={"remind_at": "not-a-date"},
        )
        assert response.status_code == 400

    def test_posted_screening_disappears_from_pending(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)

        auth_headers.post(f"/admin/alerts/{screening_id}/mark-posted")

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Duna" not in response.data


class TestAdminAlertsDismiss:
    def test_requires_login(self, app, client, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = client.post(f"/admin/alerts/{screening_id}/dismiss")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_nonexistent_screening_returns_404(self, auth_headers):
        response = auth_headers.post("/admin/alerts/99999/dismiss")
        assert response.status_code == 404

    def test_records_action(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/dismiss", follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            action = (
                db_session.query(AlertAction).filter_by(screening_id=screening_id).one()
            )
            assert action.action == "dismissed"


class TestAdminAlertsHistory:
    def test_posted_tab_shows_action(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        assert b"bg-success" in response.data
        assert b"Duna" in response.data

    def test_dismissed_tab_shows_action(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="dismissed")

        response = auth_headers.get("/admin/alerts?status=dismissed")
        assert response.status_code == 200
        assert b"bg-secondary" in response.data
        assert b"Duna" in response.data

    def test_posted_tab_does_not_show_dismissed_actions(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        # The nav bar always renders a "Descartados" tab label, so asserting
        # b"Descartado" not in response.data is trivially false regardless of
        # the history table's contents. Instead, check for the dismissed-action
        # badge's distinguishing CSS class ("bg-secondary"), which is only used
        # by the history table's badge markup for dismissed actions.
        assert b"Postado" in response.data
        assert b"bg-secondary" not in response.data

    def test_all_tab_shows_both(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

        response = auth_headers.get("/admin/alerts?status=all")
        assert response.status_code == 200
        # The nav bar always renders both "Postados" and "Descartados" tab
        # labels regardless of which tab is active, so asserting the raw
        # substrings proves nothing about the history table's contents.
        # Check the badge CSS classes, which only appear in the table body.
        assert b"bg-success" in response.data
        assert b"bg-secondary" in response.data

    def test_history_shows_reminder_date_when_set(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)
        remind_at = date.today() + timedelta(days=2)
        with app.app_context():
            alert_actions.create(
                screening_id=screening_id, action="posted", remind_at=remind_at
            )

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        assert remind_at.strftime("%d/%m/%Y").encode() in response.data

    def test_history_shows_dash_without_reminder(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        assert "—".encode() in response.data


class TestAdminAlertsFilters:
    def test_cinema_filter_narrows_pending_tab(self, app, auth_headers, setup_cinemas):
        _create_screening_with_future_date(
            app, title="Duna", slug="duna", cinema_slug="capitolio"
        )
        _create_screening_with_future_date(
            app, title="Coringa", slug="coringa", cinema_slug="sala-redencao"
        )

        response = auth_headers.get("/admin/alerts?cinema=capitolio")
        assert response.status_code == 200
        assert b"Duna" in response.data
        assert b"Coringa" not in response.data

    def test_cinema_filter_narrows_history_tab(self, app, auth_headers, setup_cinemas):
        duna_id = _create_screening_with_future_date(
            app, title="Duna", slug="duna", cinema_slug="capitolio"
        )
        coringa_id = _create_screening_with_future_date(
            app, title="Coringa", slug="coringa", cinema_slug="sala-redencao"
        )
        with app.app_context():
            alert_actions.create(screening_id=duna_id, action="posted")
            alert_actions.create(screening_id=coringa_id, action="posted")

        response = auth_headers.get("/admin/alerts?status=all&cinema=capitolio")
        assert response.status_code == 200
        assert b"Duna" in response.data
        assert b"Coringa" not in response.data

    def test_unknown_cinema_slug_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?cinema=nao-existe")
        assert response.status_code == 400

    def test_categoria_filter_narrows_pending_tab(
        self, app, auth_headers, setup_cinemas
    ):
        _create_screening_with_future_date(app, title="Duna", slug="duna", days=1)
        with app.app_context():
            movie = Movie(title="Coringa", slug="coringa", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
            )
            db_session.add(screening)
            db_session.commit()
            for offset in (1, 2, 3):
                db_session.add(
                    ScreeningDate(
                        screening_id=screening.id,
                        date=date.today() + timedelta(days=offset),
                        time="20:00",
                    )
                )
            db_session.commit()

        response = auth_headers.get("/admin/alerts?categoria=unica")
        assert response.status_code == 200
        assert b"Duna" in response.data
        assert b"Coringa" not in response.data

        response = auth_headers.get("/admin/alerts?categoria=recorrente")
        assert response.status_code == 200
        assert b"Coringa" in response.data
        assert b"Duna" not in response.data

    def test_invalid_categoria_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?categoria=bogus")
        assert response.status_code == 400

    def test_empty_cinema_and_categoria_are_treated_as_no_filter(
        self, app, auth_headers, setup_cinemas
    ):
        # Covers the "Todos"/"Todas" reset options in the filter form, which
        # submit cinema= / categoria= as empty strings rather than omitting
        # the param entirely.
        _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts?cinema=&categoria=")
        assert response.status_code == 200
        assert b"Duna" in response.data
