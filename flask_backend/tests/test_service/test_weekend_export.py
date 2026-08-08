import base64
from datetime import date
from io import BytesIO

import requests
from PIL import Image, ImageDraw

from flask_backend.service.weekend_export import (
    BG_COLOR,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    MAX_TITLE_LINES,
    CoverMovie,
    RowData,
    _available_rows_height,
    _build_poster_grid,
    _collect_cover_movies,
    _cover_crop,
    _format_weekend_date_range,
    _grid_dimensions,
    _load_poster_bytes,
    _segment_lengths,
    build_weekend_export_images,
    paginate_rows_for_day,
    render_day_image,
)


def _fake_poster_bytes(width=300, height=450, color=(200, 50, 50)):
    img = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestPaginateRowsForDay:
    def test_empty_list_returns_no_pages(self):
        assert paginate_rows_for_day([]) == []

    def test_few_short_rows_fit_on_a_single_page(self):
        rows = [RowData("Filme", "Capitólio", "20h00") for _ in range(3)]
        pages = paginate_rows_for_day(rows)
        assert len(pages) == 1
        assert sum(len(p) for p in pages) == 3

    def test_many_rows_split_into_multiple_pages(self):
        rows = [RowData(f"Filme {i}", "Capitólio", "20h00") for i in range(60)]
        pages = paginate_rows_for_day(rows)
        assert len(pages) > 1
        assert sum(len(p) for p in pages) == 60

    def test_no_page_exceeds_available_height(self):
        rows = [RowData(f"Filme {i}", "Capitólio", "20h00") for i in range(60)]
        for page in paginate_rows_for_day(rows):
            assert sum(r.height for r in page) <= _available_rows_height()

    def test_long_title_wraps_and_is_capped_at_max_lines(self):
        long_title = "Um Título De Filme Extremamente Longo " * 10
        pages = paginate_rows_for_day([RowData(long_title, "Capitólio", "20h00")])
        assert len(pages[0][0].movie_lines) <= MAX_TITLE_LINES
        assert pages[0][0].movie_lines[-1].endswith("…")


class TestRenderDayImage:
    def test_returns_valid_png_with_correct_dimensions(self):
        rows_page = paginate_rows_for_day(
            [RowData("Filme Teste", "Capitólio", "20h00")]
        )[0]
        png_bytes = render_day_image("Sexta-feira", date.today(), rows_page, 1, 1)
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        img = Image.open(BytesIO(png_bytes))
        assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)


class TestBuildWeekendExportImages:
    def test_day_with_no_screenings_has_no_images(self):
        friday, saturday, sunday = (
            date(2026, 7, 24),
            date(2026, 7, 25),
            date(2026, 7, 26),
        )
        results = build_weekend_export_images([], friday, saturday, sunday)
        assert [r.day_key for r in results] == ["friday", "saturday", "sunday"]
        assert all(r.images_base64 == [] for r in results)

    def test_returns_decodable_png_for_days_with_screenings(self, monkeypatch):
        friday, saturday, sunday = (
            date(2026, 7, 24),
            date(2026, 7, 25),
            date(2026, 7, 26),
        )

        class FakeMovie:
            title = "Filme de Sexta"

        class FakeCinema:
            name = "Cinemateca Capitólio"
            slug = "capitolio"
            short_name = "Capitólio"

        class FakeScreening:
            movie = FakeMovie()
            cinema = FakeCinema()

        class FakeScreeningDate:
            date = friday
            time = "20:00"
            screening = FakeScreening()

        results = build_weekend_export_images(
            [FakeScreeningDate()], friday, saturday, sunday
        )
        friday_result = results[0]
        assert friday_result.day_key == "friday"
        assert len(friday_result.images_base64) == 1

        png_bytes = base64.b64decode(friday_result.images_base64[0])
        img = Image.open(BytesIO(png_bytes))
        assert img.format == "PNG"

        saturday_result, sunday_result = results[1], results[2]
        assert saturday_result.images_base64 == []
        assert sunday_result.images_base64 == []


class TestFormatWeekendDateRange:
    def test_same_month_weekend(self):
        result = _format_weekend_date_range(
            date(2026, 8, 7), date(2026, 8, 8), date(2026, 8, 9)
        )
        assert result == "7, 8 e 9 de agosto"

    def test_weekend_crossing_month_boundary(self):
        result = _format_weekend_date_range(
            date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2)
        )
        assert result == "31 de julho, 1 e 2 de agosto"


class TestCollectCoverMovies:
    @staticmethod
    def _screening_date(movie_id, image):
        class FakeMovie:
            pass

        class FakeScreening:
            pass

        class FakeScreeningDate:
            pass

        FakeMovie.id = movie_id
        FakeScreening.movie = FakeMovie()
        FakeScreening.image = image
        FakeScreeningDate.screening = FakeScreening()

        return FakeScreeningDate()

    def test_skips_screenings_with_no_image(self):
        screening_dates = [self._screening_date(1, None), self._screening_date(2, "")]
        assert _collect_cover_movies(screening_dates) == []

    def test_dedupes_by_movie_id_keeping_first_image_seen(self):
        screening_dates = [
            self._screening_date(1, "/screening/assets/first.jpg"),
            self._screening_date(1, "/screening/assets/second.jpg"),
            self._screening_date(2, "/screening/assets/other.jpg"),
        ]
        result = _collect_cover_movies(screening_dates)
        assert result == [
            CoverMovie(movie_id=1, image_path="/screening/assets/first.jpg"),
            CoverMovie(movie_id=2, image_path="/screening/assets/other.jpg"),
        ]


