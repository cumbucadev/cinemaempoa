# web/

Flask web application for Cinema Em POA. Serves the public-facing site and provides an authenticated HTTP API for the runner.

## Setup

Install web-only dependencies:

    pip install -r requirements.web.txt

## Environment Variables

Copy `example.env` and configure:

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLite or PostgreSQL URL |
| `SESSION_KEY` | Flask secret key |
| `APP_ENVIRONMENT` | `development` or `production` |
| `UPLOAD_DIR` | Path for local image uploads |
| `IMGBB_API_KEY` | imgBB API key (production image storage) |
| `IMPORT_API_TOKEN` | Bearer token for the runner import/poster APIs |

## Quick Start

    rm development.sqlite
    flask --app web init-db
    flask --app web seed-db
    flask --app web run --debug --host=0.0.0.0

## API Endpoints

The web app exposes authenticated endpoints for the runner (all require `Authorization: Bearer <IMPORT_API_TOKEN>`):

- `POST /api/import` — Receive scraped cinema data and persist screenings
- `GET /api/screenings/missing-posters` — List screenings without a poster that have untried sources
- `PATCH /api/screenings/{id}/poster` — Download a poster URL and update the screening record

## Available CLI Commands

- `flask --app web init-db` — Apply all pending migrations
- `flask --app web db-upgrade [revision]` — Upgrade to a specific revision
- `flask --app web db-downgrade [revision]` — Downgrade to a specific revision
- `flask --app web db-revision --autogenerate -m "message"` — Create a new migration
- `flask --app web generate-sitemap` — Generate the sitemap
- `flask --app web dupe-check` — Check for duplicate screenings
