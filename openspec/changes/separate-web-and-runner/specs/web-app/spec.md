## MODIFIED Requirements

### Requirement: Web app module is named `web`

The web application package SHALL be located at `web/` (renamed from
`flask_backend/`). All internal Python imports SHALL use
`from web.xxx import ...`. The Gunicorn entry point SHALL be
`web:create_app()`. Alembic configuration SHALL reference `web/` for
model discovery.

No scraper classes, poster-pipeline logic, TMDB client, or IMDB scraper
SHALL remain in the `web/` package after this change.

#### Scenario: Web app starts under the new module name

- **WHEN** `gunicorn web:create_app()` is executed with the production
  environment variables set
- **THEN** the app starts without ImportError and serves HTTP traffic on
  the configured port

#### Scenario: Alembic migrations run against the renamed package

- **WHEN** `flask db-upgrade` (or `alembic upgrade head`) is run
- **THEN** migrations complete without error and the schema is up to date

#### Scenario: No import of flask_backend remains in web package

- **WHEN** the `web/` source tree is statically scanned for imports
- **THEN** no `from flask_backend` or `import flask_backend` is found

### Requirement: Web app has no scraper or heavy-ML dependencies

`requirements.web.txt` SHALL NOT include beautifulsoup4, aiohttp,
google-genai, llama-index, openai, or any other library whose sole
purpose is HTML scraping or LLM inference. The production Docker image
SHALL be built exclusively from `requirements.web.txt`.

#### Scenario: Web app Docker image builds without scraper deps

- **WHEN** `docker build -f Dockerfile.prod .` is run
- **THEN** the image builds successfully and `pip list` inside the
  container does not include beautifulsoup4 or google-genai

#### Scenario: Web app import-json CLI command is removed

- **WHEN** `flask --app web import-json` is run
- **THEN** Flask reports the command as unknown (the CLI import path is
  replaced by the HTTP API)