class TestGridDimensions:
    def test_few_movies_use_three_columns(self):
        assert _grid_dimensions(3) == (3, 1)
        assert _grid_dimensions(6) == (3, 2)

    def test_mid_range_uses_four_columns(self):
        assert _grid_dimensions(7) == (4, 2)
        assert _grid_dimensions(12) == (4, 3)

    def test_many_movies_use_five_columns_capped_at_five_rows(self):
        assert _grid_dimensions(13) == (5, 3)
        assert _grid_dimensions(30) == (5, 5)


class TestSegmentLengths:
    def test_evenly_divisible_total(self):
        assert _segment_lengths(1080, 3) == [360, 360, 360]

    def test_remainder_goes_to_last_segment(self):
        assert _segment_lengths(1350, 4) == [337, 337, 337, 339]
        assert sum(_segment_lengths(1350, 4)) == 1350


class TestLoadPosterBytes:
    def test_reads_local_asset_from_upload_folder(self, tmp_path):
        (tmp_path / "poster.jpg").write_bytes(b"fake-bytes")
        result = _load_poster_bytes("/screening/assets/poster.jpg", str(tmp_path))
        assert result == b"fake-bytes"

    def test_missing_local_asset_returns_none(self, tmp_path):
        result = _load_poster_bytes("/screening/assets/missing.jpg", str(tmp_path))
        assert result is None

    def test_remote_url_is_fetched(self, monkeypatch):
        class FakeResponse:
            content = b"remote-bytes"

            def raise_for_status(self):
                pass

        def fake_get(url, timeout):
            assert url == "https://i.ibb.co/example.jpg"
            assert timeout == 10
            return FakeResponse()

        monkeypatch.setattr(requests, "get", fake_get)
        result = _load_poster_bytes("https://i.ibb.co/example.jpg", "/uploads")
        assert result == b"remote-bytes"

    def test_remote_url_failure_returns_none(self, monkeypatch):
        def fake_get(url, timeout):
            raise requests.RequestException("boom")

        monkeypatch.setattr(requests, "get", fake_get)
        result = _load_poster_bytes("https://i.ibb.co/example.jpg", "/uploads")
        assert result is None


class TestCoverCrop:
    BG = (200, 50, 50)
    STRIPE = (20, 20, 220)

    def test_wide_source_crops_horizontally_to_exact_target(self):
        img = Image.new("RGB", (400, 100), self.BG)
        result = _cover_crop(img, 200, 100)
        assert result.size == (200, 100)

    def test_tall_source_crops_vertically_to_exact_target(self):
        img = Image.new("RGB", (100, 400), self.BG)
        result = _cover_crop(img, 200, 100)
        assert result.size == (200, 100)

    def test_wide_source_crop_keeps_center_content_without_stretching(self):
        # 400x100 source is wider than the 200x100 target (2:1) ratio, so
        # _cover_crop trims the sides: crop window is x in [100, 300).
        img = Image.new("RGB", (400, 100), self.BG)
        draw = ImageDraw.Draw(img)
        # Stripe at x in [180, 220) sits fully inside the crop window; after
        # cropping (offset -100) it should land at x in [80, 120), unscaled
        # since the crop is already exactly the target size.
        draw.rectangle([180, 0, 219, 99], fill=self.STRIPE)

        result = _cover_crop(img, 200, 100)

        assert result.size == (200, 100)
        assert result.getpixel((100, 50)) == self.STRIPE
        assert result.getpixel((10, 50)) == self.BG
        assert result.getpixel((190, 50)) == self.BG

    def test_tall_source_crop_keeps_center_content_without_stretching(self):
        # 100x400 source is taller than the 200x100 target (2:1) ratio, so
        # _cover_crop trims top/bottom: crop window is y in [175, 225),
        # then the 100x50 crop is upscaled 2x in both axes to fill 200x100.
        img = Image.new("RGB", (100, 400), self.BG)
        draw = ImageDraw.Draw(img)
        # Stripe at y in [190, 210) sits fully inside the crop window; after
        # cropping (offset -175) and 2x resize it should land at y in
        # [30, 70).
        draw.rectangle([0, 190, 99, 209], fill=self.STRIPE)

        result = _cover_crop(img, 200, 100)

        assert result.size == (200, 100)
        assert result.getpixel((100, 50)) == self.STRIPE
        assert result.getpixel((100, 5)) == self.BG
        assert result.getpixel((100, 95)) == self.BG


class TestBuildPosterGrid:
    def test_renders_full_canvas_with_all_tiles_loaded(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: _fake_poster_bytes(),
        )
        tiles = [
            CoverMovie(movie_id=i, image_path=f"/screening/assets/{i}.jpg")
            for i in range(6)
        ]
        grid = _build_poster_grid(tiles, cols=3, rows=2, upload_folder="/uploads")
        assert grid.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    def test_failed_poster_load_leaves_background_without_crashing(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: None,
        )
        tiles = [CoverMovie(movie_id=1, image_path="/screening/assets/missing.jpg")]
        grid = _build_poster_grid(tiles, cols=3, rows=1, upload_folder="/uploads")
        assert grid.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
        assert grid.getpixel((10, 10)) == BG_COLOR

    def test_corrupt_poster_bytes_leaves_background_without_crashing(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: b"not a real image",
        )
        tiles = [CoverMovie(movie_id=1, image_path="/screening/assets/corrupt.jpg")]
        grid = _build_poster_grid(tiles, cols=3, rows=1, upload_folder="/uploads")
        assert grid.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
        assert grid.getpixel((10, 10)) == BG_COLOR
