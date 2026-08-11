import io
import os
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from PIL import Image

from flask_backend.db import db_session
from flask_backend.import_json import ScrappedCinema, ScrappedFeature, ScrappedResult
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.screening import (
    build_favorites_feed,
    build_reels_feed,
    download_image_from_url,
    format_day_label,
    get_image_metadata,
    get_img_filename_from_url,
    get_img_path_from_filename,
    get_soonest_date_in_range,
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


def _create_scrapped_results_with_times(cinema, slug, times):
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
                        time=times,
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

    def test_counts_new_movie_and_new_screening_on_first_import(
        self, client, app, setup_cinemas
    ):
        summary = import_scrapped_results(
            _create_scrapped_results("Capitolio", "capitolio"), app
        )

        assert summary.movies_created == 1
        assert summary.screenings_created == 1
        assert summary.dates_registered == 0

    def test_capitolio_reimporting_identical_dates_registers_no_new_dates(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(_create_scrapped_results("Capitolio", "capitolio"), app)

        summary = import_scrapped_results(
            _create_scrapped_results("Capitolio", "capitolio"), app
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 0

    def test_capitolio_changed_time_and_new_date_register_as_dates_registered(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        summary = import_scrapped_results(
            _create_scrapped_results("Capitolio", "capitolio"), app
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 1

    def test_appends_a_new_date_to_an_existing_non_capitolio_screening(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(
            _create_scrapped_results("CineBancarios", "cinebancarios"), app
        )

        summary = import_scrapped_results(
            _create_scrapped_results_with_times(
                "CineBancarios",
                "cinebancarios",
                ["2025-12-25T12:00", "2025-12-28T10:00"],
            ),
            app,
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 1

    def test_reimporting_identical_non_capitolio_payload_registers_no_new_dates(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(
            _create_scrapped_results("CineBancarios", "cinebancarios"), app
        )

        summary = import_scrapped_results(
            _create_scrapped_results("CineBancarios", "cinebancarios"), app
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 0

    def test_feature_with_no_scraped_time_never_registers_as_a_new_date(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        scrapped_results = ScrappedResult(
            cinemas=[
                ScrappedCinema(
                    url="",
                    cinema="Capitolio",
                    slug="capitolio",
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
                            time=[],
                        )
                    ],
                )
            ]
        )

        first = import_scrapped_results(scrapped_results, app)
        second = import_scrapped_results(scrapped_results, app)

        assert first.dates_registered == 0
        assert second.dates_registered == 0

    def test_two_features_for_the_same_screening_register_dates_once(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        scrapped_results = ScrappedResult(
            cinemas=[
                ScrappedCinema(
                    url="",
                    cinema="Capitolio",
                    slug="capitolio",
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
                            time=["2025-12-28T10:00"],
                        ),
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
                            time=["2025-12-29T11:00"],
                        ),
                    ],
                )
            ]
        )

        summary = import_scrapped_results(scrapped_results, app)

        assert summary.dates_registered == 1


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
        fake_file = io.BytesIO(b"original-bytes")
        fake_file.filename = "poster.png"
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.resize_for_display",
                return_value=b"webp-bytes",
            ) as mock_resize,
            patch(
                "flask_backend.service.screening.upload_image_to_local_disk",
                return_value=("local.webp", 10, 20),
            ) as mock_local,
        ):
            result = save_image(fake_file, fake_app)
        mock_resize.assert_called_once_with(b"original-bytes")
        mock_local.assert_called_once()
        assert result == ("local.webp", 10, 20)

    def test_production_env_uploads_to_api(self):
        fake_file = io.BytesIO(b"original-bytes")
        fake_file.filename = "poster.png"
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.APP_ENVIRONMENT",
                EnvironmentEnum.PRODUCTION,
            ),
            patch(
                "flask_backend.service.screening.resize_for_display",
                return_value=b"webp-bytes",
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_api",
                return_value=("https://imgbb.example/x.webp", 30, 40),
            ) as mock_api,
        ):
            result = save_image(fake_file, fake_app)
        mock_api.assert_called_once()
        assert result == ("https://imgbb.example/x.webp", 30, 40)

    def test_production_env_falls_back_to_local_on_http_error(self):
        import requests

        fake_file = io.BytesIO(b"original-bytes")
        fake_file.filename = "poster.png"
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.APP_ENVIRONMENT",
                EnvironmentEnum.PRODUCTION,
            ),
            patch(
                "flask_backend.service.screening.resize_for_display",
                return_value=b"webp-bytes",
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_api",
                side_effect=requests.exceptions.HTTPError,
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_local_disk",
                return_value=("fallback.webp", 5, 6),
            ) as mock_local,
        ):
            result = save_image(fake_file, fake_app)
        mock_local.assert_called_once()
        assert result == ("fallback.webp", 5, 6)

    def test_converts_filename_extension_to_webp_using_file_attribute(self):
        fake_file = io.BytesIO(b"original-bytes")
        fake_file.filename = "poster.png"
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.resize_for_display",
                return_value=b"webp-bytes",
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_local_disk",
                return_value=("local.webp", 10, 20),
            ) as mock_local,
        ):
            save_image(fake_file, fake_app)
        called_file, called_app, called_filename = mock_local.call_args[0]
        assert called_filename == "poster.webp"
        assert called_app is fake_app
        assert called_file.read() == b"webp-bytes"

    def test_explicit_filename_argument_overrides_file_attribute(self):
        fake_file = io.BytesIO(b"original-bytes")
        fake_file.filename = "ignored.png"
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.resize_for_display",
                return_value=b"webp-bytes",
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_local_disk",
                return_value=("local.webp", 1, 1),
            ) as mock_local,
        ):
            save_image(fake_file, fake_app, filename="explicit.jpg")
        _, _, called_filename = mock_local.call_args[0]
        assert called_filename == "explicit.webp"

    def test_filename_without_extension_still_gets_webp_suffix(self):
        fake_file = io.BytesIO(b"original-bytes")
        fake_file.filename = "no-extension"
        fake_app = MagicMock()
        with (
            patch(
                "flask_backend.service.screening.resize_for_display",
                return_value=b"webp-bytes",
            ),
            patch(
                "flask_backend.service.screening.upload_image_to_local_disk",
                return_value=("local.webp", 1, 1),
            ) as mock_local,
        ):
            save_image(fake_file, fake_app)
        _, _, called_filename = mock_local.call_args[0]
        assert called_filename == "no-extension.webp"

    def test_real_bytes_survive_full_local_disk_pipeline(self, tmp_path):
        """End-to-end (no resize_for_display/upload_image_to_local_disk
        mocking): proves real image bytes actually survive
        save_image() -> resize_for_display() -> BytesIO ->
        upload_image_to_local_disk() and land on disk as a readable webp
        file, whose dimensions match what's returned."""
        source_bytes = _make_png_bytes(width=50, height=30)
        fake_file = io.BytesIO(source_bytes)
        fake_file.filename = "poster.png"
        fake_app = MagicMock()
        fake_app.config.get.return_value = str(tmp_path)

        result_url, width, height = save_image(fake_file, fake_app)

        assert result_url.endswith(".webp")
        saved_path = tmp_path / os.path.basename(result_url)
        assert saved_path.exists()

        with Image.open(saved_path) as saved_image:
            assert saved_image.size == (width, height)


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


