from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.screenings import (
    get_screening_dates_for_movies,
    get_screenings_in_date_range,
    get_screenings_with_upcoming_dates,
)


def _create_screening(
    app, title, slug, dates, draft=False, cinema_slug="capitolio", movie_id=None
):
    with app.app_context():
        if movie_id is None:
            movie = Movie(title=title, slug=slug, created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            movie_id = movie.id
        cinema = get_cinema_by_slug(cinema_slug)
        screening = Screening(
            movie_id=movie_id,
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
        return screening.id, movie_id


class TestGetScreeningsWithUpcomingDates:
    def test_includes_screening_with_a_future_date(self, app, setup_cinemas):
        screening_id, _ = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id in ids

    def test_excludes_screening_with_only_past_dates(self, app, setup_cinemas):
        screening_id, _ = _create_screening(
            app, "Filme Antigo", "filme-antigo", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id not in ids

    def test_excludes_draft_screenings(self, app, setup_cinemas):
        screening_id, _ = _create_screening(
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
        screening_id, _ = _create_screening(
            app,
            "Recorrente",
            "recorrente",
            [date.today() + timedelta(days=1), date.today() + timedelta(days=2)],
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert ids.count(screening_id) == 1


class TestGetScreeningsInDateRange:
    def test_includes_screening_with_a_date_inside_the_range(self, app, setup_cinemas):
        screening_id, _ = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=3)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_excludes_screening_with_a_date_before_the_range(self, app, setup_cinemas):
        screening_id, _ = _create_screening(
            app, "Filme Passado", "filme-passado", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id not in ids

    def test_excludes_screening_with_a_date_after_the_range(self, app, setup_cinemas):
        screening_id, _ = _create_screening(
            app, "Filme Futuro", "filme-futuro", [date.today() + timedelta(days=7)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id not in ids

    def test_includes_screening_with_a_date_on_the_last_day_of_the_range(
        self, app, setup_cinemas
    ):
        screening_id, _ = _create_screening(
            app, "Filme Limite", "filme-limite", [date.today() + timedelta(days=6)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_includes_draft_screenings(self, app, setup_cinemas):
        screening_id, _ = _create_screening(
            app, "Rascunho", "rascunho", [date.today()], draft=True
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_does_not_duplicate_screenings_with_multiple_dates_in_range(
        self, app, setup_cinemas
    ):
        screening_id, _ = _create_screening(
            app,
            "Recorrente",
            "recorrente",
            [date.today(), date.today() + timedelta(days=1)],
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert ids.count(screening_id) == 1


class TestGetScreeningDatesForMovies:
    def test_includes_dates_for_the_requested_movie(self, app, setup_cinemas):
        screening_id, movie_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=2)]
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 1
            assert dates[0].screening_id == screening_id

    def test_aggregates_dates_across_cinemas_for_the_same_movie(
        self, app, setup_cinemas
    ):
        _screening_id_a, movie_id = _create_screening(
            app, "Filme", "filme", [date.today()], cinema_slug="capitolio"
        )
        _create_screening(
            app,
            "Filme",
            "filme",
            [date.today() + timedelta(days=1)],
            cinema_slug="sala-redencao",
            movie_id=movie_id,
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 2

    def test_excludes_dates_for_other_movies(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app, "Filme A", "filme-a", [date.today()]
        )
        _create_screening(app, "Filme B", "filme-b", [date.today()])

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 1

    def test_excludes_dates_outside_the_range(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app,
            "Filme",
            "filme",
            [date.today(), date.today() + timedelta(days=10)],
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 1

    def test_excludes_draft_screening_dates_by_default(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app, "Rascunho", "rascunho", [date.today()], draft=True
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert dates == []

    def test_includes_draft_screening_dates_when_include_drafts_is_true(
        self, app, setup_cinemas
    ):
        _screening_id, movie_id = _create_screening(
            app, "Rascunho", "rascunho", [date.today()], draft=True
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id],
                date.today(),
                date.today() + timedelta(days=6),
                include_drafts=True,
            )
            assert len(dates) == 1

    def test_returns_empty_list_for_empty_movie_ids(self, app, setup_cinemas):
        with app.app_context():
            assert get_screening_dates_for_movies([], date.today(), date.today()) == []
