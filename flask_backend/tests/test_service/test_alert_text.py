from datetime import datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Alert, Director, Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.screenings import get_next_screening_date_for_movie
from flask_backend.service.alert_text import (
    NO_UPCOMING_SCREENING_TEXT,
    RULE_EMOJIS,
    build_drafted_text,
    refresh_pending,
)

TODAY = datetime.now().date()


def _create_movie(title, slug, created_at=None, **extra):
    movie = Movie(
        title=title, slug=slug, created_at=created_at or datetime.now(), **extra
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, cinema_slug, dates=None, **extra):
    cinema = get_cinema_by_slug(cinema_slug)
    defaults = {
        "description": "desc",
        "image": None,
        "image_alt": None,
        "image_width": None,
        "image_height": None,
        "draft": False,
        "url": None,
    }
    defaults.update(extra)
    screening = Screening(
        movie_id=movie.id,
        cinema_id=cinema.id,
        created_at=datetime.now(),
        **defaults,
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)

    for screening_date, screening_time in dates or [(TODAY, "20:00")]:
        db_session.add(
            ScreeningDate(
                screening_id=screening.id, date=screening_date, time=screening_time
            )
        )
    db_session.commit()
    db_session.refresh(screening)
    return screening


def _create_alert(movie, rule_name="new_movie", status="pending", screening_id=None):
    alert = Alert(
        rule_name=rule_name,
        movie_id=movie.id,
        screening_id=screening_id,
        dedup_key=f"{rule_name}:{movie.id}:{status}",
        drafted_text="texto original",
        status=status,
        created_at=datetime.now(),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


class TestGetNextScreeningDateForMovie:
    def test_returns_earliest_future_date_across_screenings(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            _create_screening(
                movie, "capitolio", dates=[(TODAY + timedelta(days=5), "20:00")]
            )
            _create_screening(
                movie, "cinebancarios", dates=[(TODAY + timedelta(days=1), "18:00")]
            )

            next_date = get_next_screening_date_for_movie(movie.id)

            assert next_date is not None
            assert next_date.date == TODAY + timedelta(days=1)
            assert next_date.time == "18:00"

    def test_returns_none_when_only_past_dates(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            _create_screening(
                movie, "capitolio", dates=[(TODAY - timedelta(days=1), "20:00")]
            )

            assert get_next_screening_date_for_movie(movie.id) is None

    def test_excludes_draft_screenings(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            _create_screening(
                movie,
                "capitolio",
                dates=[(TODAY + timedelta(days=1), "20:00")],
                draft=True,
            )

            assert get_next_screening_date_for_movie(movie.id) is None


class TestBuildDraftedText:
    def test_full_data(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Duna", "duna", release_year=2021)
            director = Director(tmdb_id=1, name="Denis Villeneuve")
            db_session.add(director)
            movie.directors.append(director)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            _create_screening(
                movie, "capitolio", dates=[(TODAY + timedelta(days=1), "20:00")]
            )
            alert = _create_alert(movie, rule_name="new_movie")

            text = build_drafted_text(alert)

            expected_date = (TODAY + timedelta(days=1)).strftime("%d/%m")
            assert text == (
                f"🎬 Duna (2021) de Denis Villeneuve\n\n"
                f"{expected_date} 20:00\n"
                f"Na {cinema.name}"
            )

    def test_omits_director_clause_when_no_director(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Duna", "duna", release_year=2021)
            _create_screening(
                movie, "capitolio", dates=[(TODAY + timedelta(days=1), "20:00")]
            )
            alert = _create_alert(movie, rule_name="new_movie")

            text = build_drafted_text(alert)

            assert text.startswith("🎬 Duna (2021)\n\n")
            assert " de " not in text.splitlines()[0]

    def test_omits_year_when_missing(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Duna", "duna")
            _create_screening(
                movie, "capitolio", dates=[(TODAY + timedelta(days=1), "20:00")]
            )
            alert = _create_alert(movie, rule_name="new_movie")

            text = build_drafted_text(alert)

            assert text.splitlines()[0] == "🎬 Duna"

    def test_placeholder_when_no_upcoming_screening(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Duna", "duna", release_year=2021)
            alert = _create_alert(movie, rule_name="new_movie")

            text = build_drafted_text(alert)

            assert text == f"🎬 Duna (2021)\n\n{NO_UPCOMING_SCREENING_TEXT}"

    def test_each_rule_uses_its_own_emoji(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            for rule_name, emoji in RULE_EMOJIS.items():
                alert = _create_alert(movie, rule_name=rule_name)
                assert build_drafted_text(alert).startswith(emoji)


class TestRefreshPending:
    def test_only_updates_pending_alerts(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Duna", "duna", release_year=2021)
            _create_screening(
                movie, "capitolio", dates=[(TODAY + timedelta(days=1), "20:00")]
            )
            pending = _create_alert(movie, status="pending")
            posted = _create_alert(movie, status="posted")

            refresh_pending([pending, posted])

            assert pending.drafted_text != "texto original"
            assert pending.drafted_text.startswith("🎬 Duna (2021)")
            assert posted.drafted_text == "texto original"

            refreshed_pending = db_session.query(Alert).filter_by(id=pending.id).one()
            refreshed_posted = db_session.query(Alert).filter_by(id=posted.id).one()
            assert refreshed_pending.drafted_text == pending.drafted_text
            assert refreshed_posted.drafted_text == "texto original"
