import base64
from datetime import date
from io import BytesIO

from PIL import Image

from flask_backend.service.weekend_export import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    MAX_TITLE_LINES,
    RowData,
    _available_rows_height,
    _format_weekend_date_range,
    build_weekend_export_images,
    paginate_rows_for_day,
    render_day_image,
)


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
