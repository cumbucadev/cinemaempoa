# Weekend Cover Art Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a poster-grid mosaic "cover" image to `/weekend/export` — a blurred, scrim-darkened grid of the weekend's movie posters with a centered "Programação Final de Semana" title and date subtitle.

**Architecture:** New pure/PIL-only helpers in `flask_backend/service/weekend_export.py` build the cover image independently of the existing day-schedule renderer, composed into one `build_weekend_cover_image()` entry point. The route calls it once alongside the existing `build_weekend_export_images()` call and passes the result to the template as a new variable.

**Tech Stack:** Flask, PIL (Pillow, already a dependency via the existing day-schedule renderer), `requests` (already a dependency).

## Global Constraints

- No new third-party dependencies — PIL and `requests` are already used in this file/module tree.
- Reuse existing constants/helpers in `flask_backend/service/weekend_export.py` (`CANVAS_WIDTH`, `CANVAS_HEIGHT`, `BG_COLOR`, `FONT_BOLD_PATH`, `FONT_REGULAR_PATH`, `FONT_SIZE_FOOTER`, `WATERMARK_TEXT`, `MARGIN_X`, `MARGIN_BOTTOM`, `FOOTER_HEIGHT`, `_load_font`, `_line_height`, `_wrap_text_to_width`) rather than redefining them.
- All new user-facing copy is Portuguese, matching the existing templates' tone (e.g. `weekend_export.html`'s "Imagens prontas para compartilhar no Instagram...").
- `screening.image` is always a URL string: either `/screening/assets/<filename>` (served from `UPLOAD_FOLDER`) or a full external URL (imgBB). See `flask_backend/service/upload.py`.
- A movie with no poster, or a poster that fails to load, must never crash the whole cover render — it's just skipped/left blank.

---

### Task 1: Weekend date-range subtitle formatting

**Files:**
- Modify: `flask_backend/service/weekend_export.py`
- Test: `flask_backend/tests/test_service/test_weekend_export.py`

