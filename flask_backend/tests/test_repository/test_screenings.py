from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.screenings import (
    get_latest_screening_for_movie,
    get_past_movies_for_cinema,
    get_screening_dates_for_movies,
    get_screenings_for_movies_with_dates_in_range,
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


class TestGetScreeningsForMoviesWithDatesInRange:
    def test_includes_screening_for_requested_movie_within_range(
        self, app, setup_cinemas
    ):
        screening_id, movie_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_for_movies_with_dates_in_range(
                    [movie_id], date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_excludes_screening_for_a_different_movie(self, app, setup_cinemas):
        _, movie_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=1)]
        )
        other_screening_id, _ = _create_screening(
            app, "Outro Filme", "outro-filme", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_for_movies_with_dates_in_range(
                    [movie_id], date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert other_screening_id not in ids

    def test_returns_empty_list_for_no_movie_ids(self, app, setup_cinemas):
        with app.app_context():
            result = get_screenings_for_movies_with_dates_in_range(
                [], date.today(), date.today()
            )
            assert result == []


class TestGetLatestScreeningForMovie:
    def test_returns_the_most_recently_created_screening(self, app, setup_cinemas):
        with app.app_context():
            movie = Movie(title="Filme", slug="filme", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            older = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="antiga",
                created_at=datetime.now() - timedelta(days=10),
            )
            newer = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="recente",
                created_at=datetime.now(),
            )
            db_session.add_all([older, newer])
            db_session.commit()

            latest = get_latest_screening_for_movie(movie.id)

            assert latest.id == newer.id

    def test_returns_none_for_movie_without_screenings(self, app, setup_cinemas):
        with app.app_context():
            movie = Movie(
                title="Sem Sessão", slug="sem-sessao", created_at=datetime.now()
            )
            db_session.add(movie)
            db_session.commit()

            assert get_latest_screening_for_movie(movie.id) is None

    def test_skips_a_newer_draft_and_returns_the_newest_non_draft_by_default(
        self, app, setup_cinemas
    ):
        with app.app_context():
            movie = Movie(title="Filme Rascunho Novo", slug="filme-rascunho-novo-repo")
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            older_non_draft = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="antiga publicada",
                draft=False,
                created_at=datetime.now() - timedelta(days=10),
            )
            newer_draft = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="recente rascunho",
                draft=True,
                created_at=datetime.now(),
            )
            db_session.add_all([older_non_draft, newer_draft])
            db_session.commit()

            latest = get_latest_screening_for_movie(movie.id)

            assert latest.id == older_non_draft.id

    def test_include_drafts_true_returns_the_newest_regardless_of_draft_status(
        self, app, setup_cinemas
    ):
        with app.app_context():
            movie = Movie(
                title="Filme Rascunho Novo Logado", slug="filme-rascunho-novo-logado"
            )
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            older_non_draft = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="antiga publicada",
                draft=False,
                created_at=datetime.now() - timedelta(days=10),
            )
            newer_draft = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="recente rascunho",
                draft=True,
                created_at=datetime.now(),
            )
            db_session.add_all([older_non_draft, newer_draft])
            db_session.commit()

            latest = get_latest_screening_for_movie(movie.id, include_drafts=True)

            assert latest.id == newer_draft.id


class TestGetPastMoviesForCinema:
    def test_includes_movie_with_only_a_past_date(self, app, setup_cinemas):
        screening_id, movie_id = _create_screening(
            app, "Filme Antigo", "filme-antigo", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            result = get_past_movies_for_cinema(get_cinema_by_slug("capitolio").id)
            movie_ids = [movie.id for movie, _exclusive in result]
            assert movie_id in movie_ids

    def test_excludes_movie_with_an_upcoming_date_at_this_cinema(
        self, app, setup_cinemas
    ):
        screening_id, movie_id = _create_screening(
            app, "Filme Futuro", "filme-futuro", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            result = get_past_movies_for_cinema(get_cinema_by_slug("capitolio").id)
            movie_ids = [movie.id for movie, _exclusive in result]
            assert movie_id not in movie_ids

    def test_marks_movie_screened_only_here_as_exclusive(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app, "Exclusivo", "exclusivo", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            result = get_past_movies_for_cinema(get_cinema_by_slug("capitolio").id)
            exclusivity_by_id = {movie.id: exclusive for movie, exclusive in result}
            assert exclusivity_by_id[movie_id] is True

    def test_marks_movie_screened_elsewhere_as_not_exclusive(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app, "Compartilhado", "compartilhado", [date.today() - timedelta(days=2)]
        )
        _create_screening(
            app,
            "Compartilhado",
            "compartilhado",
            [date.today() - timedelta(days=1)],
            cinema_slug="sala-redencao",
            movie_id=movie_id,
        )

        with app.app_context():
            result = get_past_movies_for_cinema(get_cinema_by_slug("capitolio").id)
            exclusivity_by_id = {movie.id: exclusive for movie, exclusive in result}
            assert exclusivity_by_id[movie_id] is False

    def test_excludes_draft_screening_with_a_past_date(self, app, setup_cinemas):
        screening_id, movie_id = _create_screening(
            app,
            "Rascunho Passado",
            "rascunho-passado",
            [date.today() - timedelta(days=1)],
            draft=True,
        )

        with app.app_context():
            result = get_past_movies_for_cinema(get_cinema_by_slug("capitolio").id)
            movie_ids = [movie.id for movie, _exclusive in result]
            assert movie_id not in movie_ids

    def test_caps_result_to_24_most_recently_shown_movies(self, app, setup_cinemas):
        movie_ids_by_recency = []
        for days_ago in range(30, 0, -1):
            _screening_id, movie_id = _create_screening(
                app,
                f"Filme {days_ago}",
                f"filme-{days_ago}",
                [date.today() - timedelta(days=days_ago)],
            )
            movie_ids_by_recency.append(movie_id)
        # movie_ids_by_recency is ordered from oldest (30 days ago) to most
        # recently shown (1 day ago) - the 24 most recent are the last 24.
        expected_movie_ids = set(movie_ids_by_recency[-24:])

        with app.app_context():
            result = get_past_movies_for_cinema(get_cinema_by_slug("capitolio").id)
            movie_ids = [movie.id for movie, _exclusive in result]
            assert len(movie_ids) == 24
            assert set(movie_ids) == expected_movie_ids
