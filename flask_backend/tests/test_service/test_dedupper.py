from datetime import date

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.scripts.dedupper import dedupper


def _cinema_id(slug):
    return get_cinema_by_slug(slug).id


class TestDedupper:
    def test_merges_duplicate_movies_across_and_within_cinemas(
        self, app, setup_cinemas
    ):
        with app.app_context():
            capitolio_id = _cinema_id("capitolio")
            sala_redencao_id = _cinema_id("sala-redencao")

            kept_movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
            kept_movie.screenings = [
                Screening(
                    cinema_id=capitolio_id,
                    description="original",
                    dates=[
                        ScreeningDate(date=date(2026, 8, 1), time="19:00"),
                    ],
                )
            ]
            db_session.add(kept_movie)
            db_session.commit()

            duplicate_movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
            duplicate_movie.screenings = [
                # same cinema as kept_movie: one date collides (exact
                # duplicate, should be skipped) and one is new (appended)
                Screening(
                    cinema_id=capitolio_id,
                    description="duplicate at same cinema",
                    dates=[
                        ScreeningDate(date=date(2026, 8, 1), time="19:00"),
                        ScreeningDate(date=date(2026, 8, 2), time="20:00"),
                    ],
                ),
                # different cinema: screening should be copied over wholesale
                Screening(
                    cinema_id=sala_redencao_id,
                    description="duplicate at different cinema",
                    dates=[
                        ScreeningDate(date=date(2026, 8, 3), time="21:00"),
                    ],
                ),
            ]
            db_session.add(duplicate_movie)
            db_session.commit()

            kept_id = kept_movie.id
            duplicate_id = duplicate_movie.id

        dedupper()

        with app.app_context():
            movies = db_session.query(Movie).filter_by(slug="filme-duplicado").all()
            assert len(movies) == 1
            assert movies[0].id == kept_id
            assert db_session.get(Movie, duplicate_id) is None

            screenings = db_session.query(Screening).filter_by(movie_id=kept_id).all()
            assert len(screenings) == 2

            capitolio_screening = next(
                s for s in screenings if s.cinema_id == capitolio_id
            )
            capitolio_dates = {(sd.date, sd.time) for sd in capitolio_screening.dates}
            assert capitolio_dates == {
                (date(2026, 8, 1), "19:00"),
                (date(2026, 8, 2), "20:00"),
            }

            sala_redencao_screening = next(
                s for s in screenings if s.cinema_id == sala_redencao_id
            )
            assert sala_redencao_screening.description == (
                "duplicate at different cinema"
            )

    def test_preserves_raw_title_and_title_cleaning_rules_when_copying_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            capitolio_id = _cinema_id("capitolio")
            sala_redencao_id = _cinema_id("sala-redencao")

            kept_movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
            kept_movie.screenings = [
                Screening(
                    cinema_id=capitolio_id,
                    description="original",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(kept_movie)
            db_session.commit()

            duplicate_movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
            duplicate_movie.screenings = [
                Screening(
                    cinema_id=sala_redencao_id,
                    description="duplicate at different cinema",
                    raw_title="Filme Duplicado (Sessão Comentada)",
                    title_cleaning_rules="sessao_comentada_suffix",
                    dates=[ScreeningDate(date=date(2026, 8, 3), time="21:00")],
                ),
            ]
            db_session.add(duplicate_movie)
            db_session.commit()

            kept_id = kept_movie.id

        dedupper()

        with app.app_context():
            copied_screening = (
                db_session.query(Screening)
                .filter_by(movie_id=kept_id, cinema_id=sala_redencao_id)
                .one()
            )
            assert copied_screening.raw_title == "Filme Duplicado (Sessão Comentada)"
            assert copied_screening.title_cleaning_rules == "sessao_comentada_suffix"

    def test_unions_title_cleaning_rules_when_merging_dates_of_existing_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            capitolio_id = _cinema_id("capitolio")

            kept_movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
            kept_movie.screenings = [
                Screening(
                    cinema_id=capitolio_id,
                    description="original",
                    raw_title=None,
                    title_cleaning_rules="sessao_strand",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(kept_movie)
            db_session.commit()

            duplicate_movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
            duplicate_movie.screenings = [
                Screening(
                    cinema_id=capitolio_id,
                    description="duplicate at same cinema",
                    raw_title="Filme Duplicado (Sessão Comentada)",
                    title_cleaning_rules="sessao_comentada_suffix",
                    dates=[ScreeningDate(date=date(2026, 8, 2), time="20:00")],
                ),
            ]
            db_session.add(duplicate_movie)
            db_session.commit()

            kept_id = kept_movie.id

        dedupper()

        with app.app_context():
            merged_screening = (
                db_session.query(Screening)
                .filter_by(movie_id=kept_id, cinema_id=capitolio_id)
                .one()
            )
            assert merged_screening.raw_title == "Filme Duplicado (Sessão Comentada)"
            assert set(merged_screening.title_cleaning_rules.split(",")) == {
                "sessao_strand",
                "sessao_comentada_suffix",
            }

    def test_no_duplicates_is_a_no_op(self, app, setup_cinemas):
        with app.app_context():
            movie = Movie(title="Filme Único", slug="filme-unico")
            movie.screenings = [
                Screening(
                    cinema_id=_cinema_id("capitolio"),
                    description="unique",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        dedupper()

        with app.app_context():
            assert db_session.query(Movie).filter_by(slug="filme-unico").count() == 1
