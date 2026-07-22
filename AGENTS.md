# AGENTS.md

Flask web portal aggregating movie screenings from independent cinemas in
Porto Alegre, Brazil. `scrapers/` holds per-site scraping logic; `flask_backend/`
is the Flask app (routes, services, templates, CLI, migrations).

## Package Manager

- Use **uv**: `uv sync`
- Requires Python 3.14.x (see `.python-version`).
- Copy `example.env` to `.env` before running anything that touches external APIs.

## Commands

| Task | Command |
|------|---------|
| Run dev server | `flask --app flask_backend run --debug` |
| Init DB | `flask --app flask_backend init-db` |
| Seed DB | `flask --app flask_backend seed-db` |
| Create migration | `flask --app flask_backend db-revision --autogenerate -m "message"` |
| Apply migration | `flask --app flask_backend db-upgrade` |
| Run scrapers | `./cinemaempoa.py -r capitolio sala-redencao cinebancarios paulo-amorim cine-cinco > import.json` |
| Import scraped JSON | `flask --app flask_backend import-json /path/to/file.json` |
| Run all tests | `pytest` |
| Run backend tests | `pytest flask_backend/tests` |
| Run scraper tests | `pytest tests/scrapers` |
| Run tests with coverage | `coverage run -m pytest && coverage report -m` |
| Lint | `uv run ruff check --fix` |
| Format | `uv run ruff format` |
| Lint templates | `uv run djlint flask_backend/templates --lint --profile=jinja` |
| Format templates | `uv run djlint --reformat flask_backend/templates --format-css --format-js` |
| Find dead code | `uv run vulture flask_backend scrapers cinemaempoa.py vulture_whitelist.py --exclude "*/tests/*" --min-confidence 80` |
| Check complexity | `uv run xenon --max-absolute B --max-modules A --max-average A flask_backend scrapers --exclude "*/tests/*"` |

Other CLI commands (see `flask_backend/commands.py`): `dupe-check`, `run-dedupper`,
`generate-sitemap`, `fetch-posters`, `poster-review`, `fetch-movie-metadata`,
`movie-metadata-review`, `title-cleaning-report`, `title-cleaning-backfill`, `delete-movie`.

## External References

| Need | File |
|------|------|
| Contributor workflow (Portuguese) | `CONTRIBUTING.md` |
| Scraper site-specific quirks | `scrapers/README.md`, `scrapers/docs/` |
| Test fixtures | `flask_backend/tests/README.md` |
| CI pipeline | `.github/workflows/ci.yml` |
| Deployment | `.github/workflows/deploy-server.yml` |
| Scheduled jobs | `.github/workflows/fetch-movie-metadata.yml`, `fetch-posters.yml`, `import-cinebancarios.yml`, `import-cine-cinco.yml`, `run-spiders.yml`, `update-sitemaps.yml` |
| Production runtime | `docker-compose.production.yml`, `Dockerfile.prod` |
| DB backups | `backup-db.sh` |

## Key Conventions

- `development.sqlite` and `flask_backend.sqlite` are local databases; never treat
their contents as authoritative or commit changes to them as data.
- `pre-commit` runs ruff and djlint on commit: install with `pre-commit install`.
- Run all four lint/format commands above before opening a PR; CI fails on unformatted code.

## Commit Attribution

- Never add an AI/agent co-author trailer (e.g. `Co-Authored-By: Claude ...`) to commits or PRs.
- The human developer is always the sole author and is responsible for every commit.
