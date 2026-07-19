import io
from datetime import datetime
from unittest.mock import MagicMock, patch

from PIL import Image

from flask_backend.db import db_session
from flask_backend.import_json import ScrappedCinema, ScrappedFeature, ScrappedResult
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.service.screening import (
    download_image_from_url,
    get_image_metadata,
    get_img_filename_from_url,
    get_img_path_from_filename,
    import_scrapped_results,
    save_image,
    validate_image,
)
from flask_backend.utils.enums.environment import EnvironmentEnum


def _make_png_bytes(width=10, height=20):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color="blue").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


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


def _create_scrapped_results_with_title(cinema, slug, title):
    return ScrappedResult(
        cinemas=[
            ScrappedCinema(
                url="",
                cinema=cinema,
                slug=slug,
                features=[
                    ScrappedFeature(
                        title=title,
                        excerpt="cool film",
                        poster="",
                        original_title="",
                        price="",
                        director="",
                        classification="",
                        general_info="",
                        read_more="",
                        time=["2025-12-25T12:00"],
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

    def test_scrapped_title_is_cleaned_before_creating_movie(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(
            _create_scrapped_results_with_title(
                "Capitolio", "capitolio", "Cinema | Lobo e Cão"
            ),
            app,
        )

        with client.application.app_context():
            movie = db_session.query(Movie).filter_by(slug="lobo-e-cao").one()
            assert movie.title == "Lobo e Cão"

    def test_populates_raw_title_and_title_cleaning_rules_on_create(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(
            _create_scrapped_results_with_title(
                "Capitolio", "capitolio", "Cinema | Lobo e Cão + debate"
            ),
            app,
        )

        with client.application.app_context():
            movie = db_session.query(Movie).filter_by(slug="lobo-e-cao").one()
            screening = movie.screenings[0]
            assert screening.raw_title == "Cinema | Lobo e Cão + debate"
            matched = set(screening.title_cleaning_rules.split(","))
            assert "cinema_pipe" in matched
            assert "debate_suffix" in matched

    def test_unions_title_cleaning_rules_across_imports_without_dropping_old(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(
            _create_scrapped_results_with_title(
                "CineBancarios", "cinebancarios", "Cinema | Lobo e Cão"
            ),
            app,
        )
        import_scrapped_results(
            _create_scrapped_results_with_title(
                "CineBancarios", "cinebancarios", "Lobo e Cão + debate"
            ),
            app,
        )

        with client.application.app_context():
            movie = db_session.query(Movie).filter_by(slug="lobo-e-cao").one()
            screening = movie.screenings[0]
            matched = set(screening.title_cleaning_rules.split(","))
            assert "cinema_pipe" in matched
            assert "debate_suffix" in matched
            assert screening.raw_title == "Lobo e Cão + debate"

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


class _FakeUpload:
    def __init__(self, filename, content: bytes):
        self.filename = filename
        self.stream = io.BytesIO(content)


class TestValidateImage:
    def test_invalid_extension_returns_error(self):
        upload = _FakeUpload("document.pdf", b"whatever")
        is_valid, message = validate_image(upload)
        assert is_valid is False
        assert "Extensão do arquivo inválida" in message

    def test_valid_extension_but_corrupted_content_returns_error(self):
        upload = _FakeUpload("poster.png", b"not-actually-an-image")
        is_valid, message = validate_image(upload)
        assert is_valid is False
        assert message == "Arquivo corrompido ou inválido."

    def test_valid_image_returns_true(self):
        upload = _FakeUpload("poster.png", _make_png_bytes())
        is_valid, message = validate_image(upload)
        assert is_valid is True
        assert message is None


class TestSaveImage:
    def test_development_env_saves_locally(self):
        fake_file = MagicMock()
        fake_app = MagicMock()
        with patch(
            "flask_backend.service.screening.upload_image_to_local_disk",
            return_value=("local.png", 10, 20),
        ) as mock_local:
            result = save_image(fake_file, fake_app)
        mock_local.assert_called_once()
        assert result == ("local.png", 10, 20)

    def test_production_env_uploads_to_api(self):
        fake_file = MagicMock()
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.APP_ENVIRONMENT",
                EnvironmentEnum.PRODUCTION,
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_api",
                return_value=("https://imgbb.example/x.png", 30, 40),
            ) as mock_api,
        ):
            result = save_image(fake_file, fake_app)
        mock_api.assert_called_once()
        assert result == ("https://imgbb.example/x.png", 30, 40)

    def test_production_env_falls_back_to_local_on_http_error(self):
        import requests

        fake_file = MagicMock()
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.APP_ENVIRONMENT",
                EnvironmentEnum.PRODUCTION,
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_api",
                side_effect=requests.exceptions.HTTPError,
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_local_disk",
                return_value=("fallback.png", 5, 6),
            ) as mock_local,
        ):
            result = save_image(fake_file, fake_app)
        mock_local.assert_called_once()
        assert result == ("fallback.png", 5, 6)


class TestDownloadImageFromUrl:
    def test_none_url_returns_none_none(self):
        assert download_image_from_url(None) == (None, None)

    def test_not_ok_response_returns_none_none(self):
        mock_response = MagicMock(ok=False)
        with patch(
            "flask_backend.service.screening.requests.Session"
        ) as mock_session_cls:
            mock_session_cls.return_value.get.return_value = mock_response
            result = download_image_from_url("https://example.com/poster.jpg")
        assert result == (None, None)

    def test_valid_image_returns_bytes_and_filename(self):
        mock_response = MagicMock(ok=True, content=_make_png_bytes())
        with patch(
            "flask_backend.service.screening.requests.Session"
        ) as mock_session_cls:
            mock_session_cls.return_value.get.return_value = mock_response
            image_bytes, filename = download_image_from_url(
                "https://example.com/poster.jpg"
            )
        assert image_bytes is not None
        assert filename.endswith(".jpg")

    def test_corrupted_content_returns_none_none(self):
        mock_response = MagicMock(ok=True, content=b"not-an-image")
        with patch(
            "flask_backend.service.screening.requests.Session"
        ) as mock_session_cls:
            mock_session_cls.return_value.get.return_value = mock_response
            result = download_image_from_url("https://example.com/poster.jpg")
        assert result == (None, None)


class TestImportScrappedResultsExtraBranches:
    def test_description_includes_all_optional_fields(self, client, app, setup_cinemas):
        scrapped_results = ScrappedResult(
            cinemas=[
                ScrappedCinema(
                    url="",
                    cinema="Capitolio",
                    slug="capitolio",
                    features=[
                        ScrappedFeature(
                            title="Filme Completo",
                            excerpt="Um belo resumo",
                            poster="",
                            original_title="Original Title",
                            price="R$ 20",
                            director="Fulano de Tal",
                            classification="16 anos",
                            general_info="Brasil / 2024 / 100 min",
                            read_more="",
                            time=["2026-08-01T19:00"],
                        )
                    ],
                )
            ]
        )
        import_scrapped_results(scrapped_results, app)
        with client.application.app_context():
            movie = db_session.query(Movie).filter_by(title="Filme Completo").one()
            screening = movie.screenings[0]
            assert "Original Title" in screening.description
            assert "R$ 20" in screening.description
            assert "Fulano de Tal" in screening.description
            assert "16 anos" in screening.description
            assert "Brasil / 2024 / 100 min" in screening.description
            assert "Um belo resumo" in screening.description

    def test_downloads_and_saves_poster_for_new_screening(
        self, client, app, setup_cinemas
    ):
        scrapped_results = ScrappedResult(
            cinemas=[
                ScrappedCinema(
                    url="",
                    cinema="Capitolio",
                    slug="capitolio",
                    features=[
                        ScrappedFeature(
                            title="Filme Com Poster",
                            excerpt="excerto",
                            poster="https://example.com/poster.jpg",
                            original_title="",
                            price="",
                            director="",
                            classification="",
                            general_info="",
                            read_more="",
                            time=["2026-08-01T19:00"],
                        )
                    ],
                )
            ]
        )
        with (
            patch(
                "flask_backend.service.screening.download_image_from_url",
                return_value=(io.BytesIO(_make_png_bytes()), "hash.jpg"),
            ),
            patch(
                "flask_backend.service.screening.save_image",
                return_value=("uploaded-poster.jpg", 50, 60),
            ) as mock_save,
        ):
            import_scrapped_results(scrapped_results, app)

        mock_save.assert_called_once()
        with client.application.app_context():
            movie = db_session.query(Movie).filter_by(title="Filme Com Poster").one()
            screening = movie.screenings[0]
            assert screening.image == "uploaded-poster.jpg"
            assert screening.image_width == 50
            assert screening.image_height == 60

    def test_skips_appending_exact_duplicate_date(self, client, app, setup_cinemas):
        with client.application.app_context():
            from flask_backend.repository.cinemas import get_by_slug

            sala_redencao = get_by_slug("sala-redencao")
            movie = Movie(title="Duplicado", slug="duplicado")
            movie.screenings = [
                Screening(
                    cinema_id=sala_redencao.id,
                    description="cool film",
                    dates=[ScreeningDate(date=_get_date("2025-12-25"), time="11:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        scrapped_results = ScrappedResult(
            cinemas=[
                ScrappedCinema(
                    url="",
                    cinema="Sala Redenção",
                    slug="sala-redencao",
                    features=[
                        ScrappedFeature(
                            title="Duplicado",
                            excerpt="cool film",
                            poster="",
                            original_title="",
                            price="",
                            director="",
                            classification="",
                            general_info="",
                            read_more="",
                            time=["2025-12-25T11:00"],
                        )
                    ],
                )
            ]
        )
        import_scrapped_results(scrapped_results, app)

        with client.application.app_context():
            dates = db_session.query(ScreeningDate).all()
            assert len(dates) == 1, "duplicate date/time should not be appended twice"


class TestImgFilenameHelpers:
    def test_get_img_filename_from_url_returns_input_extension(self):
        filename = get_img_filename_from_url("https://example.com/poster.jpg")
        assert filename.endswith(".jpg")

    def test_get_img_path_from_filename_returns_none_when_missing(self, tmp_path):
        fake_app = MagicMock()
        fake_app.config.get.return_value = str(tmp_path)
        assert get_img_path_from_filename("does-not-exist.jpg", fake_app) is None

    def test_get_img_path_from_filename_returns_path_when_present(self, tmp_path):
        (tmp_path / "existing.jpg").write_bytes(_make_png_bytes())
        fake_app = MagicMock()
        fake_app.config.get.return_value = str(tmp_path)
        path = get_img_path_from_filename("existing.jpg", fake_app)
        assert path is not None

    def test_get_image_metadata_returns_dimensions(self, tmp_path):
        img_path = tmp_path / "poster.png"
        img_path.write_bytes(_make_png_bytes(width=42, height=24))
        width, height = get_image_metadata(str(img_path))
        assert (width, height) == (42, 24)


class TestImportScrappedResultsWithoutScrapedTime:
    def test_defaults_to_current_time_when_no_time_scraped(
        self, client, app, setup_cinemas
    ):
        scrapped_results = ScrappedResult(
            cinemas=[
                ScrappedCinema(
                    url="",
                    cinema="Capitolio",
                    slug="capitolio",
                    features=[
                        ScrappedFeature(
                            title="Filme Sem Horario",
                            excerpt="excerto",
                            poster="",
                            original_title="",
                            price="",
                            director="",
                            classification="",
                            general_info="",
                            read_more="",
                            time=None,
                        )
                    ],
                )
            ]
        )
        import_scrapped_results(scrapped_results, app)
        with client.application.app_context():
            movie = db_session.query(Movie).filter_by(title="Filme Sem Horario").one()
            screening = movie.screenings[0]
            assert len(screening.dates) == 1