class TestGetSoonestDateInRange:
    def test_returns_the_earliest_date_in_range(self):
        today = date.today()
        later = ScreeningDate(date=today + timedelta(days=3), time="20:00")
        sooner = ScreeningDate(date=today + timedelta(days=1), time="18:00")

        result = get_soonest_date_in_range(
            [later, sooner], today, today + timedelta(days=6)
        )

        assert result is sooner

    def test_ignores_dates_outside_the_range(self):
        today = date.today()
        in_range = ScreeningDate(date=today + timedelta(days=1), time="18:00")
        out_of_range = ScreeningDate(date=today - timedelta(days=1), time="10:00")

        result = get_soonest_date_in_range(
            [out_of_range, in_range], today, today + timedelta(days=6)
        )

        assert result is in_range

    def test_breaks_ties_on_the_same_date_by_time(self):
        today = date.today()
        earlier_time = ScreeningDate(date=today, time="14:00")
        later_time = ScreeningDate(date=today, time="20:00")

        result = get_soonest_date_in_range(
            [later_time, earlier_time], today, today + timedelta(days=6)
        )

        assert result is earlier_time


class TestFormatDayLabel:
    def test_labels_today(self):
        today = date(2026, 7, 25)
        assert format_day_label(today, today) == "Hoje, 25/07"

    def test_labels_tomorrow(self):
        today = date(2026, 7, 25)
        assert format_day_label(today + timedelta(days=1), today) == "Amanhã, 26/07"

    def test_labels_later_days_with_weekday_name(self):
        today = date(2026, 7, 25)  # a Saturday
        # today + 4 days = 2026-07-29, a Wednesday
        assert (
            format_day_label(today + timedelta(days=4), today) == "Quarta-feira, 29/07"
        )


