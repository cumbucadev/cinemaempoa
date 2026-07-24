from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.screening_alerts import (
    RECORRENTE,
    UNICA,
    classify,
    last_upcoming_date,
)


def _create_movie(title="Filme", slug="filme"):
    movie = Movie(title=title, slug=slug, created_at=datetime.now())
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, dates, cinema_slug="capitolio"):
    cinema = get_cinema_by_slug(cinema_slug)
    screening = Screening(
        movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
    )
    db_session.add(screening)
    db_session.commit()
    for screening_date in dates:
        db_session.add(
            ScreeningDate(screening_id=screening.id, date=screening_date, time="20:00")
        )
    db_session.commit()
    db_session.refresh(screening)
    return screening


class TestClassify:
    def test_single_upcoming_date_is_unica(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])

            assert classify(screening, today=date(2026, 7, 24)) == UNICA

    def test_multiple_upcoming_dates_is_recorrente(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(
                movie, [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]
            )

            assert classify(screening, today=date(2026, 7, 24)) == RECORRENTE

    def test_last_day_of_a_long_run_stays_recorrente(self, client, app, setup_cinemas):
        # Regression: without the grace-period window, a recorring
        # screening's remaining-future-date count drops to 1 on its last
        # scheduled day, misclassifying it as "unica" right when it's
        # wrapping up a long run.
        with client.application.app_context():
            movie = _create_movie()
            past_dates = [date(2026, 6, day) for day in range(1, 21)]
            screening = _create_screening(movie, [*past_dates, date(2026, 7, 24)])

            assert classify(screening, today=date(2026, 7, 24)) == RECORRENTE

    def test_prior_occurrence_outside_grace_window_resets_to_unica(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2025, 11, 20), date(2026, 8, 1)])

            assert classify(screening, today=date(2026, 7, 24)) == UNICA

    def test_grace_window_boundary_is_inclusive(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            today = date(2026, 7, 24)
            boundary_date = today - relativedelta(months=6)
            screening = _create_screening(movie, [boundary_date, date(2026, 8, 1)])

            assert classify(screening, today=today) == RECORRENTE


class TestLastUpcomingDate:
    def test_returns_the_latest_upcoming_date(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(
                movie, [date(2026, 8, 1), date(2026, 8, 10), date(2026, 6, 1)]
            )

            assert last_upcoming_date(screening, today=date(2026, 7, 24)) == date(
                2026, 8, 10
            )

    def test_returns_none_without_upcoming_dates(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 1, 1)])

            assert last_upcoming_date(screening, today=date(2026, 7, 24)) is None
