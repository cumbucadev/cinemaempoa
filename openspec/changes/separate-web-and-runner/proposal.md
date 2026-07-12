## Why

The project currently mixes two unrelated concerns in a single Docker
image: serving the website and scraping cinema schedules. Scraper
dependencies (beautifulsoup4, aiohttp, google-genai, llama-index, etc.)
account for most of the image size but are only needed during data
collection, not while serving traffic. Moving scraping to GitHub Actions
runners eliminates this bloat and lets the VPS image stay thin.

## What Changes

- Rename `flask_backend/` → `web/` to make the separation of concerns
  explicit
- Extract shared data transfer objects into a new top-level `shared/`
  module
- Move all scraper code from `scrapers/` into a new `runner/` package
  (self-contained, no Flask dep)
- Move poster-finding logic (TMDB + IMDB) from the web app's service
  layer into `runner/`
- Add an authenticated HTTP import API to the web app so the runner can
  push scraped data without SSH
- Add an authenticated HTTP poster API so the runner can report found
  poster URLs without SSH
- Replace SSH-based GitHub Actions workflows with direct Python execution
  - HTTP API calls
- Produce separate `requirements.runner.txt` (scraper deps) and trim
  `requirements.web.txt` (web-only deps)

## Capabilities

### New Capabilities

- `http-import-api`: Authenticated endpoint (`POST /api/import`) that
  accepts scraped cinema screening data as JSON and persists it to the
  database — replaces the `flask import-json` CLI command as the
  runner's entry point
- `http-poster-api`: Authenticated endpoint
  (`PATCH /api/screenings/{id}/poster`) that accepts a poster URL and
  updates the screening record — allows the runner to report poster
  finds without writing to the VPS filesystem
- `runner-package`: Self-contained Python package (`runner/`) containing
  all scrapers, poster-finding logic, and a CLI entry point; no Flask or
  SQLAlchemy dependency; ships with its own `requirements.runner.txt`
- `shared-schema`: Top-level `shared/` module defining the
  `ScrappedResult` / `ScrappedCinema` / `ScrappedFeature` dataclasses
  that govern the JSON contract between runner output and web app input

### Modified Capabilities

- `web-app`: Module renamed from `flask_backend` to `web`; scraper and
  poster-pipeline code removed; only web-serving, DB, and import-service
  code remains

## Impact

- **`flask_backend/` rename**: Every import
  (`from flask_backend.xxx import`) across the codebase must be updated
  to `from web.xxx import`; `WSGI` entry point and Docker CMD also
  updated
- **`scrapers/` removal**: Scraper files move to `runner/scrapers/`;
  `cinemaempoa.py` becomes `runner/main.py`
- **`flask_backend/service/runner.py`**: Deleted (logic absorbed by
  `runner/`)
- **`flask_backend/service/poster_pipeline.py`**: Deleted (logic moves
  to `runner/poster/`)
- **`flask_backend/service/tmdb.py`**: Moves to `runner/poster/tmdb.py`
- **`flask_backend/import_json.py`**: DTOs extracted to
  `shared/schema.py`; remaining import logic stays in
  `web/service/screening.py`
- **`requirements.web.txt`**: Heavy scraper deps removed; should shrink
  significantly
- **`requirements.runner.txt`**: New file containing all scraper +
  poster-finding deps
- **`Dockerfile.prod`**: No changes needed (already uses
  `requirements.web.txt`)
- **GitHub Actions workflows** (`run-spiders.yml`,
  `import-cinebancarios.yml`, `fetch-posters.yml`): SSH steps replaced
  with `actions/setup-python` + direct runner execution + HTTP API calls
- **`alembic.ini` and migrations**: Reference `web/` instead of
  `flask_backend/`