def _movie(title="Filme", release_year=2024):
    return Movie(title=title, release_year=release_year, directors=[])


def _cinema(slug="capitolio"):
    # short_name and color are computed properties looked up by slug from
    # CINEMA_SHORT_NAMES/CINEMA_COLORS (flask_backend/constants.py) - the
    # slug is what actually drives them, `name` here is just the fallback.
    return Cinema(slug=slug, name=slug, url="https://example.com")


def _screening(movie, cinema, dates, draft=False, screening_id=1, image=None):
    screening = Screening(
        id=screening_id,
        movie=movie,
        movie_id=1,
        cinema=cinema,
        description="Uma descrição",
        draft=draft,
        image=image,
        dates=dates,
    )
    return screening


class TestBuildReelsFeed:
    def test_orders_cards_by_each_screenings_soonest_date(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        later = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today + timedelta(days=2), time="20:00")],
            screening_id=1,
        )
        sooner = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="18:00")],
            screening_id=2,
        )

        cards = build_reels_feed(
            [later, sooner], [], today, today + timedelta(days=6), False
        )

        assert [card["screening_id"] for card in cards] == [2, 1]

    def test_excludes_draft_screenings_when_not_logged_in(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        draft = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="20:00")],
            draft=True,
            screening_id=1,
        )

        cards = build_reels_feed([draft], [], today, today + timedelta(days=6), False)

        assert cards == []

    def test_includes_draft_screenings_when_logged_in(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        draft = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="20:00")],
            draft=True,
            screening_id=1,
        )

        cards = build_reels_feed([draft], [], today, today + timedelta(days=6), True)

        assert len(cards) == 1
        assert cards[0]["draft"] is True

    def test_attaches_next_dates_for_the_cards_movie(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )
        other_cinema_date = ScreeningDate(date=today + timedelta(days=1), time="19:00")
        other_cinema_date.screening = _screening(
            movie, _cinema(slug="sala-redencao"), [], screening_id=2
        )

        cards = build_reels_feed(
            [screening],
            [other_cinema_date],
            today,
            today + timedelta(days=6),
            False,
        )

        assert len(cards[0]["next_dates"]) == 1
        assert cards[0]["next_dates"][0]["cinema_name"] == "Sala Redenção"

    def test_marks_day_label_on_every_card(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        first = _screening(
            movie, cinema, [ScreeningDate(date=today, time="18:00")], screening_id=1
        )
        second_same_day = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=2
        )
        next_day = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today + timedelta(days=1), time="18:00")],
            screening_id=3,
        )

        cards = build_reels_feed(
            [second_same_day, next_day, first],
            [],
            today,
            today + timedelta(days=6),
            False,
        )

        assert all(card["day_label"] is not None for card in cards)

    def test_skips_screenings_with_only_past_dates(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        past = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="10:00")],
            screening_id=1,
        )
        earliest = datetime(today.year, today.month, today.day, 12, 0)

        cards = build_reels_feed(
            [past],
            [],
            today,
            today + timedelta(days=6),
            False,
            earliest_datetime=earliest,
        )

        assert cards == []

    def test_keeps_screenings_with_future_dates(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        future = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="14:00")],
            screening_id=1,
        )
        earliest = datetime(today.year, today.month, today.day, 12, 0)

        cards = build_reels_feed(
            [future],
            [],
            today,
            today + timedelta(days=6),
            False,
            earliest_datetime=earliest,
        )

        assert len(cards) == 1
        assert cards[0]["soonest_time"] == "14:00"

    def test_filters_next_dates_to_future_only(self):
        today = date.today()
        movie = _movie()
        capitolio = _cinema()
        redencao = _cinema(slug="sala-redencao")
        screening = _screening(
            movie, capitolio, [ScreeningDate(date=today, time="14:00")], screening_id=1
        )
        past_other = ScreeningDate(date=today, time="10:00")
        past_other.screening = _screening(movie, redencao, [], screening_id=2)
        future_other = ScreeningDate(date=today, time="16:00")
        future_other.screening = _screening(movie, redencao, [], screening_id=3)
        earliest = datetime(today.year, today.month, today.day, 12, 0)

        cards = build_reels_feed(
            [screening],
            [past_other, future_other],
            today,
            today + timedelta(days=6),
            False,
            earliest_datetime=earliest,
        )

        assert len(cards[0]["next_dates"]) == 1
        assert cards[0]["next_dates"][0]["time"] == "16:00"

    def test_uses_soonest_future_date_for_ordering(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        earlier_future = _screening(
            movie,
            cinema,
            [
                ScreeningDate(date=today, time="10:00"),
                ScreeningDate(date=today, time="16:00"),
            ],
            screening_id=1,
        )
        later_future = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="14:00")],
            screening_id=2,
        )
        earliest = datetime(today.year, today.month, today.day, 12, 0)

        cards = build_reels_feed(
            [earlier_future, later_future],
            [],
            today,
            today + timedelta(days=6),
            False,
            earliest_datetime=earliest,
        )

        assert [card["screening_id"] for card in cards] == [2, 1]

    def test_marks_card_as_wanted_when_its_movie_id_is_in_the_set(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )

        cards = build_reels_feed(
            [screening],
            [],
            today,
            today + timedelta(days=6),
            False,
            wanted_movie_ids={1},
        )

        assert cards[0]["wanted"] is True
        assert cards[0]["movie_id"] == 1

    def test_card_not_wanted_when_its_movie_id_is_not_in_the_set(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )

        cards = build_reels_feed(
            [screening],
            [],
            today,
            today + timedelta(days=6),
            False,
            wanted_movie_ids={999},
        )

        assert cards[0]["wanted"] is False

    def test_defaults_to_not_wanted_when_no_set_given(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )

        cards = build_reels_feed(
            [screening], [], today, today + timedelta(days=6), False
        )

        assert cards[0]["wanted"] is False


