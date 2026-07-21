# Admin Pipeline Dashboard — Design

Date: 2026-07-21

## Purpose

The admin screen currently has no way to answer two questions:

1. **Pipeline health** — which pipelines have run, when, and did they succeed?
2. **Pipeline content** — what did a specific run actually do? (e.g. "what did
   the last capitolio spider run import?", "which movies did the last
   fetch-movie-metadata run enrich?")

Today, pipelines run as GitHub Actions crons that SSH into the production
server and execute Flask CLI commands (`import-json`, `fetch-posters`,
`fetch-movie-metadata`, `generate-alerts`). The app itself has no concept of
a "run" — there's no record that an invocation happened, succeeded, or
failed. The only existing per-item history lives in `PosterFetchAttempt` and
`MovieMetadataFetchAttempt`, which log individual attempts but don't group
them into a run, and don't cover scraper imports or alert generation at all.

This design adds in-app run tracking: a `PipelineRun` table, correlation of
existing rows to their run, and a three-tier admin UI (index → history →
run detail).

## Scope

Tracked in this version:
- `import-json` (covers the 3-cinema spider workflow, `import-cinebancarios`,
  and `import-cine-cinco` — same CLI command, different invocations)
- `fetch-movie-metadata`
- `fetch-posters`
- `generate-alerts`

Out of scope for this version:
- GitHub Actions API correlation (health/timing comes entirely from in-app
  tracking, not from querying GitHub)
- Maintenance commands: `dupe-check`, `run-dedupper`, `generate-sitemap`,
  `title-cleaning-backfill`
- Retention/pruning — all `PipelineRun` rows are kept indefinitely; the UI
  shows recent runs by default with pagination for older ones

## Data model

### New table: `PipelineRun`

```
id              PK
pipeline_name   str   # "import-json" | "fetch-posters" |
                      # "fetch-movie-metadata" | "generate-alerts"
source          str, nullable
                      # for import-json only: the comma-joined cinema slugs
                      # targeted in that invocation, e.g.
                      # "capitolio,sala-redencao,paulo-amorim" |
                      # "cinebancarios" | "cine-cinco"
                      # null for the other three pipelines
started_at      DateTime, not null
finished_at     DateTime, nullable   # null while the run is in progress
status          str, not null        # "running" | "success" | "warning" |
                                      # "error"
summary         Text (JSON), nullable
                      # the pipeline's result counts, e.g.
                      # {"processed": 82, "errors": 2, ...}
error_message   str, nullable        # set only when status == "error"
                                      # (uncaught exception)
```

**Why `source` instead of always splitting `import-json` into three separate
pipeline names:** the CLI command is identical across all three import
workflows; what differs is which cinema slugs were passed as arguments. Since
they run on very different cadences (every 12h for the 3-cinema group, weekly
for cinebancarios, 4x/day for cine-cinco), lumping them under one "last
import run" health row would hide per-source staleness (e.g. cinebancarios
silently failing for weeks would be masked by cine-cinco's frequent runs).
The dashboard groups and displays health per distinct `(pipeline_name,
source)` pair.

**Stale/interrupted runs:** if a `PipelineRun` has `status == "running"` and
`started_at` is older than 1 hour, the UI displays it as **"interrupted"**
rather than "running" — this covers a container/process being killed
mid-run before it could write `finished_at`. No cleanup job is needed; this
is a display-time computation.

### Correlating "what was imported"

- `Screening` gains a nullable `pipeline_run_id` FK, set at creation time by
  the importer (`Runner.import_scrapped_results`).
- `Alert` gains a nullable `pipeline_run_id` FK, set at creation time by
  `generate-alerts` (`_record_candidate` / `create_alert`).
- `MovieMetadataFetchAttempt` gains a nullable `pipeline_run_id` FK.
- `PosterFetchAttempt` gains a nullable `pipeline_run_id` FK.

No new per-item log tables are needed for the metadata/poster pipelines —
they already function as per-item attempt logs; this just adds one more
column to each. "Movies enriched in run #482" is `MovieMetadataFetchAttempt`
rows with `pipeline_run_id = 482 AND status = "success"`.

### Status computation rules

Computed once, at the end of each run, from the pipeline's existing result
object:

| Pipeline | error | warning | success |
|---|---|---|---|
| `import-json` | uncaught exception / validation failure (invalid JSON, unknown cinema, etc.) | 0 screenings created | ≥1 screening created |
| `fetch-movie-metadata` | uncaught exception | `result.errors > 0` | 0 errors (including "nothing to process") |
| `fetch-posters` | uncaught exception | `result.errors > 0` | 0 errors (including "nothing to process") |
| `generate-alerts` | uncaught exception | *(none — 0 alerts created is a normal outcome)* | always, if it completes |

### Instrumentation

Each CLI command in `flask_backend/commands.py` (`import_json`,
`fetch_movie_metadata`, `fetch_posters`, `generate_alerts`) is updated to:

1. Create a `PipelineRun` row with `status="running"`, `started_at=now()`
   (and `source=` the cinema slugs, for `import_json`) before calling the
   underlying service.
2. Pass `run_id` down into the service call so newly created/attempted rows
   get tagged with it.
3. On successful completion, compute `status` per the table above, set
   `finished_at`, and store `summary` as JSON of the result's counts.
4. On an uncaught exception, catch it at this wrapper level, record
   `status="error"` and `error_message` (truncated), then re-raise so the
   CLI's existing exit behavior is unchanged.

## Admin UI

New blueprint `admin_pipelines` in `flask_backend/routes/admin/pipelines.py`,
following the existing `admin_alerts` pattern (`@login_required`,
`page`/`limit` pagination).

### Routes

- **`GET /admin/pipelines`** — index. One row per tracked `(pipeline_name,
  source)` group: "3-cinema spiders", "cinebancarios", "cine-cinco",
  "Fetch Posters", "Fetch Movie Metadata", "Generate Alerts". Each row shows
  the latest run's status badge, timestamp, and a one-line summary derived
  from `summary` JSON.
- **`GET /admin/pipelines/<pipeline_name>?source=<source>`** — history.
  Paginated table of past `PipelineRun` rows for that pipeline (+ source
  filter when applicable), newest first.
- **`GET /admin/pipelines/<pipeline_name>/<run_id>`** — run detail. Full
  item list for that specific run:
  - `import-json` → screenings created (title, cinema, dates), via
    `Screening.pipeline_run_id`
  - `fetch-movie-metadata` → movies enriched / not-found / errored, via
    `MovieMetadataFetchAttempt.pipeline_run_id`, grouped by status
  - `fetch-posters` → same shape, via `PosterFetchAttempt.pipeline_run_id`
  - `generate-alerts` → alerts created, via `Alert.pipeline_run_id`,
    grouped by rule name

### Navigation

Add a "Pipelines" entry to the admin dropdown in `base.html`, alongside the
existing "Gerenciar Blog" and "Alertas" entries.

## Testing

- Unit tests for the status-rule computation (success / warning / error /
  interrupted) for each of the four pipelines, following the style of
  `test_movie_metadata_pipeline.py` / `test_poster_pipeline.py`.
- Route tests for the three new admin pages under
  `flask_backend/tests/test_routes/test_admin/`, following
  `test_admin_alerts.py`'s pattern: auth required, pagination, empty states.
- No changes to scraper/pipeline business logic itself — only the
  CLI-command wrapping layer (run creation/closing) and new read-side
  queries are new behavior, so existing pipeline tests should be unaffected
  beyond the new `run_id` parameter threading through.

## Migration

A single `flask --app flask_backend db-revision --autogenerate` covering:
- the new `PipelineRun` table
- the four new nullable `pipeline_run_id` FK columns on `Screening`,
  `Alert`, `MovieMetadataFetchAttempt`, `PosterFetchAttempt`
