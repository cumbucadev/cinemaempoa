import base64
import time
from datetime import date
from io import BytesIO

import requests
from PIL import Image, ImageDraw

from flask_backend.service import weekend_export
from flask_backend.service.weekend_export import (
    BG_COLOR,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    COVER_BG_COLOR,
    COVER_TITLE_TEXT,
    FONT_BOLD_PATH,
    FONT_REGULAR_PATH,
    FONT_SIZE_COVER_SUBTITLE,
    FONT_SIZE_COVER_TITLE,
    MARGIN_TOP,
    MARGIN_X,
    MAX_COVER_TILES,
    MAX_TITLE_LINES,
    POSTER_LOAD_TIMEOUT_SECONDS,
    CoverMovie,
    RowData,
    _available_rows_height,
    _collect_cover_movies,
    _compose_poster_grid,
    _cover_crop,
    _distribute_counts,
    _format_day_header,
    _format_weekend_date_range,
    _grid_dimensions,
    _line_height,
    _load_cover_posters,
    _load_font,
    _load_poster_bytes,
    _segment_lengths,
    _wrap_text_to_width,
    build_weekend_cover_image,
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


class TestFormatDayHeader:
    def test_combines_day_label_and_short_date(self):
        assert (
            _format_day_header("Sexta-feira", date(2026, 8, 8)) == "Sexta-feira, 08/08"
        )

    def test_does_not_include_year(self):
        assert "2026" not in _format_day_header("Domingo", date(2026, 8, 9))


def _top_right_corner_has_ink(img):
    """Samples the top-right margin band (where the part indicator would
    be drawn) and returns True if any pixel there isn't the plain
    background color - i.e. something was actually drawn there."""
    top = MARGIN_TOP - 10
    bottom = MARGIN_TOP + 50
    left = CANVAS_WIDTH - 200
    right = CANVAS_WIDTH - MARGIN_X
    return any(
        img.getpixel((x, y)) != BG_COLOR
        for y in range(top, bottom)
        for x in range(left, right)
    )


class TestRenderDayImage:
    def test_returns_valid_png_with_correct_dimensions(self):
        rows_page = paginate_rows_for_day(
            [RowData("Filme Teste", "Capitólio", "20h00")]
        )[0]
        png_bytes = render_day_image("Sexta-feira", date.today(), rows_page, 1, 1)
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        img = Image.open(BytesIO(png_bytes))
        assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    def test_single_part_draws_no_corner_indicator(self):
        rows_page = paginate_rows_for_day(
            [RowData("Filme Teste", "Capitólio", "20h00")]
        )[0]
        png_bytes = render_day_image("Sexta-feira", date.today(), rows_page, 1, 1)
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        assert not _top_right_corner_has_ink(img)

    def test_multi_part_draws_corner_indicator(self):
        rows_page = paginate_rows_for_day(
            [RowData("Filme Teste", "Capitólio", "20h00")]
        )[0]
        png_bytes = render_day_image("Sexta-feira", date.today(), rows_page, 1, 2)
        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        assert _top_right_corner_has_ink(img)


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
    def test_exact_multiples_fill_every_row(self):
        assert _grid_dimensions(3) == [3]
        assert _grid_dimensions(6) == [3, 3]
        assert _grid_dimensions(12) == [4, 4, 4]

    def test_single_movie_fills_entire_canvas(self):
        assert _grid_dimensions(1) == [1]

    def test_incomplete_row_is_redistributed_instead_of_left_blank(self):
        # 7 movies at the 4-column tier would leave 1 blank cell under a
        # fixed-column grid; instead tiles spread across rows as evenly as
        # possible so every row is exactly full (row 2 gets bigger tiles).
        assert _grid_dimensions(7) == [4, 3]
        assert sum(_grid_dimensions(7)) == 7

        # 13 movies at the 5-column tier would leave 2 blank cells in the
        # last row under a fixed-column grid.
        assert _grid_dimensions(13) == [5, 4, 4]
        assert sum(_grid_dimensions(13)) == 13

    def test_many_movies_capped_at_five_rows(self):
        assert _grid_dimensions(30) == [5, 5, 5, 5, 5]


class TestDistributeCounts:
    def test_evenly_divisible_total(self):
        assert _distribute_counts(6, 2) == [3, 3]

    def test_remainder_front_loaded_onto_leading_buckets(self):
        assert _distribute_counts(7, 2) == [4, 3]
        assert _distribute_counts(13, 3) == [5, 4, 4]

    def test_single_bucket_returns_total(self):
        assert _distribute_counts(1, 1) == [1]


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
            assert timeout == POSTER_LOAD_TIMEOUT_SECONDS
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


class TestLoadCoverPosters:
    def test_loads_all_movies_within_budget(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: _fake_poster_bytes(),
        )
        movies = [
            CoverMovie(movie_id=i, image_path=f"/screening/assets/{i}.jpg")
            for i in range(6)
        ]
        posters = _load_cover_posters(movies, upload_folder="/uploads")
        assert len(posters) == 6
        assert all(isinstance(p, Image.Image) for p in posters)

    def test_failed_poster_load_is_skipped_not_counted(self, monkeypatch):
        def fake_load(image_path, _upload_folder):
            return None if image_path.endswith("1.jpg") else _fake_poster_bytes()

        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes", fake_load
        )
        movies = [
            CoverMovie(movie_id=i, image_path=f"/screening/assets/{i}.jpg")
            for i in range(3)
        ]
        posters = _load_cover_posters(movies, upload_folder="/uploads")
        assert len(posters) == 2

    def test_corrupt_poster_bytes_is_skipped_not_counted(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: b"not a real image",
        )
        movies = [CoverMovie(movie_id=1, image_path="/screening/assets/corrupt.jpg")]
        posters = _load_cover_posters(movies, upload_folder="/uploads")
        assert posters == []

    def test_reaches_success_cap_by_drawing_from_the_full_candidate_list(
        self, monkeypatch
    ):
        """The first batch of candidates (more than MAX_COVER_TILES of them)
        all fail; only candidates past that batch succeed. The loader must
        keep drawing from the full movie list - not just a pre-truncated
        first MAX_COVER_TILES - to still reach the success cap."""
        failing_batch_size = MAX_COVER_TILES + 5

        def fake_load(image_path, _upload_folder):
            index = int(image_path.rsplit("/", 1)[-1].split(".")[0])
            if index < failing_batch_size:
                return None
            return _fake_poster_bytes()

        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes", fake_load
        )
        movies = [
            CoverMovie(movie_id=i, image_path=f"/screening/assets/{i}.jpg")
            for i in range(failing_batch_size + MAX_COVER_TILES)
        ]
        posters = _load_cover_posters(movies, upload_folder="/uploads")
        assert len(posters) == MAX_COVER_TILES

    def test_poster_load_budget_returns_whatever_completed_in_time(self, monkeypatch):
        """Once the wall-clock budget for the poster-loading pass is
        exceeded, the loader must stop waiting and return whichever posters
        already finished - proving a slow/hanging image host can't pin the
        whole call indefinitely."""
        monkeypatch.setattr(weekend_export, "COVER_POSTER_LOAD_BUDGET_SECONDS", 0.2)

        def fake_load(image_path, _upload_folder):
            if image_path.endswith("hangs.jpg"):
                time.sleep(2)
            return _fake_poster_bytes()

        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes", fake_load
        )

        movies = [
            CoverMovie(movie_id=0, image_path="/screening/assets/fast.jpg"),
            CoverMovie(movie_id=1, image_path="/screening/assets/hangs.jpg"),
        ]
        posters = _load_cover_posters(movies, upload_folder="/uploads")

        assert len(posters) == 1