class TestBuildFavoritesFeed:
    def test_returns_empty_list_for_no_movie_ids(self, app):
        with app.app_context():
            assert build_favorites_feed([], date.today(), False) == []

    def test_includes_card_for_movie_with_upcoming_screening(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            movie = Movie(title="Filme Futuro", slug="filme-futuro")
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() + timedelta(days=2),
                    time="20:00",
                )
            )
            db_session.commit()

            cards = build_favorites_feed([movie.id], date.today(), False)

            assert len(cards) == 1
            assert cards[0]["movie_title"] == "Filme Futuro"
            assert cards[0]["no_sessions"] is False
            assert cards[0]["wanted"] is True

    def test_falls_back_to_latest_screening_when_no_upcoming_dates(
        self, app, setup_cinemas
    ):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            movie = Movie(title="Filme Antigo", slug="filme-antigo")
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                image="poster.jpg",
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() - timedelta(days=10),
                    time="20:00",
                )
            )
            db_session.commit()

            cards = build_favorites_feed([movie.id], date.today(), False)

            assert len(cards) == 1
            assert cards[0]["movie_title"] == "Filme Antigo"
            assert cards[0]["no_sessions"] is True
            assert cards[0]["soonest_date"] is None
            assert cards[0]["image"] == "poster.jpg"

    def test_excludes_draft_fallback_when_not_logged_in(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            movie = Movie(title="Filme Rascunho", slug="filme-rascunho")
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=True
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() - timedelta(days=10),
                    time="20:00",
                )
            )
            db_session.commit()

            cards = build_favorites_feed([movie.id], date.today(), False)

            assert cards == []

    def test_falls_back_to_newest_non_draft_screening_when_newest_is_a_draft(
        self, app, setup_cinemas
    ):
        # an older non-draft screening plus a newer draft screening (e.g.
        # a re-scrape that hasn't been published yet) must not make the
        # movie disappear from an anonymous visitor's /favoritos - the
        # stale-pick fallback should skip the draft and use the older
        # published screening instead.
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            movie = Movie(title="Filme Rascunho Mais Novo", slug="filme-rascunho-novo")
            db_session.add(movie)
            db_session.commit()
            older_non_draft = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="publicado antigo",
                draft=False,
                image="antigo.jpg",
                created_at=datetime.now() - timedelta(days=10),
            )
            newer_draft = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="rascunho recente",
                draft=True,
                image="rascunho.jpg",
                created_at=datetime.now(),
            )
            db_session.add_all([older_non_draft, newer_draft])
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=older_non_draft.id,
                    date=date.today() - timedelta(days=5),
                    time="20:00",
                )
            )
            db_session.add(
                ScreeningDate(
                    screening_id=newer_draft.id,
                    date=date.today() - timedelta(days=1),
                    time="20:00",
                )
            )
            db_session.commit()

            cards = build_favorites_feed([movie.id], date.today(), False)

            assert len(cards) == 1
            assert cards[0]["no_sessions"] is True
            assert cards[0]["image"] == "antigo.jpg"
            assert cards[0]["draft"] is False


