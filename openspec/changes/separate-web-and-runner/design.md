## Context

The project is a Flask web app (`flask_backend/`) that serves cinema
schedules for Porto Alegre. It has a second, unrelated role: scraping
those schedules from cinema websites. Both concerns currently live in the
same Docker image, which forces heavy scraper dependencies
(beautifulsoup4, aiohttp, google-genai, llama-index, etc.) into an image
that runs on a low-resource VPS and only needs to serve HTTP traffic.

GitHub Actions workflows today SSH into the VPS and run scrapers *inside*
the running web container. This couples the scraper runtime to the VPS:
scrapes fail if the VPS is unreachable, and the container must carry all
scraper code and deps at all times.

## Goals / Non-Goals

**Goals:**

- Eliminate all scraper dependencies from the production Docker image
- Give the runner a clean package boundary with its own requirements file
- Define a stable JSON contract (shared schema) that both sides own
- Replace SSH-based scraping workflows with direct runner execution +
  HTTP API calls
- Rename `flask_backend` → `web` to match the new naming intent

**Non-Goals:**

- Splitting into two separate git repositories
- Changing the scraping logic or adding new cinema sources
- Replacing the SQLite database or storage backend
- Building a public API (the import endpoint is internal, auth-gated)

## Decisions

### D1: Shared schema lives in `shared/schema.py`

The `ScrappedResult` / `ScrappedCinema` / `ScrappedFeature` dataclasses
currently live in `flask_backend/import_json.py` and are imported by
both the web app's import service and the runner. In a monorepo, a
top-level `shared/` module (no Flask, no scraper deps) is the right
home. Both `web/` and `runner/` import from `shared.schema`.

The `parse_to_datetime_string` utility (currently in
`flask_backend/service/shared.py`) moves into `shared/utils.py` since it
is called by `ScrappedFeature.from_jsonable()`.

**Alternative considered:** Duplicate the classes in each package.
Rejected because silent divergence between the two copies would break
the JSON contract without any type error.

### D2: HTTP import API with Bearer token auth

The runner POSTs scraped JSON to `POST /api/import` on the live web app.
Authentication uses a static Bearer token stored as a GitHub Secret
(`IMPORT_API_TOKEN`) and configured via environment variable on the VPS
(`IMPORT_API_TOKEN`).

The request body is the same JSON that `cinemaempoa.py` already prints
to stdout — a list of cinema objects, each with a `features` array. The
web app's existing `import_scrapped_results()` service function handles
persistence unchanged.

**Alternative considered:** Keep SSH, run `flask import-json` via
`docker exec`. Rejected because it leaves the scraper-as-VPS-concern
coupling intact and requires managing SSH keys in CI.

### D3: Poster updates via `PATCH /api/screenings/{id}/poster`

The runner discovers a poster URL (from TMDB or IMDB), then calls
`PATCH /api/screenings/{id}/poster` with `{ "url": "<image_url>" }`. The
web app downloads the image, uploads to imgBB (production) or saves
locally (dev), and stores the result — reusing `download_image_from_url`
and `save_image` which already exist in `web/service/screening.py`.

This keeps image-storage responsibility in the web app (which already
manages `uploads/` and imgBB keys) and keeps the runner concerned only
with discovery.

**Alternative considered:** Runner uploads to imgBB directly and sends
back the imgBB URL. Rejected because it requires the runner to hold the
imgBB API key and duplicates upload logic.

### D4: Runner entry point is `runner/main.py`, no Flask dependency

`runner/main.py` replaces `cinemaempoa.py` as the CLI entry point. It
accepts `--rooms` and `--api-url` / `--api-token` arguments. When run:

1. Scrapes the requested cinemas
2. POSTs to `/api/import`
3. Queries `/api/screenings/missing-posters`
4. For each, tries TMDB then IMDB
5. PATCHes found poster URLs back

This makes the runner a self-contained script:
`pip install -r requirements.runner.txt && python runner/main.py
--rooms capitolio`.

### D5: `flask_backend/` renamed to `web/`

All Python imports updated (`from flask_backend.` → `from web.`). The
Gunicorn CMD in `Dockerfile.prod` changes from
`gunicorn flask_backend:create_app()` to `gunicorn web:create_app()`.
Alembic config and any workflow references also updated.

This is the highest-risk step (many import sites) and should be done as
a single atomic commit to make it easy to revert.

## Risks / Trade-offs

**[Risk] `flask_backend` → `web` rename touches every Python file** →
Mitigation: do the rename with a global find-and-replace in a single
commit; run the test suite before merging.

**[Risk] Import API token leaked in logs** → Mitigation: token only
appears in the `Authorization` header, never echoed in response bodies
or CLI output; GitHub Actions masks secrets in logs automatically.

**[Risk] Runner and shared schema diverge from web app expectations** →
Mitigation: both import from `shared/schema.py`; a structural mismatch
will raise a Python import or type error locally before it reaches CI.

**[Risk] Poster pipeline currently runs on a schedule independent of
scraping** → Mitigation: keep `fetch-posters.yml` as a separate
workflow; runner's poster logic is callable standalone.

**[Trade-off] Web app now requires HTTP reachability for import** →
The VPS must be up for a scrape run to persist. Under the SSH model the
scrape itself could succeed even if the web app was broken (JSON stored
in the container). Accepted: VPS downtime during a scrape is rare and
the JSON can be re-run manually.

## Migration Plan

1. Create `shared/schema.py` — extract DTOs; update
   `web/service/screening.py` import
2. Rename `flask_backend/` → `web/` — global find-and-replace, update
   Dockerfile CMD and alembic.ini
3. Add `IMPORT_API_TOKEN` env var to web app; implement
   `POST /api/import` and `PATCH /api/screenings/{id}/poster` and
   `GET /api/screenings/missing-posters`
4. Build `runner/` package — move `scrapers/`, move poster logic, write
   `runner/main.py`
5. Update `requirements.runner.txt`; trim `requirements.web.txt`
6. Update GitHub Actions workflows — remove SSH steps, add runner steps
7. Deploy updated web app to VPS; set `IMPORT_API_TOKEN` secret; test
   end-to-end; disable old SSH workflows

**Rollback:** The old SSH workflows can be re-enabled at any point;
they are not deleted until the new flow is confirmed working in
production.

## Open Questions

- Should `GET /api/screenings/missing-posters` be a separate endpoint
  or bundled into the runner's post-import step? (Separate endpoint is
  more flexible for future tooling.)
- Does any existing scraper rely on the VPS locale (`pt_BR.UTF-8`)? If
  so, the GHA workflow needs a `locale-gen` step.
