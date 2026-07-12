## ADDED Requirements

### Requirement: Shared schema module defines the scraping data contract

The project SHALL contain a top-level `shared/` package with a
`schema.py` module defining `ScrappedFeature`, `ScrappedCinema`, and
`ScrappedResult` dataclasses. These classes SHALL have no dependency on
Flask, SQLAlchemy, or any scraper library — only the Python standard
library and `shared/utils.py`.

Both `web/` and `runner/` SHALL import these classes from
`shared.schema`; neither package SHALL define its own copy.

#### Scenario: Web app imports from shared schema

- **WHEN** `web/service/screening.py` is imported
- **THEN** `ScrappedResult`, `ScrappedCinema`, and `ScrappedFeature`
  resolve from `shared.schema` without error

#### Scenario: Runner imports from shared schema

- **WHEN** `runner/main.py` is imported with only
  `requirements.runner.txt` installed
- **THEN** `ScrappedResult`, `ScrappedCinema`, and `ScrappedFeature`
  resolve from `shared.schema` without error

#### Scenario: Shared schema has no web or scraper dependencies

- **WHEN** `shared/schema.py` is imported in an environment with only
  the Python standard library
- **THEN** it imports without error (no Flask, SQLAlchemy, beautifulsoup4,
  or similar deps needed)

### Requirement: Shared utils module contains pure date parsing helpers

The project SHALL contain `shared/utils.py` with the
`parse_to_datetime_string` function (currently at
`flask_backend/service/shared.py`). `shared/schema.py` SHALL import from
`shared/utils.py`.

#### Scenario: parse_to_datetime_string is accessible from shared

- **WHEN** `from shared.utils import parse_to_datetime_string` is
  executed
- **THEN** the function is importable and returns correctly formatted
  datetime strings for valid cinema time inputs