class TestImportScrappedResultsTitleCollisions:
    def test_attaches_to_the_disambiguated_sibling_with_a_matching_cinema_screening(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            base = Movie(
                title="Noite",
                slug="noite",
                screenings=[
                    Screening(
                        cinema_id=1,  # capitolio
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-01"), time="19:00")
                        ],
                    )
                ],
            )
            sibling = Movie(
                title="Noite",
                slug="noite-2",
                screenings=[
                    Screening(
                        cinema_id=2,  # sala-redencao
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-02"), time="21:00")
                        ],
                    )
                ],
            )
            db_session.add_all([base, sibling])
            db_session.commit()
            base_id, sibling_id = base.id, sibling.id

        summary = import_scrapped_results(
            _create_scrapped_results_with_title(
                "Sala Redenção", "sala-redencao", "Noite"
            ),
            app,
        )

        assert summary.movies_created == 0
        assert summary.ambiguous_collisions == []
        with client.application.app_context():
            sibling_screenings = (
                db_session.query(Screening).filter_by(movie_id=sibling_id).all()
            )
            assert len(sibling_screenings) == 1
            base_screenings = (
                db_session.query(Screening).filter_by(movie_id=base_id).all()
            )
            assert len(base_screenings) == 1

    def test_flags_ambiguous_collision_when_no_sibling_matches_the_cinema(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            base = Movie(
                title="Noite",
                slug="noite",
                screenings=[
                    Screening(
                        cinema_id=1,  # capitolio
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-01"), time="19:00")
                        ],
                    )
                ],
            )
            sibling = Movie(title="Noite", slug="noite-2")
            db_session.add_all([base, sibling])
            db_session.commit()
            base_id, sibling_id = base.id, sibling.id

        summary = import_scrapped_results(
            _create_scrapped_results_with_title(
                "Paulo Amorim", "paulo-amorim", "Noite"
            ),
            app,
        )

        assert len(summary.ambiguous_collisions) == 1
        collision = summary.ambiguous_collisions[0]
        assert collision["attached_movie_id"] == base_id
        assert set(collision["candidate_movie_ids"]) == {base_id, sibling_id}
        assert collision["cinema"] == "paulo-amorim"
        with client.application.app_context():
            screening = db_session.get(Screening, collision["screening_id"])
            assert screening.movie_id == base_id

    def test_flags_ambiguous_collision_on_the_update_branch(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            base = Movie(
                title="Noite",
                slug="noite",
                screenings=[
                    Screening(
                        cinema_id=1,  # capitolio
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-01"), time="19:00")
                        ],
                    )
                ],
            )
            sibling = Movie(
                title="Noite",
                slug="noite-2",
                screenings=[
                    Screening(
                        cinema_id=1,  # capitolio: same cinema as base's screening
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-02"), time="21:00")
                        ],
                    )
                ],
            )
            db_session.add_all([base, sibling])
            db_session.commit()
            base_id, sibling_id = base.id, sibling.id
            existing_screening_id = base.screenings[0].id

        summary = import_scrapped_results(
            _create_scrapped_results_with_title("Capitólio", "capitolio", "Noite"),
            app,
        )

        assert summary.screenings_created == 0
        assert len(summary.ambiguous_collisions) == 1
        collision = summary.ambiguous_collisions[0]
        assert collision["screening_id"] == existing_screening_id
        assert collision["attached_movie_id"] == base_id
        assert set(collision["candidate_movie_ids"]) == {base_id, sibling_id}
        assert collision["cinema"] == "capitolio"
        with client.application.app_context():
            base_screenings = (
                db_session.query(Screening).filter_by(movie_id=base_id).all()
            )
            assert len(base_screenings) == 1
