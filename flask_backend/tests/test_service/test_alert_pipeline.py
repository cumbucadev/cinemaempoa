from datetime import datetime

from flask_backend.db import db_session
from flask_backend.models import Alert, Director, Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.alert_pipeline import run_pipeline


def _create_movie(title, slug, created_at=None, **extra):
    movie = Movie(
        title=title, slug=slug, created_at=created_at or datetime.now(), **extra
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, cinema_slug, dates=None, created_at=None, **extra):
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
        created_at=created_at or datetime.now(),
        **defaults,
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    for screening_date, screening_time in dates or [(datetime.now().date(), "20:00")]:
        db_session.add(
            ScreeningDate(
                screening_id=screening.id, date=screening_date, time=screening_time
            )
        )
    db_session.commit()
    db_session.refresh(screening)
    return screening


class TestRunPipelineCorePass:
    def test_creates_alerts_for_a_due_screening(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(movie, "capitolio")

            result = run_pipeline()

            assert result.screenings_evaluated == 1
            # new_movie + single_screening both fire for a fresh, one-date screening
            assert result.alerts_created == 2
            assert set(result.alerts_by_rule) == {"new_movie", "single_screening"}

            refreshed = db_session.query(Screening).filter_by(id=screening.id).one()
            assert refreshed.core_alerts_evaluated_at is not None

            alerts = db_session.query(Alert).filter_by(movie_id=movie.id).all()
            assert len(alerts) == 2

    def test_skips_screenings_already_evaluated(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            _create_screening(
                movie, "capitolio", core_alerts_evaluated_at=datetime.now()
            )

            result = run_pipeline()

            assert result.screenings_evaluated == 0
            assert result.alerts_created == 0


class TestRunPipelineMetadataPass:
    def test_creates_director_debut_alert_for_movie_with_director(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            director = Director(tmdb_id=1, name="Jane Director")
            db_session.add(director)
            db_session.commit()

            movie = _create_movie("Filme", "filme")
            movie.directors.append(director)
            db_session.commit()

            result = run_pipeline()

            assert result.movies_evaluated == 1
            assert "director_debut" in result.alerts_by_rule

            refreshed = db_session.query(Movie).filter_by(id=movie.id).one()
            assert refreshed.metadata_alerts_evaluated_at is not None

    def test_skips_movies_already_evaluated(self, client, app, setup_cinemas):
        with client.application.app_context():
            director = Director(tmdb_id=1, name="Jane Director")
            db_session.add(director)
            db_session.commit()

            movie = _create_movie("Filme", "filme")
            movie.directors.append(director)
            movie.metadata_alerts_evaluated_at = datetime.now()
            db_session.commit()

            result = run_pipeline()

            assert result.movies_evaluated == 0


class TestRunPipelineIdempotency:
    def test_second_run_creates_no_new_alerts(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            _create_screening(movie, "capitolio")

            first = run_pipeline()
            second = run_pipeline()

            assert first.alerts_created > 0
            assert second.screenings_evaluated == 0
            assert second.alerts_created == 0

            alerts = db_session.query(Alert).filter_by(movie_id=movie.id).all()
            assert len(alerts) == first.alerts_created


class TestRunPipelineDryRun:
    def test_dry_run_writes_nothing(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(movie, "capitolio")

            result = run_pipeline(dry_run=True)

            assert result.alerts_created > 0
            assert db_session.query(Alert).count() == 0

            refreshed = db_session.query(Screening).filter_by(id=screening.id).one()
            assert refreshed.core_alerts_evaluated_at is None


class TestRunPipelineLimit:
    def test_limit_caps_screenings_processed(self, client, app, setup_cinemas):
        with client.application.app_context():
            for i in range(3):
                movie = _create_movie(f"Filme {i}", f"filme-{i}")
                _create_screening(movie, "capitolio")

            result = run_pipeline(limit=2)

            assert result.screenings_evaluated == 2
            still_due = (
                db_session.query(Screening)
                .filter(Screening.core_alerts_evaluated_at.is_(None))
                .count()
            )
            assert still_due == 1
