from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from flask_backend.db import db_session
from flask_backend.models import AlertAction, Director, Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.screening_alerts import (
    RECORRENTE,
    UNICA,
    build_drafted_text,
    classify,
    get_pending_rows,
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


class TestBuildDraftedText:
    def test_unica_includes_emoji_year_director_next_date_and_cinema(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie(title="Duna", slug="duna")
            movie.release_year = 2021
            director = Director(tmdb_id=1, name="Denis Villeneuve")
            db_session.add(director)
            movie.directors.append(director)
            db_session.commit()

            screening = _create_screening(movie, [date(2026, 8, 1)])

            text = build_drafted_text(screening, today=date(2026, 7, 24))

            assert text == (
                "⏳ Duna (2021) de Denis Villeneuve\n\n"
                "01/08 20:00\nNa Cinemateca Capitólio"
            )

    def test_recorrente_uses_the_next_upcoming_date_not_the_last(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie(title="Duna", slug="duna")
            screening = _create_screening(
                movie, [date(2026, 8, 1), date(2026, 8, 5), date(2026, 8, 10)]
            )

            text = build_drafted_text(screening, today=date(2026, 7, 24))

            assert text.startswith("🔁 Duna\n\n01/08 20:00")

    def test_omits_year_and_director_when_absent(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie(title="Filme Sem Metadados", slug="filme-sem-meta")
            screening = _create_screening(movie, [date(2026, 8, 1)])

            text = build_drafted_text(screening, today=date(2026, 7, 24))

            assert text.startswith("⏳ Filme Sem Metadados\n\n")


class TestGetPendingRows:
    def test_includes_screening_with_no_action(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])

            rows = get_pending_rows([screening], {}, today=date(2026, 7, 24))

            assert len(rows) == 1
            assert rows[0].screening.id == screening.id
            assert rows[0].category == UNICA
            assert rows[0].last_upcoming_date == date(2026, 8, 1)

    def test_excludes_screening_with_indefinite_action(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])
            action = AlertAction(
                screening_id=screening.id, action="posted", created_at=datetime.now()
            )

            rows = get_pending_rows(
                [screening], {screening.id: action}, today=date(2026, 7, 24)
            )

            assert rows == []

    def test_excludes_screening_whose_reminder_has_not_arrived(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])
            action = AlertAction(
                screening_id=screening.id,
                action="dismissed",
                created_at=datetime.now(),
                remind_at=date(2026, 7, 30),
            )

            rows = get_pending_rows(
                [screening], {screening.id: action}, today=date(2026, 7, 24)
            )

            assert rows == []

    def test_includes_screening_whose_reminder_has_arrived(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])
            action = AlertAction(
                screening_id=screening.id,
                action="posted",
                created_at=datetime.now(),
                remind_at=date(2026, 7, 24),
            )

            rows = get_pending_rows(
                [screening], {screening.id: action}, today=date(2026, 7, 24)
            )

            assert len(rows) == 1

    def test_sorts_by_nearest_upcoming_date_ascending(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            later = _create_screening(movie, [date(2026, 9, 1)])
            sooner = _create_screening(
                _create_movie(title="Filme 2", slug="filme-2"), [date(2026, 8, 1)]
            )

            rows = get_pending_rows([later, sooner], {}, today=date(2026, 7, 24))

            assert [row.screening.id for row in rows] == [sooner.id, later.id]
