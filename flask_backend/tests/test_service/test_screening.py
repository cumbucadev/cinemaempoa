from datetime import datetime

from flask_backend.db import db_session
from flask_backend.import_json import ScrappedCinema, ScrappedFeature, ScrappedResult
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.service.screening import import_scrapped_results


def _get_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _create_scrapped_results(cinema, slug):
    return ScrappedResult(
        cinemas=[
            ScrappedCinema(
                url="",
                cinema=cinema,
                slug=slug,
                features=[
                    ScrappedFeature(
                        title="Lobo e Cão",
                        excerpt="cool film",
                        poster="",
                        original_title="",
                        price="",
                        director="",
                        classification="",
                        general_info="",
                        read_more="",
                        time=["2025-12-25T12:00", "2025-12-27T14:00"],
                    )
                ],
            )
        ]
    )


def _create_movie_on_db(db_session):
    movie = Movie(
        title="Lobo e Cão",
        slug="lobo-e-cao",
        screenings=[
            Screening(
                cinema_id=1,  # should be capitolio
                description="cool film",
                dates=[
                    ScreeningDate(date=_get_date("2025-12-25"), time="11:00"),
                    ScreeningDate(date=_get_date("2025-12-26"), time="13:00"),
                ],
            )
        ],
    )
    db_session.add(movie)
    db_session.commit()


class TestImportScrappedResults:
    def test_capitolio_overwrites_existing_records_for_each_day(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        import_scrapped_results(_create_scrapped_results("Capitolio", "capitolio"), app)

        with client.application.app_context():
            dates = db_session.query(ScreeningDate).all()
            assert len(dates) == 3, "Invalid quantity of dates"

            first_date = [x for x in dates if x.date == _get_date("2025-12-25")]
            assert (
                len(first_date) == 1
            ), "screening date for the 25th should be overwritten"
            assert (
                first_date[0].time == "12:00"
            ), "screening date for the 25th should be overwritten"

            second_date = next(
                (x for x in dates if x.date == _get_date("2025-12-26")), None
            )
            assert (
                second_date is not None
            ), "dates not present in the import should be kept as is"
            assert (
                second_date.time == "13:00"
            ), "dates not present in the import should be kept as is"

            third_date = next(
                (x for x in dates if x.date == _get_date("2025-12-27")), None
            )
            assert third_date is not None, "new dates should be added"
            assert third_date.time == "14:00", "error adding new date"

    def test_cinebancario_appends_to_existing_records_for_each_day(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        import_scrapped_results(
            _create_scrapped_results("CineBancarios", "cinebancarios"), app
        )

        with client.application.app_context():
            dates = db_session.query(ScreeningDate).all()
            assert len(dates) == 4, "Invalid quantity of dates"

            first_date = [x for x in dates if x.date == _get_date("2025-12-25")]
            assert (
                len(first_date) == 2
            ), "screening date for the 25th should not be overwritten"
            assert (
                first_date[0].time == "11:00"
            ), "screening date for the 25th should not be overwritten"
            assert (
                first_date[1].time == "12:00"
            ), "screening date for the 25th should not be overwritten"

            second_date = next(
                (x for x in dates if x.date == _get_date("2025-12-26")), None
            )
            assert (
                second_date is not None
            ), "dates not present in the import should be kept as is"
            assert (
                second_date.time == "13:00"
            ), "dates not present in the import should be kept as is"

            third_date = next(
                (x for x in dates if x.date == _get_date("2025-12-27")), None
            )
            assert third_date is not None, "new dates should be added"
            assert third_date.time == "14:00", "error adding new date"

    def test_paulo_amorim_appends_to_existing_records_for_each_day(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        import_scrapped_results(
            _create_scrapped_results("Paulo Amorim", "paulo-amorim"), app
        )

        with client.application.app_context():
            dates = db_session.query(ScreeningDate).all()
            assert len(dates) == 4, "Invalid quantity of dates"

            first_date = [x for x in dates if x.date == _get_date("2025-12-25")]
            assert (
                len(first_date) == 2
            ), "screening date for the 25th should not be overwritten"
            assert (
                first_date[0].time == "11:00"
            ), "screening date for the 25th should not be overwritten"
            assert (
                first_date[1].time == "12:00"
            ), "screening date for the 25th should not be overwritten"

            second_date = next(
                (x for x in dates if x.date == _get_date("2025-12-26")), None
            )
            assert (
                second_date is not None
            ), "dates not present in the import should be kept as is"
            assert (
                second_date.time == "13:00"
            ), "dates not present in the import should be kept as is"

            third_date = next(
                (x for x in dates if x.date == _get_date("2025-12-27")), None
            )
            assert third_date is not None, "new dates should be added"
            assert third_date.time == "14:00", "error adding new date"

    def test_sala_redencao_appends_to_existing_records_for_each_day(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        import_scrapped_results(
            _create_scrapped_results("Sala Redenção", "sala-redencao"), app
        )

        with client.application.app_context():
            dates = db_session.query(ScreeningDate).all()
            assert len(dates) == 4, "Invalid quantity of dates"

            first_date = [x for x in dates if x.date == _get_date("2025-12-25")]
            assert (
                len(first_date) == 2
            ), "screening date for the 25th should not be overwritten"
            assert (
                first_date[0].time == "11:00"
            ), "screening date for the 25th should not be overwritten"
            assert (
                first_date[1].time == "12:00"
            ), "screening date for the 25th should not be overwritten"

            second_date = next(
                (x for x in dates if x.date == _get_date("2025-12-26")), None
            )
            assert (
                second_date is not None
            ), "dates not present in the import should be kept as is"
            assert (
                second_date.time == "13:00"
            ), "dates not present in the import should be kept as is"

            third_date = next(
                (x for x in dates if x.date == _get_date("2025-12-27")), None
            )
            assert third_date is not None, "new dates should be added"
            assert third_date.time == "14:00", "error adding new date"
