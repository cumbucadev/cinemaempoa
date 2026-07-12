## ADDED Requirements

### Requirement: Runner is a self-contained package with no web dependency

The `runner/` directory SHALL be installable with
`pip install -r requirements.runner.txt` alone, with no dependency on
`web/` or any Flask/SQLAlchemy package. The `runner/` package SHALL
contain all scraper classes (previously in `scrapers/`) and all
poster-finding logic (previously in
`flask_backend/service/poster_pipeline.py`,
`flask_backend/service/tmdb.py`, and `scrapers/imdb.py`).

#### Scenario: Runner installs without web dependencies

- **WHEN** `pip install -r requirements.runner.txt` is run in a clean
  virtualenv
- **THEN** `python runner/main.py --help` executes without ImportError

#### Scenario: Runner has no import of flask_backend or web modules

- **WHEN** `runner/` source files are statically scanned for imports
- **THEN** no import of `flask_backend`, `web`, `flask`, or `sqlalchemy`
  is found

### Requirement: Runner CLI accepts rooms and API connection arguments

`runner/main.py` SHALL accept the following CLI arguments:

- `--rooms` (required, one or more of: `capitolio`, `sala-redencao`,
  `cinebancarios`, `paulo-amorim`)
- `--api-url` (required): base URL of the web app (e.g.
  `https://cinemaempoa.com.br`)
- `--api-token` (required): Bearer token for the import API; MAY
  alternatively be read from `IMPORT_API_TOKEN` env var
- `--skip-posters` (optional flag): if set, skips the poster-finding
  step after import

#### Scenario: Scrape and import completes successfully

- **WHEN** `python runner/main.py --rooms capitolio --api-url
  https://example.com --api-token secret` is run
- **THEN** the runner scrapes Capitólio, POSTs to `/api/import`, and
  prints a summary of created screenings

#### Scenario: Unknown room argument is rejected

- **WHEN** `--rooms` includes a value not in the allowed list
- **THEN** the CLI exits with a non-zero status and an informative error
  message

#### Scenario: Missing API token causes early exit

- **WHEN** neither `--api-token` nor `IMPORT_API_TOKEN` env var is set
- **THEN** the CLI exits with a non-zero status before making any network
  request

### Requirement: Runner reports poster discovery results to the web app

After a successful import, the runner SHALL (unless `--skip-posters` is
passed):

1. Call `GET /api/screenings/missing-posters` to retrieve screenings
   needing posters
2. For each, attempt TMDB first, then IMDB
3. For each found URL, call `PATCH /api/screenings/{id}/poster` with the
   URL and source name

#### Scenario: Poster found via TMDB is reported

- **WHEN** TMDB returns a poster URL for a screening's movie title
- **THEN** the runner calls `PATCH /api/screenings/{id}/poster` with
  `{ "url": "<tmdb_url>", "source": "tmdb" }`

#### Scenario: TMDB misses, IMDB found

- **WHEN** TMDB returns no result but IMDB scraping finds a poster URL
- **THEN** the runner calls `PATCH /api/screenings/{id}/poster` with
  `{ "url": "<imdb_url>", "source": "imdb" }`

#### Scenario: No poster found from any source

- **WHEN** both TMDB and IMDB return no result for a screening
- **THEN** the runner logs the screening as unfound and continues without
  calling the PATCH endpoint

### Requirement: Runner scrapers are organised under `runner/scrapers/`

The scraper classes (Capitólio, Sala Redenção, CineBancários,
Cinemateca Paulo Amorim) SHALL live at `runner/scrapers/<name>.py`,
mirroring the current `scrapers/` structure. The `runner/poster/`
sub-package SHALL contain `tmdb.py` and `imdb.py`.

#### Scenario: Scraper imports resolve inside runner package

- **WHEN** `from runner.scrapers.capitolio import Capitolio` is executed
- **THEN** the class is importable without error
