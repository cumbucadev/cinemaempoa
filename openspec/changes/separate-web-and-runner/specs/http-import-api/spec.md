## ADDED Requirements

### Requirement: Authenticated import endpoint accepts scraped cinema data

The web app SHALL expose `POST /api/import` that accepts a JSON array of
cinema objects in the same format produced by `runner/main.py` and
persists them as screenings via the existing `import_scrapped_results()`
service.

The endpoint SHALL require a Bearer token in the `Authorization` header
matching the `IMPORT_API_TOKEN` environment variable. Requests with a
missing or incorrect token SHALL be rejected with HTTP 401.

#### Scenario: Valid import request persists screenings

- **WHEN** a POST request is made to `/api/import` with a valid Bearer
  token and a well-formed JSON body
- **THEN** the screenings are persisted to the database and the response
  is HTTP 200 with a JSON body `{ "created": <count> }`

#### Scenario: Missing Authorization header is rejected

- **WHEN** a POST request is made to `/api/import` with no
  `Authorization` header
- **THEN** the response is HTTP 401 with a JSON error body

#### Scenario: Wrong token is rejected

- **WHEN** a POST request is made to `/api/import` with an
  `Authorization: Bearer <wrong-token>` header
- **THEN** the response is HTTP 401 with a JSON error body

#### Scenario: Malformed JSON body returns a client error

- **WHEN** a POST request is made to `/api/import` with a valid token
  but an invalid or structurally incorrect JSON body
- **THEN** the response is HTTP 400 with a JSON error body describing the
  problem

#### Scenario: Unknown cinema slug returns a client error

- **WHEN** the JSON body references a cinema `slug` that does not exist
  in the database
- **THEN** the response is HTTP 422 with a JSON error body naming the
  unknown slug

### Requirement: Import API token is configured via environment variable

The web app SHALL read `IMPORT_API_TOKEN` from the environment at
startup. If the variable is not set, the endpoint SHALL remain available
but SHALL reject all requests with HTTP 500 and a log warning, signalling
misconfiguration.

#### Scenario: Token env var not set

- **WHEN** `IMPORT_API_TOKEN` is absent from the environment and a POST
  request arrives at `/api/import`
- **THEN** the response is HTTP 500 and a warning is written to the
  application log
