## 1. Shared Schema

- [x] 1.1 Create `shared/__init__.py`
- [x] 1.2 Move `parse_to_datetime_string` (and any helpers it uses) from
      `flask_backend/service/shared.py` to `shared/utils.py`
- [x] 1.3 Create `shared/schema.py` — extract `ScrappedFeature`,
      `ScrappedCinema`, `ScrappedResult` dataclasses from
      `flask_backend/import_json.py`; update `from_jsonable` to import
      from `shared.utils`
- [x] 1.4 Update `flask_backend/import_json.py` to import DTOs from
      `shared.schema` (keep file as thin re-export or delete after
      downstream references are updated)
- [x] 1.5 Update `flask_backend/service/screening.py` to import DTOs
      from `shared.schema`
- [x] 1.6 Verify tests still pass after shared module extraction

## 2. Rename flask_backend → web

- [x] 2.1 Rename directory `flask_backend/` → `web/` in the filesystem
- [x] 2.2 Global find-and-replace `flask_backend` → `web` across all
      Python source files, config files, and shell scripts
- [x] 2.3 Update `Dockerfile.prod` CMD:
      `gunicorn flask_backend:create_app()` →
      `gunicorn web:create_app()`
- [x] 2.4 Update `alembic.ini` — fix any references to `flask_backend`
      (model import path, script location)
- [x] 2.5 Update `migrations/env.py` — fix `flask_backend` import
- [x] 2.6 Update `docker-compose.*.yml` files if they reference
      `flask_backend` directly
- [x] 2.7 Update `.github/workflows/*.yml` files that reference
      `flask_backend` (e.g. `flask --app flask_backend`)
- [x] 2.8 Run the test suite and fix any remaining import errors

## 3. HTTP Import API

- [x] 3.1 Add `IMPORT_API_TOKEN` to `web/env_config.py` (read from env,
      default `None`)
- [x] 3.2 Create `web/routes/api.py` with a `require_api_token`
      decorator that validates the `Authorization: Bearer <token>` header
- [x] 3.3 Implement `POST /api/import` in `web/routes/api.py` — validate
      token, parse body into `ScrappedResult`, validate cinema slugs,
      call `import_scrapped_results()`, return `{ "created": <count> }`
- [x] 3.4 Register the `api` blueprint in `web/__init__.py`
- [x] 3.5 Add `IMPORT_API_TOKEN` to `example.env`
- [x] 3.6 Write tests for the import endpoint (valid token, wrong token,
      bad JSON, unknown slug)

## 4. HTTP Poster API

- [x] 4.1 Implement `GET /api/screenings/missing-posters` in
      `web/routes/api.py` — return list with `id`, `movie_title`,
      `next_source` for each screening without a poster that still has
      untried sources
- [x] 4.2 Implement `PATCH /api/screenings/{id}/poster` — validate
      token, look up screening, call `download_image_from_url()` +
      `save_image()`, update screening fields, record
      `PosterFetchAttempt`
- [x] 4.3 Write tests for the poster endpoints (found, not found, bad
      URL, screening 404, auth failure)

## 5. Runner Package

- [x] 5.1 Create `runner/__init__.py` and `runner/scrapers/__init__.py`
      and `runner/poster/__init__.py`
- [x] 5.2 Move `scrapers/capitolio.py` →
      `runner/scrapers/capitolio.py`
- [x] 5.3 Move `scrapers/cinebancarios.py` →
      `runner/scrapers/cinebancarios.py`
- [x] 5.4 Move `scrapers/paulo_amorim.py` →
      `runner/scrapers/paulo_amorim.py`
- [x] 5.5 Move `scrapers/sala_redencao.py` →
      `runner/scrapers/sala_redencao.py`
- [x] 5.6 Move `scrapers/llms.py` → `runner/scrapers/llms.py` (if still
      used by any scraper)
- [x] 5.7 Move `flask_backend/service/tmdb.py` →
      `runner/poster/tmdb.py`; remove Flask imports if any
- [x] 5.8 Move `scrapers/imdb.py` → `runner/poster/imdb.py`
- [x] 5.9 Update intra-runner imports so no file imports from `web/` or
      `shared/` except `shared.schema`
- [x] 5.10 Delete `flask_backend/service/runner.py` (logic absorbed by
      runner package)
- [x] 5.11 Delete `flask_backend/service/poster_pipeline.py` (logic
      moves to runner)
- [x] 5.12 Remove `fetch-posters` and `import-json` Flask CLI commands
      from `web/commands.py`

## 6. Runner CLI Entry Point

- [x] 6.1 Write `runner/main.py` with argparse: `--rooms` (required,
      multi-value), `--api-url` (required), `--api-token` (optional,
      falls back to `IMPORT_API_TOKEN` env var), `--skip-posters` (flag)
- [x] 6.2 Implement scrape-and-import flow: instantiate scrapers for
      requested rooms, build `ScrappedResult`, POST to `/api/import`,
      print summary
- [x] 6.3 Implement poster-find flow: GET
      `/api/screenings/missing-posters`, for each try TMDB then IMDB,
      PATCH found URLs back
- [x] 6.4 Confirm `python runner/main.py --help` works in a clean venv
      with only `requirements.runner.txt` installed

## 7. Dependency Files

- [x] 7.1 Create `requirements.runner.txt` — include beautifulsoup4,
      requests, aiohttp, google-genai, pillow, and all other deps needed
      by runner scrapers and poster logic; no Flask or SQLAlchemy
- [x] 7.2 Audit `requirements.web.txt` — remove any dep that is now
      runner-only (beautifulsoup4, aiohttp, llama-index, google-genai,
      openai, etc.)
- [x] 7.3 Verify `Dockerfile.prod` builds successfully and the resulting
      image does not contain scraper deps

## 8. GitHub Actions Workflows

- [x] 8.1 Rewrite `run-spiders.yml`: replace SSH steps with
      `actions/setup-python` + `pip install -r requirements.runner.txt`
      + `python runner/main.py --rooms capitolio sala-redencao
      paulo-amorim --api-url ${{ secrets.APP_URL }} --api-token
      ${{ secrets.IMPORT_API_TOKEN }}`
- [x] 8.2 Rewrite `import-cinebancarios.yml`: same pattern with
      `--rooms cinebancarios`
- [x] 8.3 Rewrite `fetch-posters.yml`: replace SSH with runner
      invocation using `--skip-posters` removed (poster step is now
      integrated into `main.py`) — or retire this workflow if poster
      finding is now part of the scrape workflow
- [x] 8.4 Add `APP_URL` and `IMPORT_API_TOKEN` to GitHub Actions secrets
      documentation in `CONTRIBUTING.md` or `README.md`
- [x] 8.5 Add a locale step to workflows if any scraper requires
      `pt_BR.UTF-8` (verify by running scrapers against live sites in CI)

## 9. Documentation

- [x] 9.1 Update `README.md` to describe the two-app architecture: web
      app (VPS) and runner (GitHub Actions / local)
- [x] 9.2 Update `flask_backend/README.md` → `web/README.md` — document
      web-only setup and env vars
- [x] 9.3 Create `runner/README.md` — document how to run the runner
      locally (`requirements.runner.txt`, CLI args, env vars)
- [x] 9.4 Update `example.env` to document `IMPORT_API_TOKEN`
