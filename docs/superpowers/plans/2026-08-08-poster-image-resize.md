# Poster Image Resize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop every image the app stores (posters and cinema photos) from being uploaded at their raw source size, so mobile visitors stop downloading multi-hundred-KB-to-multi-MB images on first load.

**Architecture:** A single `resize_for_display()` function (new `image_processing.py` module) is wired into the one existing choke point every image upload already passes through — `save_image()` — so every current and future caller (poster pipeline, manual admin uploads, scraper imports, cinema photos) gets it automatically, with no schema change. A second new module, `image_resize_pipeline.py`, backfills already-stored images via a new `flask resize-images` CLI command, reusing `save_image()` and the existing `download_image_from_url()`.

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, Pillow (PIL) for image resizing/re-encoding, Click for the CLI command, pytest for tests.

## Global Constraints

- Python 3.14.x (see `.python-version`); use `uv run` / `uv sync`, never bare `python`/`pip`.
- Do not touch `requests`, `jiter`, or `jinja2` pins — they're pinned for `atomic-agents`/`instructor` compatibility (see `CLAUDE.md`).
- Run `uv run ruff check --fix` and `uv run ruff format` before considering any task's code complete.
- Every new/changed Python file must pass `pytest` (`pytest flask_backend/tests`) before its commit.
- Follow existing Portuguese-language conventions for CLI `--help` text and user-facing `click.echo` output (see `fetch-posters` in `flask_backend/commands.py`).
- No AI/agent co-author trailer in any commit message (project convention, see `CLAUDE.md`).

Spec: `docs/superpowers/specs/2026-08-08-poster-image-resize-design.md`

---

### Task 1: `resize_for_display()` in a new `image_processing` module

**Files:**
- Create: `flask_backend/service/image_processing.py`
- Test: `flask_backend/tests/test_service/test_image_processing.py`

**Interfaces:**
- Produces: `resize_for_display(image_bytes: bytes, max_dimension: int = 1200, quality: int = 80) -> bytes` — resizes so the longer edge is `<= max_dimension` (never upscales), re-encodes as WebP, returns the encoded bytes. Used by Task 2 (`save_image`) and Task 4 (backfill pipeline).

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_service/test_image_processing.py`:

```python
import io

from PIL import Image

from flask_backend.service.image_processing import resize_for_display


def _make_image_bytes(width, height, mode="RGB", fmt="PNG", color=(120, 60, 200)):
    buffer = io.BytesIO()
    Image.new(mode, (width, height), color=color).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer.read()


