from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.screenings import get_screenings_with_upcoming_dates


def _create_screening(app, title, slug, dates, draft=False):
    with app.app_context():
        movie = Movie(title=title, slug=slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug("capitolio")
        screening = Screening(
            movie_id=movie.id,
            cinema_id=cinema.id,
            description="desc",
            draft=draft,
        )
        db_session.add(screening)
        db_session.commit()
        for screening_date in dates:
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id, date=screening_date, time="20:00"
                )
            )
        db_session.commit()
        return screening.id


class TestGetScreeningsWithUpcomingDates:
    def test_includes_screening_with_a_future_date(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id in ids

    def test_excludes_screening_with_only_past_dates(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Filme Antigo", "filme-antigo", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id not in ids

    def test_excludes_draft_screenings(self, app, setup_cinemas):
        screening_id = _create_screening(
            app,
            "Rascunho",
            "rascunho",
            [date.today() + timedelta(days=1)],
            draft=True,
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id not in ids

    def test_does_not_duplicate_screenings_with_multiple_future_dates(
        self, app, setup_cinemas
    ):
        screening_id = _create_screening(
            app,
            "Recorrente",
            "recorrente",
            [date.today() + timedelta(days=1), date.today() + timedelta(days=2)],
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert ids.count(screening_id) == 1