**Interfaces:**
- Produces: `_format_weekend_date_range(friday_date: date, saturday_date: date, sunday_date: date) -> str`

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_service/test_weekend_export.py` (add `from flask_backend.service.weekend_export import _format_weekend_date_range` to the existing import block from that module):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestFormatWeekendDateRange -v`
Expected: FAIL with `ImportError` (`_format_weekend_date_range` doesn't exist yet).

- [ ] **Step 3: Implement the helper**

Add to `flask_backend/service/weekend_export.py`, near the top-level constants (after `DAY_DEFS`):

```python
_MONTH_NAMES_PT = {
    1: "janeiro",
    2: "fevereiro",
    3: "março",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}


def _format_weekend_date_range(
    friday_date: date, saturday_date: date, sunday_date: date
) -> str:
    """Formats the three weekend dates as a natural-language Portuguese
    range, e.g. "7, 8 e 9 de agosto". Groups consecutive same-month dates
    together, so a weekend crossing a month boundary (e.g. the last
    weekend of a month) reads as "31 de julho, 1 e 2 de agosto"."""
    dates = [friday_date, saturday_date, sunday_date]

    groups: List[List[date]] = []
    for current_date in dates:
        if groups and groups[-1][-1].month == current_date.month:
            groups[-1].append(current_date)
        else:
            groups.append([current_date])

    parts = []
    for group in groups:
        days = [str(d.day) for d in group]
        month_name = _MONTH_NAMES_PT[group[-1].month]
        day_text = days[0] if len(days) == 1 else f"{', '.join(days[:-1])} e {days[-1]}"
        parts.append(f"{day_text} de {month_name}")

    return ", ".join(parts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestFormatWeekendDateRange -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/weekend_export.py flask_backend/tests/test_service/test_weekend_export.py
git commit -m "feat: add weekend date-range subtitle formatting for cover art"
```

---

### Task 2: Movie dedup for the cover grid

**Files:**
- Modify: `flask_backend/service/weekend_export.py`
- Test: `flask_backend/tests/test_service/test_weekend_export.py`

**Interfaces:**
- Consumes: `ScreeningDate` (existing model, already imported in this file) — each has `.screening.movie.id` (int) and `.screening.image` (str or None).
- Produces:
  - `CoverMovie` dataclass: `movie_id: int`, `image_path: str`
  - `_collect_cover_movies(screening_dates: List[ScreeningDate]) -> List[CoverMovie]`

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_service/test_weekend_export.py` (extend the import to include `CoverMovie`, `_collect_cover_movies`):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestCollectCoverMovies -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the dataclass and helper**

Add to `flask_backend/service/weekend_export.py`, near the existing `RowData`/`RowLayout` dataclasses:

```python
@dataclass
class CoverMovie:
    movie_id: int
    image_path: str


def _collect_cover_movies(screening_dates: List[ScreeningDate]) -> List[CoverMovie]:
    """Deduplicates screening_dates into one CoverMovie per distinct movie,
    keeping the image from the first occurrence in weekend order (the list
    is assumed already date/time-ordered, same as build_weekend_export_images
    expects). Screenings with no image are skipped entirely."""
    seen_movie_ids = set()
    movies: List[CoverMovie] = []
    for screening_date in screening_dates:
        screening = screening_date.screening
        image_path = screening.image
        if not image_path:
            continue
        movie_id = screening.movie.id
        if movie_id in seen_movie_ids:
            continue
        seen_movie_ids.add(movie_id)
        movies.append(CoverMovie(movie_id=movie_id, image_path=image_path))
    return movies
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestCollectCoverMovies -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/weekend_export.py flask_backend/tests/test_service/test_weekend_export.py
git commit -m "feat: add movie dedup helper for weekend cover art"
```

---

### Task 3: Grid dimensions and even segment splitting

**Files:**
- Modify: `flask_backend/service/weekend_export.py`
- Test: `flask_backend/tests/test_service/test_weekend_export.py`

**Interfaces:**
- Produces:
  - `_grid_dimensions(movie_count: int) -> Tuple[int, int]` — returns `(cols, rows)`.
  - `_segment_lengths(total: int, count: int) -> List[int]` — splits `total` pixels into `count` near-equal integer segments (remainder on the last one).

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_service/test_weekend_export.py` (extend the import to include `_grid_dimensions`, `_segment_lengths`):

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestGridDimensions flask_backend/tests/test_service/test_weekend_export.py::TestSegmentLengths -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the helpers**

Add to `flask_backend/service/weekend_export.py`: add `from math import ceil` to the top imports, and change `from typing import List` to `from typing import List, Tuple`. Then:

```python
def _grid_dimensions(movie_count: int) -> Tuple[int, int]:
    """Picks column count from the number of movies (more movies -> more,
    narrower columns), then caps rows at 5 so tiles never get too thin.
    Returns (cols, rows); cols * rows is the max number of tiles shown -
    movies beyond that are dropped by the caller (_collect_cover_movies
    already orders movies by weekend order, so earlier movies win)."""
    if movie_count <= 6:
        cols = 3
    elif movie_count <= 12:
        cols = 4
    else:
        cols = 5

    max_tiles = cols * 5
    tile_count = min(movie_count, max_tiles)
    rows = ceil(tile_count / cols)
    return cols, rows


def _segment_lengths(total: int, count: int) -> List[int]:
    """Splits `total` pixels into `count` near-equal integer segments; any
    remainder from integer division is added to the last segment so the
    segments always sum exactly to `total`."""
    base = total // count
    lengths = [base] * count
    lengths[-1] += total - base * count
    return lengths
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestGridDimensions flask_backend/tests/test_service/test_weekend_export.py::TestSegmentLengths -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/weekend_export.py flask_backend/tests/test_service/test_weekend_export.py
git commit -m "feat: add grid sizing helpers for weekend cover art"
```

---

### Task 4: Poster loading and grid compositing

**Files:**
- Modify: `flask_backend/service/weekend_export.py`
- Test: `flask_backend/tests/test_service/test_weekend_export.py`

**Interfaces:**
- Consumes: `CoverMovie` (Task 2), `_segment_lengths` (Task 3), `CANVAS_WIDTH`/`CANVAS_HEIGHT`/`BG_COLOR` (existing).
- Produces:
  - `_load_poster_bytes(image_path: str, upload_folder: str) -> Optional[bytes]`
  - `_cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image`
  - `_build_poster_grid(tiles: List[CoverMovie], cols: int, rows: int, upload_folder: str) -> Image.Image`

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_service/test_weekend_export.py`. Extend the import from `flask_backend.service.weekend_export` to include `_build_poster_grid`, `_load_poster_bytes`. Add `import requests` and a small PNG-bytes helper near the top of the test file:

```python
def _fake_poster_bytes(width=300, height=450, color=(200, 50, 50)):
    img = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

```python
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


class TestBuildPosterGrid:
    def test_renders_full_canvas_with_all_tiles_loaded(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda image_path, upload_folder: _fake_poster_bytes(),
        )
        tiles = [CoverMovie(movie_id=i, image_path=f"/screening/assets/{i}.jpg") for i in range(6)]
        grid = _build_poster_grid(tiles, cols=3, rows=2, upload_folder="/uploads")
        assert grid.size == (CANVAS_WIDTH, CANVAS_HEIGHT)

    def test_failed_poster_load_leaves_background_without_crashing(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda image_path, upload_folder: None,
        )
        tiles = [CoverMovie(movie_id=1, image_path="/screening/assets/missing.jpg")]
        grid = _build_poster_grid(tiles, cols=3, rows=1, upload_folder="/uploads")
        assert grid.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
        assert grid.getpixel((10, 10)) == BG_COLOR
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestLoadPosterBytes flask_backend/tests/test_service/test_weekend_export.py::TestBuildPosterGrid -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the helpers**

Add `import logging` and `import requests` to the top imports of `flask_backend/service/weekend_export.py`, and change `from typing import List, Tuple` to `from typing import List, Optional, Tuple` (extend the existing `typing` import from Task 3). Add a module logger near the top-level constants:

```python
logger = logging.getLogger(__name__)

LOCAL_ASSET_PREFIX = "/screening/assets/"
```

Then add:

```python
def _load_poster_bytes(image_path: str, upload_folder: str) -> Optional[bytes]:
    """Loads poster image bytes from either a local upload
    (/screening/assets/<filename>, served straight from disk) or a remote
    URL (production imgBB uploads). Returns None on any failure - missing
    file, network error, or bad response - so a single bad poster never
    breaks the whole cover image."""
    try:
        if image_path.startswith(LOCAL_ASSET_PREFIX):
            filename = image_path[len(LOCAL_ASSET_PREFIX):]
            file_path = os.path.join(upload_folder, filename)
            with open(file_path, "rb") as f:
                return f.read()
        response = requests.get(image_path, timeout=10)
        response.raise_for_status()
        return response.content
    except (OSError, requests.RequestException) as exc:
        logger.warning(
            "Falha ao carregar poster '%s' para a capa do fim de semana: %s",
            image_path,
            exc,
        )
        return None


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Center-crops (never distorts) `img` to exactly target_w x target_h,
    cropping whichever dimension has excess before resizing."""
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_w = round(src_h * target_ratio)
        offset = (src_w - new_w) // 2
        img = img.crop((offset, 0, offset + new_w, src_h))
    else:
        new_h = round(src_w / target_ratio)
        offset = (src_h - new_h) // 2
        img = img.crop((0, offset, src_w, offset + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def _build_poster_grid(
    tiles: List[CoverMovie], cols: int, rows: int, upload_folder: str
) -> Image.Image:
    """Renders the CANVAS_WIDTH x CANVAS_HEIGHT poster mosaic: each tile is
    center-cropped to fill its cell. A tile whose poster fails to load is
    left as plain background - grid layout still holds."""
    grid = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR)
    col_widths = _segment_lengths(CANVAS_WIDTH, cols)
    row_heights = _segment_lengths(CANVAS_HEIGHT, rows)

    for idx, tile in enumerate(tiles):
        col, row = idx % cols, idx // cols
        x = sum(col_widths[:col])
        y = sum(row_heights[:row])
        w, h = col_widths[col], row_heights[row]

        poster_bytes = _load_poster_bytes(tile.image_path, upload_folder)
        if poster_bytes is None:
            continue
        try:
            poster = Image.open(BytesIO(poster_bytes)).convert("RGB")
        except Exception as exc:
            logger.warning(
                "Poster inválido para o filme %d na capa do fim de semana: %s",
                tile.movie_id,
                exc,
            )
            continue
        grid.paste(_cover_crop(poster, w, h), (x, y))

    return grid
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestLoadPosterBytes flask_backend/tests/test_service/test_weekend_export.py::TestBuildPosterGrid -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/weekend_export.py flask_backend/tests/test_service/test_weekend_export.py
git commit -m "feat: add poster loading and grid compositing for weekend cover art"
```

---

### Task 5: Blur, scrim, title/subtitle text, and the full cover-image entry point

**Files:**
- Modify: `flask_backend/service/weekend_export.py`
- Test: `flask_backend/tests/test_service/test_weekend_export.py`

**Interfaces:**
- Consumes: `_collect_cover_movies`, `_grid_dimensions`, `_build_poster_grid`, `_format_weekend_date_range` (Tasks 1-4); `_load_font`, `_line_height`, `_wrap_text_to_width`, `FONT_BOLD_PATH`, `FONT_REGULAR_PATH`, `FONT_SIZE_FOOTER`, `WATERMARK_TEXT`, `MARGIN_X`, `MARGIN_BOTTOM`, `FOOTER_HEIGHT` (existing).
- Produces: `build_weekend_cover_image(screening_dates: List[ScreeningDate], upload_folder: str, friday_date: date, saturday_date: date, sunday_date: date) -> Optional[str]` — a base64-encoded PNG string, or `None` if no weekend screening has a usable poster.

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_service/test_weekend_export.py`. Extend the import from `flask_backend.service.weekend_export` to include `build_weekend_cover_image`:

```python
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

    def test_returns_decodable_png_at_canvas_size(self, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda image_path, upload_folder: _fake_poster_bytes(),
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py::TestBuildWeekendCoverImage -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the readability treatment and orchestration**

Add `ImageFilter` to the existing `from PIL import Image, ImageDraw, ImageFont` line, making it `from PIL import Image, ImageDraw, ImageFilter, ImageFont`. Add these constants near the other `FONT_SIZE_*`/`COLUMN_*` constants:

```python
COVER_TITLE_TEXT = "Programação Final de Semana"
FONT_SIZE_COVER_TITLE = 64
FONT_SIZE_COVER_SUBTITLE = 34
COVER_BLUR_RADIUS = 6
COVER_SCRIM_PEAK_ALPHA = 170
```

Then add the rendering helpers and the entry point:

```python
def _build_vertical_scrim(width: int, height: int, peak_alpha: int) -> Image.Image:
    """Black overlay, near-transparent at the top/bottom edges and darkest
    through the middle band, so centered title text stays readable over a
    busy poster grid without hiding the whole image."""
    scrim = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scrim)
    center = height / 2
    for y in range(height):
        distance = abs(y - center) / center
        alpha = max(int(peak_alpha * (1 - distance)), 0)
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return scrim


def _draw_cover_text(img: Image.Image, subtitle_text: str) -> None:
    draw = ImageDraw.Draw(img)
    font_title = _load_font(FONT_BOLD_PATH, FONT_SIZE_COVER_TITLE)
    font_subtitle = _load_font(FONT_REGULAR_PATH, FONT_SIZE_COVER_SUBTITLE)

    title_lines = _wrap_text_to_width(
        draw, COVER_TITLE_TEXT, font_title, CANVAS_WIDTH - 2 * MARGIN_X
    )
    title_line_height = _line_height(font_title)
    subtitle_line_height = _line_height(font_subtitle)

    block_height = len(title_lines) * title_line_height + 16 + subtitle_line_height
    y = (CANVAS_HEIGHT - block_height) / 2

    for line in title_lines:
        line_width = draw.textlength(line, font=font_title)
        x = (CANVAS_WIDTH - line_width) / 2
        draw.text((x, y), line, font=font_title, fill=(255, 255, 255))
        y += title_line_height

    y += 16
    subtitle_width = draw.textlength(subtitle_text, font=font_subtitle)
    x = (CANVAS_WIDTH - subtitle_width) / 2
    draw.text((x, y), subtitle_text, font=font_subtitle, fill=(255, 255, 255))


def _draw_cover_watermark(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    font_footer = _load_font(FONT_REGULAR_PATH, FONT_SIZE_FOOTER)
    watermark_width = draw.textlength(WATERMARK_TEXT, font=font_footer)
    footer_y = CANVAS_HEIGHT - MARGIN_BOTTOM - FOOTER_HEIGHT / 2
    draw.text(
        ((CANVAS_WIDTH - watermark_width) / 2, footer_y),
        WATERMARK_TEXT,
        font=font_footer,
        fill=(255, 255, 255),
    )


def build_weekend_cover_image(
    screening_dates: List[ScreeningDate],
    upload_folder: str,
    friday_date: date,
    saturday_date: date,
    sunday_date: date,
) -> Optional[str]:
    """Builds the weekend's single base64 PNG cover image: a poster-grid
    mosaic of every distinct movie showing that weekend (first-seen poster
    wins), blurred with a dark scrim, and the "Programação Final de
    Semana" title + date subtitle centered on top. Returns None if no
    screening that weekend has a usable poster image."""
    movies = _collect_cover_movies(screening_dates)
    if not movies:
        return None

    cols, rows = _grid_dimensions(len(movies))
    tiles = movies[: cols * rows]

    grid = _build_poster_grid(tiles, cols, rows, upload_folder)
    blurred = grid.filter(ImageFilter.GaussianBlur(COVER_BLUR_RADIUS)).convert("RGBA")
    scrim = _build_vertical_scrim(CANVAS_WIDTH, CANVAS_HEIGHT, COVER_SCRIM_PEAK_ALPHA)
    composited = Image.alpha_composite(blurred, scrim).convert("RGB")

    subtitle_text = _format_weekend_date_range(friday_date, saturday_date, sunday_date)
    _draw_cover_text(composited, subtitle_text)
    _draw_cover_watermark(composited)

    buffer = BytesIO()
    composited.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_weekend_export.py -v`
Expected: PASS (full file, including all earlier tasks' tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/weekend_export.py flask_backend/tests/test_service/test_weekend_export.py
git commit -m "feat: render blurred/scrim weekend cover image with title and subtitle"
```

---

### Task 6: Wire the cover image into the /weekend/export route and template

**Files:**
- Modify: `flask_backend/routes/screening.py:57` (import), `flask_backend/routes/screening.py:219-230` (`weekend_export` route)
- Modify: `flask_backend/templates/screening/weekend_export.html`
- Test: `flask_backend/tests/test_routes/test_screening.py`

**Interfaces:**
- Consumes: `build_weekend_cover_image(screening_dates, upload_folder, friday_date, saturday_date, sunday_date) -> Optional[str]` (Task 5).

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_routes/test_screening.py`, inside the existing `TestScreeningWeekendExport` class (this test file already imports `date`, `_create_screening`, `get_weekend_dates`, and `client`/`setup_cinemas` fixtures):

```python
    def test_weekend_export_shows_no_cover_when_no_screenings_have_images(
        self, client, setup_cinemas
    ):
        friday_date, _, _ = get_weekend_dates(date.today())
        with client.application.app_context():
            _create_screening(movie_title="Filme Sem Poster", screening_date=friday_date)
        response = client.get("/weekend/export")
        html = response.get_data(as_text=True)
        assert "Capa" not in html

    def test_weekend_export_shows_cover_when_a_screening_has_an_image(
        self, client, setup_cinemas, monkeypatch
    ):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda image_path, upload_folder: _fake_png_bytes(),
        )
        friday_date, _, _ = get_weekend_dates(date.today())
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Com Poster",
                screening_date=friday_date,
                image="/screening/assets/poster.jpg",
                image_width=300,
                image_height=450,
            )
        response = client.get("/weekend/export")
        html = response.get_data(as_text=True)
        assert "Capa" in html
        assert html.count("data:image/png;base64,") == 2  # cover + 1 day image
```

Add the `_fake_png_bytes` helper and a `PIL`/`io` import near the top of `flask_backend/tests/test_routes/test_screening.py` (it already imports `io`, so only PIL and `BytesIO` are new):

```python
from io import BytesIO

from PIL import Image


def _fake_png_bytes():
    img = Image.new("RGB", (300, 450), (200, 50, 50))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest "flask_backend/tests/test_routes/test_screening.py::TestScreeningWeekendExport" -v`
Expected: `test_weekend_export_shows_no_cover_when_no_screenings_have_images` PASSes already (no cover markup exists yet at all, so "Capa" is indeed absent) but `test_weekend_export_shows_cover_when_a_screening_has_an_image` FAILs (no "Capa" text, and only 1 `data:image/png;base64,` occurrence instead of 2).

- [ ] **Step 3: Wire the route**

In `flask_backend/routes/screening.py:57`, change:

```python
from flask_backend.service.weekend_export import build_weekend_export_images
```

to:

```python
from flask_backend.service.weekend_export import (
    build_weekend_cover_image,
    build_weekend_export_images,
)
```

Then replace the `weekend_export` route (`flask_backend/routes/screening.py:219-230`):

```python
@bp.route("/weekend/export")
def weekend_export():
    screening_dates, friday_date, saturday_date, sunday_date = (
        get_weekend_screening_dates()
    )
    day_exports = build_weekend_export_images(
        screening_dates, friday_date, saturday_date, sunday_date
    )
    cover_image_base64 = build_weekend_cover_image(
        screening_dates,
        current_app.config["UPLOAD_FOLDER"],
        friday_date,
        saturday_date,
        sunday_date,
    )
    return render_template(
        "screening/weekend_export.html",
        day_exports=day_exports,
        cover_image_base64=cover_image_base64,
    )
```

- [ ] **Step 4: Add the cover section to the template**

In `flask_backend/templates/screening/weekend_export.html`, insert this block right after the intro `<p>...</p>` (the one starting "Imagens prontas para compartilhar...") and before `{% for day_export in day_exports %}`:

```html
    {% if cover_image_base64 %}
        <div class="mb-5">
            <h3 class="mb-3">Capa</h3>
            <figure class="mb-0">
                {# djlint:off #}
                <img src="data:image/png;base64,{{ cover_image_base64 }}"
                     alt="Capa da programação de fim de semana"
                     width="1080"
                     height="1350"
                     class="img-fluid border rounded"
                     style="max-width: 360px;">
                {# djlint:on #}
            </figure>
        </div>
    {% endif %}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py flask_backend/tests/test_service/test_weekend_export.py -v`
Expected: PASS (all tests in both files)

- [ ] **Step 6: Run the full test suite and lint**

Run: `pytest` then `uv run ruff check --fix` then `uv run ruff format` then `uv run djlint flask_backend/templates --lint --profile=jinja`
Expected: all green; if `djlint` flags the new template block, run `uv run djlint --reformat flask_backend/templates --format-css --format-js` and re-check.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/routes/screening.py flask_backend/templates/screening/weekend_export.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: show weekend cover art on /weekend/export"
```

---

## Self-Review Notes

- **Spec coverage:** dedup/first-occurrence-wins (Task 2), grid columns 3/4/5 scaling + row cap (Task 3), center-crop tiling (Task 4), poster loading for both local and remote `screening.image` forms with graceful failure (Task 4), blur + vertical scrim + centered title/subtitle + watermark (Task 5), date-range subtitle incl. cross-month case (Task 1), route/template wiring with conditional rendering (Task 6), all spec'd tests are present.
- **Type consistency:** `CoverMovie` (Task 2) is threaded unchanged through `_grid_dimensions`'s caller, `_build_poster_grid` (Task 4), and `build_weekend_cover_image` (Task 5). `upload_folder: str` is consistent from `_load_poster_bytes` through to the route's `current_app.config["UPLOAD_FOLDER"]`. `build_weekend_cover_image` returns `Optional[str]` (base64 or `None`), matching the template's `{% if cover_image_base64 %}` check.
- **No placeholders:** every step has complete, copy-pasteable code.
