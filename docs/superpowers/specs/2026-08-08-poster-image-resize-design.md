# Poster image resize (issue #229)

## Problem

Mobile first-time visitors hit the index page and immediately download very
large poster images, making the site feel broken. Confirmed example: the
YUNAN poster (`https://i.ibb.co/RkVRSRDM/f0129f72410e.png`) is a 1200x675
PNG, 1.3MB.

Root cause, traced through the code:

- No resize/recompress step exists anywhere in the image pipeline. Source
  bytes (from TMDB, IMDB scraping, or manual admin upload) are uploaded to
  imgbb unmodified (`flask_backend/service/upload.py:14`,
  `upload_image_to_api`), and only the original `data.url` is kept —
  `image_width`/`image_height` are stored, but the file itself is never
  touched.
- `screening.image` (the stored full-resolution URL) is the *only* image
  ever displayed, at every size the site uses it at: 325px (desktop index
  grid, `/movies/posters` gallery), 50px (movie search list thumbnail),
  full-viewport (mobile reels feed), and legitimately large (movie detail
  page hero/carousel).
- imgbb's own `thumb`/`medium` response fields (present in the upload
  response today but never read) were evaluated and are not good enough:
  `thumb` force-crops to a 180x180 square (would mangle portrait posters),
  and `medium` (640x360 in the test) keeps the lossless PNG format, only
  getting to 497KB. A same-dimensions re-encode to WebP got to 16KB — the
  dominant cost is format, not just pixel count.

## Approach

**One universal resized variant, applied at the single upload choke point,
no schema changes.**

- New function `resize_for_display(image_bytes, max_dimension=1200,
  quality=80) -> bytes` in a new module
  `flask_backend/service/image_processing.py`. Resizes so the longer edge
  is `<= max_dimension` (never upscales smaller images), re-encodes to
  WebP. WebP is chosen over JPEG because it keeps alpha natively (no
  background-flatten decision needed) and compressed smaller at equal
  quality in testing (16KB vs 28KB for the same source/dimensions).
- Called from `save_image()` (`flask_backend/service/screening.py:89`),
  before it branches into `upload_image_to_local_disk` /
  `upload_image_to_api`. `save_image()` is the single choke point for
  every image-producing path in the app: `fetch-posters`
  (`poster_pipeline.py:215`), manual admin poster upload/edit
  (`routes/screening.py:308`, `:410`), the scraper-import pipeline
  (`service/screening.py:434`), and cinema-photo upload
  (`routes/admin/cinemas.py:59`). Fixing it here means every current and
  future caller gets the resize automatically — no call site can forget
  it.
- `image`/`image_width`/`image_height` (and `photo`/`photo_width`/
  `photo_height`) keep their current meaning and no migration is needed —
  they just now describe a `<=1200px` WebP file instead of an untouched
  original. Every current display context (325px grid, gallery, 50px
  thumbnail, full-viewport mobile reels, full-container detail-page hero
  capped at `max-height: 100vh`) is comfortably served by this one size —
  confirmed by comparing a 650px WebP q80 render against the 1.3MB
  original side-by-side; no visible quality loss at any of these display
  sizes.

## Backfill

New CLI command, matching the existing `fetch-posters` conventions
(Portuguese `--help` text, `--limit`/`--dry-run`/`--verbose` flags,
`pipeline_runs` tracking): `flask resize-images`.

Iterates `Screening` rows with `image` set and `Cinema` rows with `photo`
set. For each row, decides whether to reprocess using only data already in
the DB row (no download needed to decide):

- **Skip** a row only if *both*: (a) the stored URL ends in `.webp`
  (nothing else in this codebase ever uploads WebP, so this is a reliable
  proxy for "already went through `resize_for_display`"), and (b)
  `max(width, height) <= 1200` using the already-stored `image_width`/
  `image_height` (or `photo_width`/`photo_height`) columns.
- **Reprocess** otherwise: download the current image, run it through
  `resize_for_display`, re-upload via the existing `save_image()` path,
  update the row's URL/width/height columns.

A small-but-already-under-1200px PNG is still reprocessed, because the
format conversion is frequently the bigger win (497KB PNG → 16KB WebP at
the same dimensions in testing). This also makes reruns of the command
cheap/idempotent: a second run touches nothing, since everything it would
have changed already passed both checks on the first run.

Run manually, at the developer's own pace, after this ships — not wired
into deploy, startup, or any scheduled job.

## Error handling

No new failure modes; existing semantics are preserved:

- A corrupt/undecodable image still fails at the existing PIL-open
  validation in `download_image_from_url`
  (`flask_backend/service/screening.py:317`).
- An imgbb upload failure still propagates and falls back to local disk
  exactly as `save_image()` does today
  (`flask_backend/service/screening.py:89-101`).
- `resize_for_display` only processes the first frame of animated input.
  This is a known non-issue: posters aren't animated, and no code path in
  this app uploads animated images today.

## Testing

- New `flask_backend/tests/test_service/test_image_processing.py`:
  `resize_for_display` output dimensions (including the no-upscale case),
  output format, and alpha-channel handling.
- Update `test_upload.py` / `test_screening.py` `save_image()` fixtures
  for the new resize step in the call chain.
- A test for the `resize-images` command's skip-vs-reprocess decision
  (webp+within-bounds → skip; anything else → reprocess) and its
  `--dry-run` behavior.

## Out of scope

`flask_backend/templates/screening/_reels_card.html`'s eager-loading of
the first two mobile reels cards (4 `<img>` requests, no `loading="lazy"`,
no `width`/`height` reserved) is a separate, smaller front-end concern.
Once posters are tens of KB instead of 1.3MB, this stops being the
dominant cause of the "site looks broken" symptom on its own. Deferred to
a separate follow-up issue.
