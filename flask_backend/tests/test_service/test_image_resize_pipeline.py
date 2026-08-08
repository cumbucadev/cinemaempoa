import io
from datetime import date
from unittest.mock import MagicMock, patch

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import (
    get_by_slug as get_cinema_by_slug,
    update as update_cinema,
)
from flask_backend.service.image_resize_pipeline import run_pipeline


def _create_screening_with_image(app, slug, image_url, width, height):
    with app.app_context():
        movie = Movie(title=slug, slug=slug)
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug("capitolio")
        screening = Screening(
            movie_id=movie.id,
            cinema_id=cinema.id,
            description="desc",
            draft=False,
            image=image_url,
            image_width=width,
            image_height=height,
        )
        db_session.add(screening)
        db_session.commit()
        db_session.add(ScreeningDate(screening_id=screening.id, date=date.today()))
        db_session.commit()
        return screening.id


class TestRunPipeline:
    def test_skips_screening_already_webp_within_bounds(self, app, setup_cinemas):
        screening_id = _create_screening_with_image(
            app, "ja-otimizada", "https://i.ibb.co/x/poster.webp", 800, 1200
        )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url"
            ) as mock_download,
            patch(
                "flask_backend.service.image_resize_pipeline.save_image"
            ) as mock_save,
        ):
            result = run_pipeline(MagicMock())

        mock_download.assert_not_called()
        mock_save.assert_not_called()
        assert result.resized == 0
        assert result.skipped_already_processed == 1
        with app.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.image == "https://i.ibb.co/x/poster.webp"

    def test_reprocesses_screening_with_non_webp_image(self, app, setup_cinemas):
        screening_id = _create_screening_with_image(
            app, "precisa-reprocessar", "https://i.ibb.co/x/poster.png", 2000, 1000
        )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url",
                return_value=(io.BytesIO(b"original-bytes"), "poster.png"),
            ) as mock_download,
            patch(
                "flask_backend.service.image_resize_pipeline.save_image",
                return_value=("https://i.ibb.co/y/poster.webp", 1200, 600),
            ) as mock_save,
        ):
            result = run_pipeline(MagicMock())

        mock_download.assert_called_once_with("https://i.ibb.co/x/poster.png")
        mock_save.assert_called_once()
        assert result.resized == 1
        assert result.skipped_already_processed == 0
        with app.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.image == "https://i.ibb.co/y/poster.webp"
            assert screening.image_width == 1200
            assert screening.image_height == 600

    def test_reprocesses_small_non_webp_image(self, app, setup_cinemas):
        screening_id = _create_screening_with_image(
            app, "pequena-nao-webp", "https://i.ibb.co/x/poster-pequeno.png", 800, 600
        )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url",
                return_value=(io.BytesIO(b"original-bytes"), "poster-pequeno.png"),
            ) as mock_download,
            patch(
                "flask_backend.service.image_resize_pipeline.save_image",
                return_value=("https://i.ibb.co/y/poster-pequeno.webp", 800, 600),
            ) as mock_save,
        ):
            result = run_pipeline(MagicMock())

        mock_download.assert_called_once_with("https://i.ibb.co/x/poster-pequeno.png")
        mock_save.assert_called_once()
        assert result.resized == 1
        assert result.skipped_already_processed == 0
        with app.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.image == "https://i.ibb.co/y/poster-pequeno.webp"

    def test_reprocesses_webp_image_over_max_dimension(self, app, setup_cinemas):
        _create_screening_with_image(
            app, "webp-grande", "https://i.ibb.co/x/poster.webp", 2400, 1200
        )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url",
                return_value=(io.BytesIO(b"original-bytes"), "poster.webp"),
            ),
            patch(
                "flask_backend.service.image_resize_pipeline.save_image",
                return_value=("https://i.ibb.co/y/poster.webp", 1200, 600),
            ) as mock_save,
        ):
            result = run_pipeline(MagicMock())

        mock_save.assert_called_once()
        assert result.resized == 1

    def test_dry_run_does_not_download_save_or_modify_db(self, app, setup_cinemas):
        screening_id = _create_screening_with_image(
            app, "dry-run-teste", "https://i.ibb.co/x/poster.png", 2000, 1000
        )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url"
            ) as mock_download,
            patch(
                "flask_backend.service.image_resize_pipeline.save_image"
            ) as mock_save,
        ):
            result = run_pipeline(MagicMock(), dry_run=True)

        mock_download.assert_not_called()
        mock_save.assert_not_called()
        assert result.processed == 1
        assert result.resized == 0
        with app.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.image == "https://i.ibb.co/x/poster.png"

    def test_download_failure_increments_errors_and_continues(self, app, setup_cinemas):
        _create_screening_with_image(
            app, "download-falha", "https://i.ibb.co/x/poster.png", 2000, 1000
        )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url",
                return_value=(None, None),
            ),
            patch(
                "flask_backend.service.image_resize_pipeline.save_image"
            ) as mock_save,
        ):
            result = run_pipeline(MagicMock())

        mock_save.assert_not_called()
        assert result.errors == 1
        assert result.resized == 0

    def test_limit_caps_number_of_items_processed(self, app, setup_cinemas):
        _create_screening_with_image(
            app, "primeira", "https://i.ibb.co/x/a.png", 2000, 1000
        )
        _create_screening_with_image(
            app, "segunda", "https://i.ibb.co/x/b.png", 2000, 1000
        )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url",
                return_value=(io.BytesIO(b"bytes"), "a.png"),
            ),
            patch(
                "flask_backend.service.image_resize_pipeline.save_image",
                return_value=("https://i.ibb.co/y/a.webp", 1200, 600),
            ),
        ):
            result = run_pipeline(MagicMock(), limit=1)

        assert result.processed == 1

    def test_reprocesses_cinema_photo(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            update_cinema(
                cinema,
                name=cinema.name,
                url=cinema.url,
                photo="https://i.ibb.co/x/capitolio.png",
                photo_width=1800,
                photo_height=1000,
            )

        with (
            app.app_context(),
            patch(
                "flask_backend.service.image_resize_pipeline.download_image_from_url",
                return_value=(io.BytesIO(b"bytes"), "capitolio.png"),
            ),
            patch(
                "flask_backend.service.image_resize_pipeline.save_image",
                return_value=("https://i.ibb.co/y/capitolio.webp", 1200, 666),
            ),
        ):
            result = run_pipeline(MagicMock())

        assert result.resized == 1
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            assert cinema.photo == "https://i.ibb.co/y/capitolio.webp"
