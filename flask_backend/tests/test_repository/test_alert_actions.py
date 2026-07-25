from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import AlertAction, Movie, Screening, ScreeningDate, User
from flask_backend.repository import alert_actions
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


def _create_screening(app, movie_title="Filme", movie_slug="filme"):
    with app.app_context():
        movie = Movie(title=movie_title, slug=movie_slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug("capitolio")
        screening = Screening(
            movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
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
        return screening.id


class TestCreate:
    def test_creates_action_without_reminder(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            action = alert_actions.create(screening_id=screening_id, action="posted")

            assert action.id is not None
            assert action.screening_id == screening_id
            assert action.action == "posted"
            assert action.remind_at is None
            assert action.created_at is not None

    def test_creates_action_with_reminder_and_user(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            user = User(username="admin", password="pwd")
            db_session.add(user)
            db_session.commit()

            remind_at = date.today() + timedelta(days=3)
            action = alert_actions.create(
                screening_id=screening_id,
                action="dismissed",
                remind_at=remind_at,
                created_by_user_id=user.id,
            )

            assert action.remind_at == remind_at
            assert action.created_by_user_id == user.id


class TestGetLatestByScreeningIds:
    def test_returns_most_recent_action_per_screening(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            older = AlertAction(
                screening_id=screening_id,
                action="dismissed",
                created_at=datetime(2026, 1, 1),
            )
            newer = AlertAction(
                screening_id=screening_id,
                action="posted",
                created_at=datetime(2026, 1, 2),
            )
            db_session.add_all([older, newer])
            db_session.commit()

            latest = alert_actions.get_latest_by_screening_ids([screening_id])

            assert latest[screening_id].action == "posted"

    def test_ignores_screenings_with_no_actions(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            latest = alert_actions.get_latest_by_screening_ids([screening_id])

            assert latest == {}

    def test_returns_empty_dict_for_empty_input(self, app):
        with app.app_context():
            assert alert_actions.get_latest_by_screening_ids([]) == {}


class TestGetPaginated:
    def test_filters_by_action(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

            posted, pages, count = alert_actions.get_paginated("posted", 1, 20)

            assert count == 1
            assert posted[0].action == "posted"

    def test_none_action_returns_everything(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

            actions, pages, count = alert_actions.get_paginated(None, 1, 20)

            assert count == 2


class TestDeleteForScreening:
    def test_removes_all_actions_for_the_screening(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

            alert_actions.delete_for_screening(screening_id)
            db_session.commit()

            remaining = (
                db_session.query(AlertAction)
                .filter_by(screening_id=screening_id)
                .count()
            )
            assert remaining == 0


class TestRepointToScreening:
    def test_moves_actions_to_the_new_screening(self, app, setup_cinemas):
        old_screening_id = _create_screening(app, "Filme A", "filme-a")
        new_screening_id = _create_screening(app, "Filme B", "filme-b")
        with app.app_context():
            action = alert_actions.create(
                screening_id=old_screening_id, action="posted"
            )
            action_id = action.id

            alert_actions.repoint_to_screening(old_screening_id, new_screening_id)
            db_session.commit()

            refreshed = db_session.query(AlertAction).filter_by(id=action_id).one()
            assert refreshed.screening_id == new_screening_id