class TestResizeForDisplay:
    def test_downscales_when_longer_edge_exceeds_max_dimension(self):
        source = _make_image_bytes(2000, 1000)

        result = resize_for_display(source, max_dimension=1200)

        image = Image.open(io.BytesIO(result))
        assert image.size == (1200, 600)

    def test_does_not_upscale_smaller_images(self):
        source = _make_image_bytes(400, 300)

        result = resize_for_display(source, max_dimension=1200)

        image = Image.open(io.BytesIO(result))
        assert image.size == (400, 300)

    def test_output_is_webp(self):
        source = _make_image_bytes(500, 500)

        result = resize_for_display(source)

        image = Image.open(io.BytesIO(result))
        assert image.format == "WEBP"

    def test_preserves_alpha_channel(self):
        source = _make_image_bytes(
            300, 300, mode="RGBA", fmt="PNG", color=(10, 20, 30, 128)
        )

        result = resize_for_display(source)

        image = Image.open(io.BytesIO(result))
        assert image.mode == "RGBA"

    def test_flattens_palette_mode_without_error(self):
        buffer = io.BytesIO()
        Image.new("P", (200, 200)).save(buffer, format="PNG")
        buffer.seek(0)
        source = buffer.read()

        result = resize_for_display(source)

        image = Image.open(io.BytesIO(result))
        assert image.format == "WEBP"

    def test_higher_quality_produces_larger_output(self):
        source = _make_image_bytes(800, 800, color=(200, 40, 90))

        low = resize_for_display(source, quality=10)
        high = resize_for_display(source, quality=95)

        assert len(high) > len(low)

    def test_uses_longest_edge_for_portrait_images(self):
        source = _make_image_bytes(900, 1600)

        result = resize_for_display(source, max_dimension=1200)

        image = Image.open(io.BytesIO(result))
        assert image.size == (675, 1200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest flask_backend/tests/test_service/test_image_processing.py -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'flask_backend.service.image_processing'`

- [ ] **Step 3: Write the implementation**

Create `flask_backend/service/image_processing.py`:

```python
from io import BytesIO

from PIL import Image

# Modes WebP can't encode directly (or that would lose information encoding
# it directly, e.g. palette-indexed) - flatten to RGBA first.
_MODES_NEEDING_CONVERSION = {"P", "CMYK", "1", "L", "LA"}


def resize_for_display(
    image_bytes: bytes, max_dimension: int = 1200, quality: int = 80
) -> bytes:
    """Resizes an image so its longest edge is at most `max_dimension`
    pixels (never upscaling smaller images) and re-encodes it as WebP.

    This is the single normalization point every image the app stores
    passes through - see issue #229 and
    docs/superpowers/specs/2026-08-08-poster-image-resize-design.md.
    """
    image = Image.open(BytesIO(image_bytes))
    image.load()

    if image.mode in _MODES_NEEDING_CONVERSION or image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    width, height = image.size
    longest_edge = max(width, height)
    if longest_edge > max_dimension:
        scale = max_dimension / longest_edge
        new_size = (round(width * scale), round(height * scale))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    output = BytesIO()
    image.save(output, format="WEBP", quality=quality)
    return output.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_service/test_image_processing.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/service/image_processing.py flask_backend/tests/test_service/test_image_processing.py && uv run ruff format flask_backend/service/image_processing.py flask_backend/tests/test_service/test_image_processing.py`

- [ ] **Step 6: Commit**

```bash
git add flask_backend/service/image_processing.py flask_backend/tests/test_service/test_image_processing.py
git commit -m "feat: add resize_for_display() for normalizing stored image sizes"
```

---

### Task 2: Wire `resize_for_display()` into `save_image()`

**Files:**
- Modify: `flask_backend/service/screening.py:89-101` (`save_image`)
- Test: `flask_backend/tests/test_service/test_screening.py:533-583` (`TestSaveImage`)

**Interfaces:**
- Consumes: `resize_for_display(image_bytes: bytes, max_dimension: int = 1200, quality: int = 80) -> bytes` from Task 1.
- Produces: `save_image(file, app, filename: Optional[str] = None) -> Tuple[str, int, int]` — same public signature and return shape as before (URL, width, height of the *resized* image now), so every existing caller (`poster_pipeline.py`, `routes/screening.py`, `routes/admin/cinemas.py`, `service/screening.py`'s import pipeline) needs no changes.

- [ ] **Step 1: Write the failing tests**

In `flask_backend/tests/test_service/test_screening.py`, replace the existing `TestSaveImage` class (currently lines 533-583) with:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest flask_backend/tests/test_service/test_screening.py::TestSaveImage -v`
Expected: FAIL — `AttributeError` / `ImportError` (`resize_for_display` not imported/used yet in `screening.py`, and current `save_image` doesn't call it), plus the filename-conversion tests fail because filenames aren't rewritten yet.

- [ ] **Step 3: Write the implementation**

In `flask_backend/service/screening.py`, add one new import line directly above the existing `from flask_backend.service.upload import ...` line (currently line 35) — do not duplicate that existing line, just add this new one next to it:

```python
from flask_backend.service.image_processing import resize_for_display
```

Replace `save_image` (currently `flask_backend/service/screening.py:89-101`) with:

```python
def save_image(file, app, filename: Optional[str] = None) -> Tuple[str, int, int]:
    """Resizes the received `file` for display (see resize_for_display), then
    saves it into disk or uploads it to imgBB API, depending on the current
    environment"""
    source_filename = filename or getattr(file, "filename", None)
    resized_bytes = resize_for_display(file.read())
    resized_file = BytesIO(resized_bytes)
    webp_filename = _to_webp_filename(source_filename)

    # always save images locally on development
    if APP_ENVIRONMENT != EnvironmentEnum.PRODUCTION:
        return upload_image_to_local_disk(resized_file, app, webp_filename)
    # on production, attempt to save to the imgBB API
    try:
        return upload_image_to_api(app, resized_file)
    # on failure, save locally
    except requests.exceptions.HTTPError:
        resized_file.seek(0)
        return upload_image_to_local_disk(resized_file, app, webp_filename)


def _to_webp_filename(filename: Optional[str]) -> str:
    base = filename.rsplit(".", 1)[0] if filename and "." in filename else filename
    return f"{base or 'image'}.webp"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_service/test_screening.py -v`
Expected: PASS — all of `TestSaveImage` and every other test in the file (the rest of the suite doesn't touch `save_image`'s internals, so it should be unaffected; if any other test in this file also calls `save_image` without mocking `resize_for_display`, apply the same `resize_for_display` patch used above).

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py && uv run ruff format flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py`

- [ ] **Step 6: Full test suite sanity check**

Run: `uv run pytest flask_backend/tests -v`
Expected: PASS — confirms no other test (e.g. routes tests exercising the create/update screening or cinema forms) broke from the `save_image` behavior change. If any route-level test uploads a real image through `save_image` without mocking `resize_for_display`, it will still pass functionally (Pillow will actually resize/re-encode a small test fixture image), just slower — only fix it if it actually fails.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py
git commit -m "feat: resize and re-encode images to webp before upload"
```

---

### Task 3: Repository queries for images eligible for backfill

**Files:**
- Modify: `flask_backend/repository/screenings.py`
- Modify: `flask_backend/repository/cinemas.py`
- Test: `flask_backend/tests/test_repository/test_screenings.py`
- Test: `flask_backend/tests/test_repository/test_cinemas.py`

**Interfaces:**
- Produces: `get_screenings_with_image() -> List[Screening]` (screenings.py), `get_cinemas_with_photo() -> List[Cinema]` (cinemas.py). Both consumed by Task 4's backfill pipeline.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_repository/test_screenings.py` (add `get_screenings_with_image` to the existing import block at the top of the file, then add this class anywhere at module level):

```python
class TestGetScreeningsWithImage:
    def test_returns_only_screenings_with_image_set(self, app, setup_cinemas):
        with app.app_context():
            with_image_id, _ = _create_screening(
                app, "Com Imagem", "com-imagem", [date.today()]
            )
            without_image_id, _ = _create_screening(
                app, "Sem Imagem", "sem-imagem", [date.today()]
            )
            screening = db_session.get(Screening, with_image_id)
            screening.image = "https://i.ibb.co/x/poster.webp"
            screening.image_width = 800
            screening.image_height = 1200
            db_session.commit()

            result = get_screenings_with_image()

        result_ids = {s.id for s in result}
        assert with_image_id in result_ids
        assert without_image_id not in result_ids

    def test_returns_empty_list_when_no_screening_has_image(self, app, setup_cinemas):
        with app.app_context():
            _create_screening(app, "Sem Imagem", "sem-imagem-2", [date.today()])

            result = get_screenings_with_image()

        assert result == []
```

Append to `flask_backend/tests/test_repository/test_cinemas.py` (add `get_cinemas_with_photo` to the existing import line):

```python
class TestGetCinemasWithPhoto:
    def test_returns_only_cinemas_with_photo_set(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_by_slug("capitolio")
            update(
                cinema,
                name=cinema.name,
                url=cinema.url,
                photo="https://i.ibb.co/x/capitolio.webp",
                photo_width=900,
                photo_height=600,
            )

            result = get_cinemas_with_photo()

        result_slugs = {c.slug for c in result}
        assert "capitolio" in result_slugs
        assert "sala-redencao" not in result_slugs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest flask_backend/tests/test_repository/test_screenings.py::TestGetScreeningsWithImage flask_backend/tests/test_repository/test_cinemas.py::TestGetCinemasWithPhoto -v`
Expected: FAIL — `ImportError: cannot import name 'get_screenings_with_image'` / `'get_cinemas_with_photo'`

- [ ] **Step 3: Write the implementation**

In `flask_backend/repository/screenings.py`, add (near the other `get_screenings_*` query functions):

```python
def get_screenings_with_image() -> List[Screening]:
    """Return screenings that have an image set. Used by the resize-images
    backfill (flask_backend.service.image_resize_pipeline) to find
    candidates for reprocessing."""
    return (
        db_session.query(Screening)
        .filter(Screening.image.isnot(None), Screening.image != "")
        .order_by(Screening.id)
        .all()
    )
```

In `flask_backend/repository/cinemas.py`, add (near `get_all`):

```python
def get_cinemas_with_photo() -> List[Cinema]:
    """Return cinemas that have a photo set. Used by the resize-images
    backfill (flask_backend.service.image_resize_pipeline) to find
    candidates for reprocessing."""
    return (
        db_session.query(Cinema)
        .filter(Cinema.photo.isnot(None), Cinema.photo != "")
        .order_by(Cinema.id)
        .all()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_repository/test_screenings.py flask_backend/tests/test_repository/test_cinemas.py -v`
Expected: PASS

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/repository/screenings.py flask_backend/repository/cinemas.py flask_backend/tests/test_repository/test_screenings.py flask_backend/tests/test_repository/test_cinemas.py && uv run ruff format flask_backend/repository/screenings.py flask_backend/repository/cinemas.py flask_backend/tests/test_repository/test_screenings.py flask_backend/tests/test_repository/test_cinemas.py`

- [ ] **Step 6: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/repository/cinemas.py flask_backend/tests/test_repository/test_screenings.py flask_backend/tests/test_repository/test_cinemas.py
git commit -m "feat: add repository queries for images eligible for resize backfill"
```

---

### Task 4: Backfill pipeline (`image_resize_pipeline.py`)

**Files:**
- Create: `flask_backend/service/image_resize_pipeline.py`
- Test: `flask_backend/tests/test_service/test_image_resize_pipeline.py`

**Interfaces:**
- Consumes: `get_screenings_with_image()`, `get_cinemas_with_photo()` (Task 3); `download_image_from_url(url) -> Tuple[Optional[BytesIO], Optional[str]]` and `save_image(file, app, filename=None) -> Tuple[str, int, int]` (both already in `flask_backend/service/screening.py`, `save_image` now resizes per Task 2).
- Produces: `ResizePipelineResult` dataclass (`processed`, `resized`, `skipped_already_processed`, `errors` — all `int`, default `0`) and `run_pipeline(current_app, limit: Optional[int] = None, dry_run: bool = False) -> ResizePipelineResult`. Consumed by Task 5's CLI command.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_service/test_image_resize_pipeline.py`:

```python
import io
from datetime import date
from unittest.mock import MagicMock, patch

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.cinemas import update as update_cinema
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

    def test_download_failure_increments_errors_and_continues(
        self, app, setup_cinemas
    ):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest flask_backend/tests/test_service/test_image_resize_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flask_backend.service.image_resize_pipeline'`

- [ ] **Step 3: Write the implementation**

Create `flask_backend/service/image_resize_pipeline.py`:

```python
"""Backfill pipeline that reprocesses already-stored screening posters and
cinema photos through resize_for_display() (via save_image()), for images
uploaded before issue #229's resize step shipped.

Usage (via CLI):
    flask resize-images          # process all eligible screenings/cinemas
    flask resize-images --limit 10
    flask resize-images --dry-run
"""

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from flask_backend.db import db_session
from flask_backend.repository.cinemas import get_cinemas_with_photo
from flask_backend.repository.screenings import get_screenings_with_image
from flask_backend.service.screening import download_image_from_url, save_image

logger = logging.getLogger(__name__)

# Must match resize_for_display's default max_dimension - an image within
# this bound and already webp is assumed to have already gone through the
# resize pipeline, so reprocessing it would be a no-op.
MAX_DIMENSION = 1200


@dataclass
class ResizePipelineResult:
    processed: int = 0
    resized: int = 0
    skipped_already_processed: int = 0
    errors: int = 0


def _is_already_processed(
    url: Optional[str], width: Optional[int], height: Optional[int]
) -> bool:
    if not url or width is None or height is None:
        return False
    is_webp = urlparse(url).path.lower().endswith(".webp")
    within_bounds = max(width, height) <= MAX_DIMENSION
    return is_webp and within_bounds


def _reprocess(url: str, current_app):
    image_bytes, filename = download_image_from_url(url)
    if image_bytes is None:
        raise RuntimeError(f"Falha ao baixar imagem: {url}")
    return save_image(image_bytes, current_app, filename)


def run_pipeline(
    current_app,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> ResizePipelineResult:
    """Reprocesses every screening image / cinema photo that isn't already
    a webp within MAX_DIMENSION, resizing and re-uploading via save_image()
    and updating the corresponding DB row."""
    result = ResizePipelineResult()

    all_screenings = get_screenings_with_image()
    screenings_to_process = [
        s
        for s in all_screenings
        if not _is_already_processed(s.image, s.image_width, s.image_height)
    ]

    all_cinemas = get_cinemas_with_photo()
    cinemas_to_process = [
        c
        for c in all_cinemas
        if not _is_already_processed(c.photo, c.photo_width, c.photo_height)
    ]

    result.skipped_already_processed = (
        len(all_screenings)
        - len(screenings_to_process)
        + len(all_cinemas)
        - len(cinemas_to_process)
    )

    items = [("screening", s) for s in screenings_to_process] + [
        ("cinema", c) for c in cinemas_to_process
    ]
    if limit is not None:
        items = items[:limit]

    for kind, obj in items:
        result.processed += 1
        url = obj.image if kind == "screening" else obj.photo

        if dry_run:
            logger.info("[dry-run] %s #%d: reprocessaria %s", kind, obj.id, url)
            continue

        try:
            new_url, width, height = _reprocess(url, current_app)
        except Exception as exc:
            logger.warning(
                "%s #%d: erro ao reprocessar '%s': %s", kind, obj.id, url, exc
            )
            result.errors += 1
            continue

        if kind == "screening":
            obj.image = new_url
            obj.image_width = width
            obj.image_height = height
        else:
            obj.photo = new_url
            obj.photo_width = width
            obj.photo_height = height
        db_session.add(obj)
        db_session.commit()
        result.resized += 1

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_service/test_image_resize_pipeline.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/service/image_resize_pipeline.py flask_backend/tests/test_service/test_image_resize_pipeline.py && uv run ruff format flask_backend/service/image_resize_pipeline.py flask_backend/tests/test_service/test_image_resize_pipeline.py`

- [ ] **Step 6: Commit**

```bash
git add flask_backend/service/image_resize_pipeline.py flask_backend/tests/test_service/test_image_resize_pipeline.py
git commit -m "feat: add resize-images backfill pipeline"
```

---

### Task 5: `flask resize-images` CLI command

**Files:**
- Modify: `flask_backend/commands.py`

**Interfaces:**
- Consumes: `run_pipeline(current_app, limit=None, dry_run=False) -> ResizePipelineResult` (Task 4); `pipeline_runs.start(pipeline_name: str) -> PipelineRun` and `pipeline_runs.finish(run_id, status, summary=None, error_message=None) -> PipelineRun` (existing, `flask_backend/repository/pipeline_runs.py`).
- Produces: a registered `resize-images` Flask CLI command.

- [ ] **Step 1: Write the implementation**

In `flask_backend/commands.py`, add the command (near `fetch_posters`, e.g. directly after it):

```python
@click.command("resize-images")
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Número máximo de imagens a reprocessar. Sem limite por padrão.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Apenas lista o que seria feito, sem fazer requisições.",
)
@click.option(
    "--verbose", "-v", is_flag=True, default=False, help="Mostra logs detalhados."
)
def resize_images(limit, dry_run, verbose):
    """Reprocessa imagens de sessões e cinemas enviadas antes da #229.

    Baixa cada imagem que ainda não está no formato/tamanho alvo (webp,
    maior lado <= 1200px), reprocessa via resize_for_display() e reenvia,
    atualizando o registro no banco.
    """
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.image_resize_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhuma requisição será feita ===\n")

    run = pipeline_runs.start("resize-images")
    try:
        result = run_pipeline(current_app, limit=limit, dry_run=dry_run)
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise

    status = "warning" if result.errors > 0 else "success"
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "processed": result.processed,
                "resized": result.resized,
                "skipped_already_processed": result.skipped_already_processed,
                "errors": result.errors,
            }
        ),
    )

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado do reprocessamento de imagens:")
    click.echo(f"  Processadas:            {result.processed}")
    click.echo(f"  Reprocessadas:          {result.resized}")
    click.echo(f"  Já otimizadas (pulado): {result.skipped_already_processed}")
    click.echo(f"  Erros:                  {result.errors}")
```

Register it in `register_commands` (`flask_backend/commands.py:28-44`), directly after the existing `app.cli.add_command(fetch_posters)` line:

```python
    app.cli.add_command(fetch_posters)
    app.cli.add_command(resize_images)
```

- [ ] **Step 2: Verify the command is registered**

Run: `uv run flask --app flask_backend resize-images --help`
Expected: prints the command's help text (confirms `register_commands` wired it correctly), no traceback.

- [ ] **Step 3: Manual dry-run smoke test against the dev database**

Run: `uv run flask --app flask_backend resize-images --dry-run -v`
Expected: runs without error; logs one `[dry-run] screening #N: reprocessaria <url>` (or `cinema #N`) line per eligible row, ends with the `Resultado do reprocessamento de imagens:` summary block, `Processadas` count matches how many screenings/cinemas in `development.sqlite` currently have a non-webp or oversized image.

- [ ] **Step 4: Lint and format**

Run: `uv run ruff check --fix flask_backend/commands.py && uv run ruff format flask_backend/commands.py`

- [ ] **Step 5: Full test suite + coverage check**

Run: `uv run pytest flask_backend/tests -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add flask_backend/commands.py
git commit -m "feat: add flask resize-images CLI command"
```

---

## After all tasks: manual end-to-end verification

Not a task with its own commit — a final check before calling the branch done:

1. Start the dev server (`uv run flask --app flask_backend run --debug`) and, in dev/local-disk mode, manually create or edit a screening with a poster image upload through the admin UI. Confirm the saved file under `flask_backend/static/screening/assets/` (or wherever `UPLOAD_FOLDER` points) has a `.webp` extension and is small.
2. Run `uv run flask --app flask_backend fetch-posters --dry-run` to confirm it still runs cleanly end-to-end with the changed `save_image`.
3. Run the full lint/format/test suite one more time per `CLAUDE.md`: `uv run ruff check --fix`, `uv run ruff format`, `uv run djlint flask_backend/templates --lint --profile=jinja` (no templates changed by this plan, but this project's convention runs all four before a PR), `pytest`.
