# Weekend Cover Art — Design

## Problem

`/weekend/export` renders share-ready PNGs of the weekend's schedule (one or
more per day, table-style: movie/cinema/time). There's no single "cover"
image that visually represents the weekend as a whole — something to lead
with on Instagram before the schedule slides. This adds one such cover
image: a poster-grid mosaic of the weekend's movies with a centered title
and date subtitle.

## Scope

One new cover image on `/weekend/export`, generated server-side with PIL,
consistent with the existing day-schedule image generation in
`flask_backend/service/weekend_export.py`. No changes to the day-schedule
images themselves.

## Architecture

A new function `build_weekend_cover_image()` lives alongside (not merged
into) the existing `build_weekend_export_images()` in
`flask_backend/service/weekend_export.py`. The route calls both and passes
a new `cover_image_base64` template variable. This keeps the existing
function's signature and tests untouched and mirrors the existing
`render_day_image` pattern (a render function returning PNG bytes /
base64).

## Data flow / movie dedup

- Reuse the `screening_dates` list already fetched by the route
  (`get_weekend_screening_dates()`) — it's flat and date/time-ordered
  across Friday–Sunday.
- Walk it once. For each `ScreeningDate`, skip if `screening.image` is
  falsy, or if `screening.movie.id` has already been seen. Otherwise
  record `(movie.id, image_path)`.
- This gives "first occurrence in weekend order" dedup (Friday morning
  through Sunday night), and naturally excludes movies with no poster.
- If zero movies survive this filter, `build_weekend_cover_image()`
  returns `None` and the template omits the cover section entirely — no
  "no cover" placeholder message, since this is a bonus lead image, not a
  required section.

## Grid layout

- Canvas: 1080×1350 (same `CANVAS_WIDTH`/`CANVAS_HEIGHT` as the day
  images).
- Column count scales with movie count:
  - ≤ 6 movies → 3 columns
  - 7–12 movies → 4 columns
  - 13+ movies → 5 columns
- Row count is `ceil(tile_count / cols)`, capped at 5 rows. This bounds
  the grid at `cols * 5` tiles; on an unusually packed weekend, movies
  beyond that cap are simply dropped from the grid (favoring earlier /
  Friday titles, since the source list is date/time-ordered). This keeps
  tiles from becoming absurdly thin.
- Tiles are distributed per row (`_distribute_counts`), not fixed at
  `cols` for every row: `tile_count` is spread across the row count as
  evenly as possible, front-loading the remainder onto leading rows so no
  row ever needs more than `cols` tiles. A row with fewer tiles than the
  tier's column count gets proportionally *wider* tiles — every row is
  always exactly full, so there is never a leftover blank cell, and fewer
  movies means bigger tiles rather than empty background.
- Tile size = `CANVAS_WIDTH / row_tile_count` × `CANVAS_HEIGHT / rows` for
  each row's own tile count. Each poster is center-cropped (cover-fit, no
  distortion) to exactly fill its tile.

## Poster loading

New helper:

```
_load_poster_bytes(image_path: str, upload_folder: str) -> Optional[bytes]
```

- `screening.image` is always a URL string produced by the existing
  upload pipeline (`flask_backend/service/upload.py`): either a local
  relative path of the form `/screening/assets/<filename>` (dev, and
  production fallback), or a full imgBB URL (production default).
- If `image_path` starts with `/screening/assets/`, read the file
  directly from `upload_folder` (no network call).
- Otherwise, `requests.get(image_path, timeout=10)` and use the response
  body.
- Wrapped in try/except: any failure (missing file, network error,
  non-200, corrupt/unparseable image) logs a warning via
  `logging.getLogger(__name__)` and that movie is skipped from the grid —
  not fatal to the rest of the cover image.
- This function is a deliberate seam: unit tests monkeypatch it directly
  so no real network or disk I/O is needed to test grid/layout/dedup
  logic.

## Readability treatment (blur + gradient + text)

1. Assemble the full poster grid as described above (RGB image).
2. Apply a light `ImageFilter.GaussianBlur` (radius ≈ 6) to the entire
   assembled grid.
3. Composite a black vertical-gradient scrim on top: near-transparent at
   the very top/bottom edges, darkest through the middle band where the
   title sits (peak alpha ≈ 160–180).
4. Draw centered white text on top of the scrim:
   - Title: "Programação Final de Semana" — `FONT_BOLD_PATH`, large size.
   - Subtitle below it: the formatted date range — `FONT_REGULAR_PATH`,
     smaller size.
5. Small `cinemaempoa.com.br` watermark near the bottom, consistent in
   style with the existing day images' footer.

### Date range formatting

New helper:

```
_format_weekend_date_range(friday_date: date, saturday_date: date, sunday_date: date) -> str
```

- Common case (all three dates share a month): `"7, 8 e 9 de agosto"`.
- Cross-month weekend (rare, e.g. last weekend of a month): groups
  consecutive same-month days and lists each group with its own month
  name, e.g. `"31 de julho, 1 e 2 de agosto"`.
- Portuguese month names, lowercase, no leading zero on day numbers.

## Wiring

- `weekend_export()` route (`flask_backend/routes/screening.py`): read
  `current_app.config["UPLOAD_FOLDER"]`, call
  `build_weekend_cover_image(screening_dates, upload_folder, friday_date, saturday_date, sunday_date)`,
  pass `cover_image_base64` into the template alongside the existing
  `day_exports`.
- Template (`flask_backend/templates/screening/weekend_export.html`): new
  section above the existing per-day loop, reusing the same `<img>`
  styling/pattern as the day images (base64 PNG data URI, `img-fluid`,
  `max-width: 360px`). Rendered only when `cover_image_base64` is
  truthy — no `{% else %}` placeholder branch.

## Testing

- `_format_weekend_date_range`: same-month case, cross-month case.
- Column-count thresholds (3/4/5 cols at the boundary counts).
- Dedup logic: a movie appearing in multiple screenings keeps only its
  first-seen poster; screenings with no `image` are skipped entirely.
- `build_weekend_cover_image()` end-to-end with `_load_poster_bytes`
  monkeypatched to return synthetic image bytes (or `None` for a
  simulated failed fetch) — no real network/disk I/O in tests. Covers:
  normal case (valid PNG returned, correct dimensions), zero-eligible-
  movies case (returns `None`), and a failed poster load being skipped
  without crashing the whole render.
- Route test: `/weekend/export` still returns 200; cover section markup
  is present when eligible screenings-with-images exist for the weekend,
  and absent when none do (reuse the existing `setup_cinemas` /
  screening fixtures pattern from `test_screening.py`).

## Out of scope

- Per-day cover images (explicitly rejected — one grid for the whole
  weekend).
- Poster-source priority logic when the same movie has different images
  per cinema (explicitly rejected — first occurrence in weekend order
  wins).
- Any change to the existing day-schedule image rendering
  (`render_day_image`, `paginate_rows_for_day`, etc).