class TestComposePosterGrid:
    @staticmethod
    def _solid_posters(count, color=(200, 50, 50)):
        return [Image.new("RGB", (300, 450), color) for _ in range(count)]

    def test_renders_full_canvas(self):
        grid = _compose_poster_grid(self._solid_posters(6), row_counts=[3, 3])
        assert grid.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    def test_uneven_row_counts_leave_no_blank_cell(self):
        """A row with fewer tiles than another must still be fully covered
        by (bigger) tiles - proving the justified-row layout leaves no
        background-colored gap anywhere on the canvas, unlike the old
        fixed-column grid which left incomplete rows partially blank."""
        grid = _compose_poster_grid(self._solid_posters(7), row_counts=[4, 3])
        assert grid.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
        for x in range(0, CANVAS_WIDTH, 10):
            for y in range(0, CANVAS_HEIGHT, 10):
                assert grid.getpixel((x, y)) != COVER_BG_COLOR


class TestBuildWeekendCoverImage:
    FRIDAY, SATURDAY, SUNDAY = date(2026, 8, 7), date(2026, 8, 8), date(2026, 8, 9)

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

    def test_returns_none_when_no_movie_has_a_poster(self):
        screening_dates = [self._screening_date(1, None)]
        result = build_weekend_cover_image(
            screening_dates, "/uploads", self.FRIDAY, self.SATURDAY, self.SUNDAY
        )
        assert result is None

    def test_returns_none_when_every_poster_fails_to_load(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: None,
        )
        screening_dates = [self._screening_date(1, "/screening/assets/missing.jpg")]
        result = build_weekend_cover_image(
            screening_dates, "/uploads", self.FRIDAY, self.SATURDAY, self.SUNDAY
        )
        assert result is None

    def test_grid_size_adapts_to_loaded_posters_not_movie_count(self, monkeypatch):
        """13 candidate movies would normally pick the 5-column tier, but
        if only 8 posters actually load, the grid must be sized for 8 (a
        full 4x2 layout) rather than for 13 (a 5-column grid with blank
        cells for the movies whose poster never loaded)."""

        def fake_load(image_path, _upload_folder):
            movie_num = int(image_path.rsplit("/", 1)[-1].split(".")[0])
            return None if movie_num >= 8 else _fake_poster_bytes()

        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes", fake_load
        )

        captured = {}
        original_compose = weekend_export._compose_poster_grid

        def spy_compose(posters, row_counts):
            captured["poster_count"] = len(posters)
            captured["row_counts"] = row_counts
            return original_compose(posters, row_counts)

        monkeypatch.setattr(
            "flask_backend.service.weekend_export._compose_poster_grid", spy_compose
        )

        screening_dates = [
            self._screening_date(i, f"/screening/assets/{i}.jpg") for i in range(13)
        ]
        result = build_weekend_cover_image(
            screening_dates, "/uploads", self.FRIDAY, self.SATURDAY, self.SUNDAY
        )

        assert result is not None
        assert captured["poster_count"] == 8
        assert captured["row_counts"] == [4, 4]

    def test_returns_decodable_png_at_canvas_size(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: _fake_poster_bytes(),
        )
        screening_dates = [
            self._screening_date(1, "/screening/assets/1.jpg"),
            self._screening_date(2, "/screening/assets/2.jpg"),
            self._screening_date(3, "/screening/assets/3.jpg"),
        ]
        result = build_weekend_cover_image(
            screening_dates, "/uploads", self.FRIDAY, self.SATURDAY, self.SUNDAY
        )
        assert result is not None
        png_bytes = base64.b64decode(result)
        img = Image.open(BytesIO(png_bytes))
        assert img.format == "PNG"
        assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    def test_title_text_is_actually_drawn_near_white(self, monkeypatch):
        """A near-white pixel must exist in the title text's band -
        catches a regression where the title were drawn in the background
        color (invisible) instead of white."""
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: _fake_poster_bytes(color=(200, 50, 50)),
        )
        screening_dates = [
            self._screening_date(1, "/screening/assets/1.jpg"),
            self._screening_date(2, "/screening/assets/2.jpg"),
            self._screening_date(3, "/screening/assets/3.jpg"),
        ]
        result = build_weekend_cover_image(
            screening_dates, "/uploads", self.FRIDAY, self.SATURDAY, self.SUNDAY
        )
        img = Image.open(BytesIO(base64.b64decode(result))).convert("RGB")

        # Replicate the title block's vertical placement using the same
        # private helpers _draw_cover_text uses, so the sampled strip
        # matches wherever the title actually lands regardless of wrapping.
        dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        font_title = _load_font(FONT_BOLD_PATH, FONT_SIZE_COVER_TITLE)
        title_lines = _wrap_text_to_width(
            dummy_draw, COVER_TITLE_TEXT, font_title, CANVAS_WIDTH - 2 * MARGIN_X
        )
        title_line_height = _line_height(font_title)
        font_subtitle = _load_font(FONT_REGULAR_PATH, FONT_SIZE_COVER_SUBTITLE)
        subtitle_line_height = _line_height(font_subtitle)
        block_height = len(title_lines) * title_line_height + 16 + subtitle_line_height
        top = int((CANVAS_HEIGHT - block_height) / 2)
        bottom = top + len(title_lines) * title_line_height

        brightest = max(
            max(img.getpixel((x, y)))
            for y in range(top, bottom)
            for x in range(0, CANVAS_WIDTH, 2)
        )
        assert brightest >= 230

    def test_scrim_darkens_center_band_relative_to_known_poster_color(
        self, monkeypatch
    ):
        """Proves the vertical scrim actually darkens the middle band by
        rendering with a known solid poster color and asserting the
        composited pixel is measurably darker in every channel than the
        pre-scrim color."""
        poster_color = (200, 50, 50)
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: _fake_poster_bytes(color=poster_color),
        )
        # 3 movies -> _grid_dimensions(3) == [3], so the single row of
        # tiles spans the full canvas height and every tile uses the same
        # monkeypatched solid-color poster, making the pre-scrim canvas a
        # known uniform color.
        screening_dates = [
            self._screening_date(1, "/screening/assets/1.jpg"),
            self._screening_date(2, "/screening/assets/2.jpg"),
            self._screening_date(3, "/screening/assets/3.jpg"),
        ]
        result = build_weekend_cover_image(
            screening_dates, "/uploads", self.FRIDAY, self.SATURDAY, self.SUNDAY
        )
        img = Image.open(BytesIO(base64.b64decode(result))).convert("RGB")

        # Sample near the left edge at the vertical center: still inside
        # the scrim's darkest band (alpha depends only on y), but outside
        # the centered title/subtitle/watermark text.
        sample_x, sample_y = 20, CANVAS_HEIGHT // 2
        r, g, b = img.getpixel((sample_x, sample_y))
        assert r < poster_color[0]
        assert g < poster_color[1]
        assert b < poster_color[2]
