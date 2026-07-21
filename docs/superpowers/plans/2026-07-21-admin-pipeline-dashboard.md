# Admin Pipeline Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin screen a pipeline health dashboard (did each pipeline run, when, did it succeed) and a drill-down view of exactly what each run imported/enriched/created.

**Architecture:** A new `PipelineRun` table records one row per CLI invocation (`import-json`, `fetch-posters`, `fetch-movie-metadata`, `generate-alerts`), with a computed status (`running` / `success` / `warning` / `error`, displayed as `interrupted` if stuck). Existing rows created by these pipelines (`Screening`, `Alert`, `MovieMetadataFetchAttempt`, `PosterFetchAttempt`) get a nullable `pipeline_run_id` FK so a run's exact output can be queried directly, no timestamp-window guessing. A new `admin_pipelines` blueprint exposes a three-tier UI: index (latest status per pipeline) → history (paginated past runs) → detail (full item list for one run).

**Tech Stack:** Flask, SQLAlchemy, Alembic, pytest, Jinja2/Bootstrap templates (matches existing `flask_backend` conventions).

## Global Constraints

- Follow the codebase's existing repository/service/route layering — no new architectural layers.
- All new user-facing text is in Portuguese, matching every other admin page.
- `pipeline_run_id` columns are nullable everywhere — pre-existing rows and non-pipeline call sites (manual screening creation, dedupper, alert repointing) are unaffected.
- No GitHub Actions API integration, no retention/pruning, no tracking of `dupe-check` / `run-dedupper` / `generate-sitemap` / `title-cleaning-backfill` — all explicitly out of scope per the spec (`docs/superpowers/specs/2026-07-21-admin-pipeline-dashboard-design.md`).
- Run `uv run ruff check --fix` and `uv run ruff format` before considering any task's code final; run `uv run djlint --reformat flask_backend/templates --format-css --format-js` after any template changes.

---

## Task 1: `PipelineRun` model, migration, and repository

**Files:**
- Modify: `flask_backend/models.py`
- Create: `migrations/versions/20260721_000000_add_pipeline_runs.py`
- Create: `flask_backend/repository/pipeline_runs.py`
- Modify: `flask_backend/tests/conftest.py`
- Create: `flask_backend/tests/test_repository/__init__.py`
- Create: `flask_backend/tests/test_repository/test_pipeline_runs.py`

**Interfaces:**
- Produces (used by every later task):
  - `flask_backend.models.PipelineRun` — columns `id, pipeline_name: str, source: Optional[str], started_at: datetime, finished_at: Optional[datetime], status: str, summary: Optional[str], error_message: Optional[str]`
  - `flask_backend.models.PIPELINE_RUN_STATUSES = ["running", "success", "warning", "error"]`
  - `Screening.pipeline_run_id`, `Alert.pipeline_run_id`, `MovieMetadataFetchAttempt.pipeline_run_id`, `PosterFetchAttempt.pipeline_run_id` — all nullable `Integer` FK columns to `pipeline_runs.id`
  - `flask_backend.repository.pipeline_runs.start(pipeline_name: str, source: Optional[str] = None) -> PipelineRun`
  - `flask_backend.repository.pipeline_runs.set_source(run_id: int, source: str) -> None`
  - `flask_backend.repository.pipeline_runs.finish(run_id: int, status: str, summary: Optional[str] = None, error_message: Optional[str] = None) -> PipelineRun`
  - `flask_backend.repository.pipeline_runs.get_by_id(run_id: int) -> Optional[PipelineRun]`
  - `flask_backend.repository.pipeline_runs.get_latest_by_pipeline(pipeline_name: str, source: Optional[str] = None) -> Optional[PipelineRun]`
  - `flask_backend.repository.pipeline_runs.get_paginated(pipeline_name: str, current_page: int, per_page: int, source: Optional[str] = None) -> Tuple[list[PipelineRun], int, int]`
  - `flask_backend.repository.pipeline_runs.is_interrupted(run: PipelineRun) -> bool`
  - `flask_backend.repository.pipeline_runs.display_status(run: PipelineRun) -> str` — returns `run.status`, except `"interrupted"` when `is_interrupted(run)` is true

- [ ] **Step 1: Write the failing repository tests**

Create `flask_backend/tests/test_repository/__init__.py` (empty file).

Create `flask_backend/tests/test_repository/test_pipeline_runs.py`:

```python
from datetime import datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import PipelineRun
from flask_backend.repository import pipeline_runs


class TestStart:
    def test_creates_running_run(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")

            assert run.id is not None
            assert run.pipeline_name == "fetch-posters"
            assert run.source is None
            assert run.status == "running"
            assert run.started_at is not None
            assert run.finished_at is None

    def test_stores_source_when_given(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json", source="cine-cinco")
            assert run.source == "cine-cinco"


class TestSetSource:
    def test_updates_source_on_existing_run(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")
            pipeline_runs.set_source(run.id, "capitolio,paulo-amorim,sala-redencao")

            refreshed = db_session.query(PipelineRun).filter_by(id=run.id).one()
            assert refreshed.source == "capitolio,paulo-amorim,sala-redencao"


class TestFinish:
    def test_sets_status_finished_at_and_summary(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-movie-metadata")

            finished = pipeline_runs.finish(
                run.id, status="success", summary='{"processed": 5}'
            )

            assert finished.status == "success"
            assert finished.finished_at is not None
            assert finished.summary == '{"processed": 5}'
            assert finished.error_message is None

    def test_sets_error_message_on_error(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")

            finished = pipeline_runs.finish(
                run.id, status="error", error_message="boom"
            )

            assert finished.status == "error"
            assert finished.error_message == "boom"


class TestGetById:
    def test_returns_none_when_missing(self, app):
        with app.app_context():
            assert pipeline_runs.get_by_id(99999) is None

    def test_returns_run_when_present(self, app):
        with app.app_context():
            run = pipeline_runs.start("generate-alerts")
            found = pipeline_runs.get_by_id(run.id)
            assert found is not None
            assert found.id == run.id


class TestGetLatestByPipeline:
    def test_returns_none_when_no_runs(self, app):
        with app.app_context():
            assert pipeline_runs.get_latest_by_pipeline("fetch-posters") is None

    def test_returns_most_recent_run(self, app):
        with app.app_context():
            older = pipeline_runs.start("fetch-posters")
            older.started_at = datetime.now() - timedelta(hours=2)
            db_session.commit()

            newer = pipeline_runs.start("fetch-posters")

            latest = pipeline_runs.get_latest_by_pipeline("fetch-posters")
            assert latest.id == newer.id

    def test_filters_by_source(self, app):
        with app.app_context():
            run_a = pipeline_runs.start("import-json", source="cinebancarios")
            pipeline_runs.start("import-json", source="cine-cinco")

            latest = pipeline_runs.get_latest_by_pipeline(
                "import-json", source="cinebancarios"
            )
            assert latest.id == run_a.id


class TestGetPaginated:
    def test_paginates_and_orders_newest_first(self, app):
        with app.app_context():
            for i in range(3):
                run = pipeline_runs.start("fetch-posters")
                run.started_at = datetime.now() - timedelta(hours=3 - i)
                db_session.commit()

            runs, pages, total = pipeline_runs.get_paginated(
                "fetch-posters", current_page=1, per_page=2
            )

            assert total == 3
            assert pages == 2
            assert len(runs) == 2
            assert runs[0].started_at > runs[1].started_at

    def test_filters_by_source(self, app):
        with app.app_context():
            pipeline_runs.start("import-json", source="cinebancarios")
            pipeline_runs.start("import-json", source="cine-cinco")

            runs, pages, total = pipeline_runs.get_paginated(
                "import-json", current_page=1, per_page=20, source="cine-cinco"
            )

            assert total == 1
            assert runs[0].source == "cine-cinco"


class TestDisplayStatus:
    def test_running_recent_stays_running(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            assert pipeline_runs.display_status(run) == "running"

    def test_running_stale_shows_interrupted(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            run.started_at = datetime.now() - timedelta(hours=2)
            db_session.commit()

            assert pipeline_runs.is_interrupted(run) is True
            assert pipeline_runs.display_status(run) == "interrupted"

    def test_finished_status_passes_through(self, app):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            pipeline_runs.finish(run.id, status="warning")
            run = pipeline_runs.get_by_id(run.id)

            assert pipeline_runs.display_status(run) == "warning"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_pipeline_runs.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'flask_backend.repository.pipeline_runs'` (and `PipelineRun` not importable from `models`).

- [ ] **Step 3: Add `PipelineRun` model and `pipeline_run_id` columns**

In `flask_backend/models.py`, add the new status constant near the top, right after `ALERT_STATUSES = ["pending", "posted", "dismissed"]` (line 26):

```python
ALERT_STATUSES = ["pending", "posted", "dismissed"]

PIPELINE_RUN_STATUSES = ["running", "success", "warning", "error"]
```

Add `pipeline_run_id` to `Screening` — modify the class (currently lines 137–171) so the column block reads:

```python
    core_alerts_evaluated_at = Column(DateTime, nullable=True, index=True)
    # Set when this screening was created by a tracked pipeline run (e.g.
    # import-json). NULL for screenings created manually via /admin or by
    # scripts/dedupper.py.
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    movie: Mapped["Movie"] = relationship(back_populates="screenings")
```

Add `PipelineRun` class right before `PosterFetchAttempt` (currently line 184), and add `pipeline_run_id` to both `PosterFetchAttempt` and `MovieMetadataFetchAttempt`:

```python
class PipelineRun(Base):
    """One row per invocation of a tracked pipeline CLI command (import-json,
    fetch-posters, fetch-movie-metadata, generate-alerts). Powers the
    /admin/pipelines health dashboard and lets a specific run's output be
    looked up exactly via the pipeline_run_id columns on Screening, Alert,
    MovieMetadataFetchAttempt and PosterFetchAttempt, instead of guessing
    from timestamps."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)
    # e.g. "import-json", "fetch-posters", "fetch-movie-metadata",
    # "generate-alerts" - the flask CLI command name.
    pipeline_name = Column(String, nullable=False, index=True)
    # For "import-json" only: the sorted, comma-joined cinema slugs targeted
    # by this invocation (e.g. "capitolio,paulo-amorim,sala-redencao"),
    # since the same CLI command covers cinema groups that run on very
    # different schedules. NULL for the other three pipelines, and also
    # NULL for import-json runs that failed before the JSON could be
    # parsed (the cinema slugs aren't known yet at that point).
    source = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False)  # see PIPELINE_RUN_STATUSES
    # JSON-encoded result counts (e.g. {"processed": 5, "errors": 1}).
    summary = Column(Text, nullable=True)
    error_message = Column(String, nullable=True)


class PosterFetchAttempt(Base):
    """Tracks each attempt to fetch a poster for a screening from an external source.

    A screening that has failed attempts for every source in POSTER_SOURCES
    (and still has no image) is considered as needing manual review.
    """

    __tablename__ = "poster_fetch_attempts"

    id = Column(Integer, primary_key=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), nullable=False)
    source = Column(String, nullable=False)  # e.g. "tmdb", "imdb"
    status = Column(String, nullable=False)  # "success", "not_found", "error"
    attempted_at = Column(DateTime, nullable=False)
    error_message = Column(String, nullable=True)
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    screening: Mapped["Screening"] = relationship()


class MovieMetadataFetchAttempt(Base):
    """Tracks each attempt to fetch metadata (director, genres) for a movie
    from an external source.

    A movie that has failed attempts for every source in MOVIE_METADATA_SOURCES
    is considered as needing manual review.
    """

    __tablename__ = "movie_metadata_fetch_attempts"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    source = Column(String, nullable=False)  # e.g. "tmdb"
    status = Column(String, nullable=False)  # "success", "not_found", "error"
    attempted_at = Column(DateTime, nullable=False)
    error_message = Column(String, nullable=True)
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    movie: Mapped["Movie"] = relationship()
```

Add `pipeline_run_id` to `Alert` — modify the column block (currently lines 223–249) so it reads:

```python
    resolved_at = Column(DateTime, nullable=True)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Set when this alert was created by a tracked generate-alerts run.
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    movie: Mapped["Movie"] = relationship()
```

- [ ] **Step 4: Write the migration**

Create `migrations/versions/20260721_000000_add_pipeline_runs.py`:

```python
"""Adds pipeline run tracking (pipeline_runs table) so the admin dashboard
can show pipeline health (did it run, when, did it succeed) and correlate
what each run touched, by tagging screenings, alerts,
movie_metadata_fetch_attempts and poster_fetch_attempts rows with the run
that created them.

Revision ID: 20260721_000000
Revises: 20260719_000001
Create Date: 2026-07-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260721_000000"
down_revision: Union[str, None] = "20260719_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pipeline_runs_pipeline_name", "pipeline_runs", ["pipeline_name"]
    )

    op.add_column(
        "screenings", sa.Column("pipeline_run_id", sa.Integer(), nullable=True)
    )
    with op.batch_alter_table("screenings") as batch_op:
        batch_op.create_foreign_key(
            "fk_screenings_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index("ix_screenings_pipeline_run_id", "screenings", ["pipeline_run_id"])

    op.add_column("alerts", sa.Column("pipeline_run_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.create_foreign_key(
            "fk_alerts_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index("ix_alerts_pipeline_run_id", "alerts", ["pipeline_run_id"])

    op.add_column(
        "movie_metadata_fetch_attempts",
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("movie_metadata_fetch_attempts") as batch_op:
        batch_op.create_foreign_key(
            "fk_movie_metadata_fetch_attempts_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index(
        "ix_movie_metadata_fetch_attempts_pipeline_run_id",
        "movie_metadata_fetch_attempts",
        ["pipeline_run_id"],
    )

    op.add_column(
        "poster_fetch_attempts",
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("poster_fetch_attempts") as batch_op:
        batch_op.create_foreign_key(
            "fk_poster_fetch_attempts_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index(
        "ix_poster_fetch_attempts_pipeline_run_id",
        "poster_fetch_attempts",
        ["pipeline_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_poster_fetch_attempts_pipeline_run_id", table_name="poster_fetch_attempts"
    )
    with op.batch_alter_table("poster_fetch_attempts") as batch_op:
        batch_op.drop_constraint(
            "fk_poster_fetch_attempts_pipeline_run_id_pipeline_runs",
            type_="foreignkey",
        )
    op.drop_column("poster_fetch_attempts", "pipeline_run_id")

    op.drop_index(
        "ix_movie_metadata_fetch_attempts_pipeline_run_id",
        table_name="movie_metadata_fetch_attempts",
    )
    with op.batch_alter_table("movie_metadata_fetch_attempts") as batch_op:
        batch_op.drop_constraint(
            "fk_movie_metadata_fetch_attempts_pipeline_run_id_pipeline_runs",
            type_="foreignkey",
        )
    op.drop_column("movie_metadata_fetch_attempts", "pipeline_run_id")

    op.drop_index("ix_alerts_pipeline_run_id", table_name="alerts")
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_constraint(
            "fk_alerts_pipeline_run_id_pipeline_runs", type_="foreignkey"
        )
    op.drop_column("alerts", "pipeline_run_id")

    op.drop_index("ix_screenings_pipeline_run_id", table_name="screenings")
    with op.batch_alter_table("screenings") as batch_op:
        batch_op.drop_constraint(
            "fk_screenings_pipeline_run_id_pipeline_runs", type_="foreignkey"
        )
    op.drop_column("screenings", "pipeline_run_id")

    op.drop_index("ix_pipeline_runs_pipeline_name", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
```

- [ ] **Step 5: Write the repository module**

Create `flask_backend/repository/pipeline_runs.py`:

```python
from datetime import datetime, timedelta
from math import ceil
from typing import Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import PipelineRun

# A "running" run older than this is considered dead (its process was
# killed before it could write finished_at) rather than genuinely in
# progress. Display-only - never mutates the stored status.
INTERRUPTED_THRESHOLD = timedelta(hours=1)


def start(pipeline_name: str, source: Optional[str] = None) -> PipelineRun:
    run = PipelineRun(
        pipeline_name=pipeline_name,
        source=source,
        started_at=datetime.now(),
        status="running",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def set_source(run_id: int, source: str) -> None:
    db_session.query(PipelineRun).filter(PipelineRun.id == run_id).update(
        {"source": source}
    )
    db_session.commit()


def finish(
    run_id: int,
    status: str,
    summary: Optional[str] = None,
    error_message: Optional[str] = None,
) -> PipelineRun:
    run = db_session.query(PipelineRun).filter(PipelineRun.id == run_id).one()
    run.status = status
    run.finished_at = datetime.now()
    run.summary = summary
    run.error_message = error_message
    db_session.commit()
    db_session.refresh(run)
    return run


def get_by_id(run_id: int) -> Optional[PipelineRun]:
    return db_session.query(PipelineRun).filter(PipelineRun.id == run_id).first()


def get_latest_by_pipeline(
    pipeline_name: str, source: Optional[str] = None
) -> Optional[PipelineRun]:
    query = db_session.query(PipelineRun).filter(
        PipelineRun.pipeline_name == pipeline_name
    )
    if source is not None:
        query = query.filter(PipelineRun.source == source)
    return query.order_by(PipelineRun.started_at.desc()).first()


def get_paginated(
    pipeline_name: str,
    current_page: int,
    per_page: int,
    source: Optional[str] = None,
) -> Tuple[list[PipelineRun], int, int]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(PipelineRun).filter(
        PipelineRun.pipeline_name == pipeline_name
    )
    if source is not None:
        query = query.filter(PipelineRun.source == source)

    runs = (
        query.order_by(PipelineRun.started_at.desc())
        .limit(per_page)
        .offset(offset_value)
        .all()
    )

    count_query = db_session.query(func.count(PipelineRun.id)).filter(
        PipelineRun.pipeline_name == pipeline_name
    )
    if source is not None:
        count_query = count_query.filter(PipelineRun.source == source)
    total_count = count_query.scalar()
    total_pages = ceil(total_count / per_page) if total_count else 0

    return (runs, total_pages, total_count)


def is_interrupted(run: PipelineRun) -> bool:
    return run.status == "running" and (
        datetime.now() - run.started_at > INTERRUPTED_THRESHOLD
    )


def display_status(run: PipelineRun) -> str:
    """Status to show in the UI - "running" becomes "interrupted" once stale."""
    if is_interrupted(run):
        return "interrupted"
    return run.status
```

- [ ] **Step 6: Clean up `PipelineRun` rows between tests**

In `flask_backend/tests/conftest.py`, add `PipelineRun` to the imports in `clean_db` (currently lines 38–50) and delete it. Modify the import block and add a delete call:

```python
        from flask_backend.models import (
            Alert,
            BlogPost,
            Cinema,
            Collection,
            Country,
            Director,
            Genre,
            Movie,
            MovieMetadataFetchAttempt,
            PipelineRun,
            PosterFetchAttempt,
            Screening,
            ScreeningDate,
            User,
            movie_countries,
            movie_directors,
            movie_genres,
        )

        db_session.query(Alert).delete()
        db_session.query(BlogPost).delete()
        db_session.query(User).delete()
        db_session.query(MovieMetadataFetchAttempt).delete()
        db_session.query(PosterFetchAttempt).delete()
        db_session.query(PipelineRun).delete()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_pipeline_runs.py -v`
Expected: PASS (all tests green)

Also run the full suite once to confirm nothing else broke from the schema change:

Run: `pytest flask_backend/tests -x -q`
Expected: PASS

- [ ] **Step 8: Lint and format**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no errors

- [ ] **Step 9: Commit**

```bash
git add flask_backend/models.py flask_backend/repository/pipeline_runs.py \
  flask_backend/tests/conftest.py flask_backend/tests/test_repository \
  migrations/versions/20260721_000000_add_pipeline_runs.py
git commit -m "feat: add PipelineRun model, migration, and repository"
```

---

## Task 2: Instrument the `import-json` command

**Files:**
- Modify: `flask_backend/repository/screenings.py:84-113` (add `pipeline_run_id` param to `create`)
- Modify: `flask_backend/service/screening.py:151-155` (thread `pipeline_run_id` through `import_scrapped_results`)
- Modify: `flask_backend/service/runner.py` (thread `pipeline_run_id` through `Runner.import_scrapped_results`)
- Modify: `flask_backend/commands.py:38-64` (wrap `import_json` command)
- Modify: `flask_backend/tests/test_service/test_commands.py`

**Interfaces:**
- Consumes: `flask_backend.repository.pipeline_runs.start`, `.set_source`, `.finish` (Task 1)
- Produces: `Screening` rows created via the import path now carry `pipeline_run_id`; every `import-json` invocation creates exactly one `PipelineRun` row with `pipeline_name="import-json"`.

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_service/test_commands.py`, inside `class TestImportJsonCommand` (after the existing `test_success_imports_screenings` method — keep existing imports, add `from flask_backend.db import db_session` and `from flask_backend.models import PipelineRun, Screening` at the top of the file):

```python
    def test_success_creates_pipeline_run_with_source_and_summary(
        self, app, runner, tmp_path, setup_cinemas
    ):
        payload = [
            {
                "url": "",
                "cinema": "Cinemateca Capitólio",
                "slug": "capitolio",
                "features": [
                    {
                        "poster": "",
                        "time": ["2026-08-01T19:00"],
                        "title": "Filme via CLI 2",
                        "original_title": "",
                        "price": "",
                        "director": "",
                        "classification": "",
                        "general_info": "",
                        "excerpt": "um filme",
                        "read_more": "",
                    }
                ],
            }
        ]
        json_path = tmp_path / "valid2.json"
        json_path.write_text(json.dumps(payload))

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="import-json"
            ).one()
            assert run.status == "success"
            assert run.source == "capitolio"
            assert run.finished_at is not None
            assert '"created": 1' in run.summary

            screening = db_session.query(Screening).filter_by(
                pipeline_run_id=run.id
            ).one()
            assert screening.movie.title == "Filme via CLI 2"

    def test_zero_screenings_created_marks_run_as_warning(
        self, app, runner, tmp_path, setup_cinemas
    ):
        payload = [
            {
                "url": "",
                "cinema": "Cinemateca Capitólio",
                "slug": "capitolio",
                "features": [],
            }
        ]
        json_path = tmp_path / "empty.json"
        json_path.write_text(json.dumps(payload))

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="import-json"
            ).one()
            assert run.status == "warning"

    def test_invalid_json_marks_run_as_error(self, app, runner, tmp_path):
        json_path = tmp_path / "bad.json"
        json_path.write_text("not-valid-json{")

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="import-json"
            ).one()
            assert run.status == "error"
            assert run.source is None
            assert "inválido" in run.error_message

    def test_unknown_cinema_marks_run_as_error(self, app, runner, tmp_path):
        payload = [
            {
                "url": "",
                "cinema": "Inexistente",
                "slug": "inexistente",
                "features": [],
            }
        ]
        json_path = tmp_path / "unknown-cinema2.json"
        json_path.write_text(json.dumps(payload))

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="import-json"
            ).one()
            assert run.status == "error"
            assert "não encontrada" in run.error_message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k ImportJson -v`
Expected: FAIL — no `PipelineRun` rows are created yet (`NoResultFound`).

- [ ] **Step 3: Add `pipeline_run_id` to `repository/screenings.py::create`**

Modify the `create` function (`flask_backend/repository/screenings.py:84-113`) to accept and store the new param:

```python
def create(
    movie_id: int,
    description: str,
    cinema_id: int,
    screening_dates: List[ScreeningDate],
    image: Optional[str],
    image_width: Optional[int],
    image_height: Optional[int],
    is_draft: Optional[bool] = False,
    image_alt: Optional[bool] = None,
    url_origin: Optional[str] = None,
    raw_title: Optional[str] = None,
    title_cleaning_rules: Optional[str] = None,
    pipeline_run_id: Optional[int] = None,
) -> Screening:
    screening = Screening(
        movie_id=movie_id,
        cinema_id=cinema_id,
        dates=screening_dates,
        image=image,
        image_alt=image_alt,
        image_width=image_width,
        image_height=image_height,
        description=description,
        draft=is_draft,
        url=url_origin,
        raw_title=raw_title,
        title_cleaning_rules=title_cleaning_rules,
        pipeline_run_id=pipeline_run_id,
        created_at=datetime.now(),
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening
```

- [ ] **Step 4: Thread `pipeline_run_id` through the screening import service**

In `flask_backend/service/screening.py`, change the function signature at line 151 and the `create_screening` call at lines 205-219:

```python
def import_scrapped_results(
    scrapped_results: ScrappedResult, current_app, pipeline_run_id: Optional[int] = None
):
```

(`flask_backend/service/screening.py` already has `from typing import List, Optional, Tuple` at the top — no import change needed.)

```python
                create_screening(
                    movie_id=movie.id,
                    description=description,
                    cinema_id=cinema.id,
                    screening_dates=screenings_dates,
                    image=image_filename,
                    image_width=image_width,
                    image_height=image_height,
                    is_draft=False,
                    image_alt=None,
                    url_origin=scrapped_feature.read_more,
                    raw_title=title_cleaning_result.raw_title,
                    title_cleaning_rules=",".join(title_cleaning_result.matched_rules)
                    or None,
                    pipeline_run_id=pipeline_run_id,
                )
```

- [ ] **Step 5: Thread `pipeline_run_id` through `Runner`**

Replace `flask_backend/service/runner.py` in full:

```python
from typing import Optional

from flask_backend.import_json import ScrappedResult
from flask_backend.service.screening import import_scrapped_results


class Runner:
    def parse_scrapped_json(self, features):
        self.scrapped_results: ScrappedResult = ScrappedResult.from_jsonable(features)

    def import_scrapped_results(self, current_app, pipeline_run_id: Optional[int] = None):
        return import_scrapped_results(
            self.scrapped_results, current_app, pipeline_run_id=pipeline_run_id
        )
```

- [ ] **Step 6: Wrap the `import-json` command**

Replace the `import_json` command in `flask_backend/commands.py` (currently lines 38-64):

```python
def _run_import_json(run, json_path):
    from flask_backend.repository import pipeline_runs

    with open(json_path) as json_file:
        try:
            parsed_json = json.load(json_file)
        except (json.decoder.JSONDecodeError, UnicodeDecodeError):
            message = "Arquivo .json inválido ou não encontrado"
            pipeline_runs.finish(run.id, status="error", error_message=message)
            click.echo(message, err=True)
            return

    runner = Runner()
    try:
        runner.parse_scrapped_json(parsed_json)
    except Exception:
        message = "Arquivo .json com estrutura inválida para importação"
        pipeline_runs.finish(run.id, status="error", error_message=message)
        click.echo(message, err=True)
        return

    slugs = sorted({c.slug for c in runner.scrapped_results.cinemas})
    pipeline_runs.set_source(run.id, ",".join(slugs))

    # validate all cinemas exist in db
    for json_cinema in runner.scrapped_results.cinemas:
        cinema = get_cinema_by_slug(json_cinema.slug)
        if cinema is None:
            message = f"Sala {json_cinema.slug} não encontrada."
            pipeline_runs.finish(run.id, status="error", error_message=message)
            click.echo(message, err=True)
            return

    # all validations passed, import screenings :)
    created_features = runner.import_scrapped_results(
        current_app, pipeline_run_id=run.id
    )
    status = "warning" if created_features == 0 else "success"
    pipeline_runs.finish(
        run.id, status=status, summary=json.dumps({"created": created_features})
    )
    click.echo(f"«{created_features}» sessões criadas com sucesso!")


@click.command("import-json")
@click.argument("json_path")
def import_json(json_path):
    from flask_backend.repository import pipeline_runs

    run = pipeline_runs.start("import-json")
    try:
        _run_import_json(run, json_path)
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k ImportJson -v`
Expected: PASS

Run the full suite to confirm the two other `create_screening` call sites (`routes/screening.py`, `scripts/dedupper.py`) are unaffected:

Run: `pytest flask_backend/tests -x -q`
Expected: PASS

- [ ] **Step 8: Lint and format**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no errors

- [ ] **Step 9: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/service/screening.py \
  flask_backend/service/runner.py flask_backend/commands.py \
  flask_backend/tests/test_service/test_commands.py
git commit -m "feat: track import-json runs in PipelineRun"
```

---

## Task 3: Instrument the `fetch-movie-metadata` command

**Files:**
- Modify: `flask_backend/repository/movie_metadata_fetch_attempts.py:12-28` (add `pipeline_run_id` param to `create`)
- Modify: `flask_backend/service/movie_metadata_pipeline.py` (thread `pipeline_run_id` through `run_pipeline`)
- Modify: `flask_backend/commands.py` (wrap `fetch_movie_metadata` command)
- Modify: `flask_backend/tests/test_service/test_movie_metadata_pipeline.py`
- Modify: `flask_backend/tests/test_service/test_commands.py`

**Interfaces:**
- Consumes: `flask_backend.repository.pipeline_runs.start`, `.finish` (Task 1)
- Produces: `MovieMetadataFetchAttempt` rows now carry `pipeline_run_id` when `run_pipeline(..., pipeline_run_id=...)` is passed one.

- [ ] **Step 1: Write the failing unit test for attempt tagging**

Add to `flask_backend/tests/test_service/test_movie_metadata_pipeline.py`, inside `class TestRunPipeline`:

```python
    def test_attempts_are_tagged_with_pipeline_run_id(self, client, app):
        with client.application.app_context():
            movie = _create_movie("Filme Tagueado", "filme-tagueado")

            tmdb_client = _tmdb_client(search_result=None)
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                run_pipeline(pipeline_run_id=42)

            attempt = (
                db_session.query(MovieMetadataFetchAttempt)
                .filter(MovieMetadataFetchAttempt.movie_id == movie.id)
                .one()
            )
            assert attempt.pipeline_run_id == 42
```

(This uses `MovieMetadataFetchAttempt`, already imported at the top of the file, and `db_session`, already imported.)

Add to `flask_backend/tests/test_service/test_commands.py`, inside `class TestFetchMovieMetadataCommand` (add `from flask_backend.models import PipelineRun` to the top-level imports if not already added in Task 2):

```python
    def test_creates_pipeline_run_with_success_status(self, app, runner):
        result_obj = MetadataPipelineResult(processed=5, metadata_found=5, errors=0)
        with patch(
            "flask_backend.service.movie_metadata_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-movie-metadata"])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="fetch-movie-metadata"
            ).one()
            assert run.status == "success"
            assert '"processed": 5' in run.summary

    def test_creates_pipeline_run_with_warning_status_on_errors(self, app, runner):
        result_obj = MetadataPipelineResult(processed=5, metadata_found=3, errors=2)
        with patch(
            "flask_backend.service.movie_metadata_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-movie-metadata"])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="fetch-movie-metadata"
            ).one()
            assert run.status == "warning"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_movie_metadata_pipeline.py flask_backend/tests/test_service/test_commands.py -k "Tagged or FetchMovieMetadataCommand" -v`
Expected: FAIL — `run_pipeline()` doesn't accept `pipeline_run_id`; no `PipelineRun` rows created by the command.

- [ ] **Step 3: Add `pipeline_run_id` to the attempts repository**

Modify `flask_backend/repository/movie_metadata_fetch_attempts.py::create` (lines 12-28):

```python
def create(
    movie_id: int,
    source: str,
    status: str,
    error_message: Optional[str] = None,
    pipeline_run_id: Optional[int] = None,
) -> MovieMetadataFetchAttempt:
    attempt = MovieMetadataFetchAttempt(
        movie_id=movie_id,
        source=source,
        status=status,
        attempted_at=datetime.now(),
        error_message=error_message,
        pipeline_run_id=pipeline_run_id,
    )
    db_session.add(attempt)
    db_session.commit()
    db_session.refresh(attempt)
    return attempt
```

- [ ] **Step 4: Thread `pipeline_run_id` through `run_pipeline`**

In `flask_backend/service/movie_metadata_pipeline.py`, change the signature (line 70) and all three `create_attempt(...)` calls (lines 130-135, 147-151, 195-199) to pass it through:

```python
def run_pipeline(
    limit: Optional[int] = None,
    dry_run: bool = False,
    pipeline_run_id: Optional[int] = None,
) -> PipelineResult:
```

```python
            create_attempt(
                movie_id=movie.id,
                source=next_source,
                status="error",
                error_message=str(exc)[:500],
                pipeline_run_id=pipeline_run_id,
            )
```

```python
            create_attempt(
                movie_id=movie.id,
                source=next_source,
                status="not_found",
                pipeline_run_id=pipeline_run_id,
            )
```

```python
        create_attempt(
            movie_id=movie.id,
            source=next_source,
            status="success",
            pipeline_run_id=pipeline_run_id,
        )
```

- [ ] **Step 5: Wrap the `fetch-movie-metadata` command**

Replace the `fetch_movie_metadata` command body in `flask_backend/commands.py` (currently lines 169-198):

```python
def fetch_movie_metadata(limit, dry_run, verbose):
    """Busca diretor(es) e gêneros para filmes sem esses dados.

    Tenta fontes na ordem: TMDB.
    Registra cada tentativa para evitar repetição.
    """
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.movie_metadata_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhuma requisição será feita ===\n")

    run = pipeline_runs.start("fetch-movie-metadata")
    try:
        result = run_pipeline(limit=limit, dry_run=dry_run, pipeline_run_id=run.id)
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise

    status = "warning" if result.errors > 0 else "success"
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "processed": result.processed,
                "metadata_found": result.metadata_found,
                "metadata_not_found": result.metadata_not_found,
                "errors": result.errors,
                "skipped_all_sources_tried": result.skipped_all_sources_tried,
            }
        ),
    )

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da busca de metadados de filmes:")
    click.echo(f"  Processados:          {result.processed}")
    click.echo(f"  Metadados encontrados:  {result.metadata_found}")
    click.echo(f"  Não encontrados:      {result.metadata_not_found}")
    click.echo(f"  Erros:                {result.errors}")
    click.echo(f"  Fontes esgotadas:     {result.skipped_all_sources_tried}")
    click.echo(f"{'=' * 40}")

    if result.skipped_all_sources_tried > 0:
        click.echo(
            f"\n⚠ {result.skipped_all_sources_tried} filme(s) já tentaram todas "
            "as fontes sem sucesso. Use 'flask movie-metadata-review' para listá-los."
        )
```

(The `@click.command(...)` / `@click.option(...)` decorators above the function are unchanged — only the function body changes.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_movie_metadata_pipeline.py flask_backend/tests/test_service/test_commands.py -v`
Expected: PASS

- [ ] **Step 7: Lint and format**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add flask_backend/repository/movie_metadata_fetch_attempts.py \
  flask_backend/service/movie_metadata_pipeline.py flask_backend/commands.py \
  flask_backend/tests/test_service/test_movie_metadata_pipeline.py \
  flask_backend/tests/test_service/test_commands.py
git commit -m "feat: track fetch-movie-metadata runs in PipelineRun"
```

---

## Task 4: Instrument the `fetch-posters` command

**Files:**
- Modify: `flask_backend/repository/poster_fetch_attempts.py:8-22` (add `pipeline_run_id` param to `create`)
- Modify: `flask_backend/service/poster_pipeline.py` (thread `pipeline_run_id` through `run_pipeline`)
- Modify: `flask_backend/commands.py` (wrap `fetch_posters` command)
- Modify: `flask_backend/tests/test_service/test_poster_pipeline.py`
- Modify: `flask_backend/tests/test_service/test_commands.py`

**Interfaces:**
- Consumes: `flask_backend.repository.pipeline_runs.start`, `.finish` (Task 1)
- Produces: `PosterFetchAttempt` rows now carry `pipeline_run_id` when `run_pipeline(..., pipeline_run_id=...)` is passed one.

This task mirrors Task 3 exactly, applied to the poster pipeline.

- [ ] **Step 1: Write the failing unit test for attempt tagging**

Add to `flask_backend/tests/test_service/test_poster_pipeline.py`, inside `class TestRunPipeline` (the file already imports `PosterFetchAttempt`, `db_session`, `patch`, `run_pipeline`, and defines the `_create_screening_without_poster` helper used below — no new imports needed):

```python
    def test_attempts_are_tagged_with_pipeline_run_id(self, client, app, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening_without_poster()

            with patch(
                "flask_backend.service.poster_pipeline._try_tmdb", return_value=None
            ):
                run_pipeline(app, pipeline_run_id=42)

            attempt = (
                db_session.query(PosterFetchAttempt)
                .filter_by(screening_id=screening_id)
                .one()
            )
            assert attempt.status == "not_found"
            assert attempt.pipeline_run_id == 42
```

(`_try_tmdb` returning `None` means the screening's first untried source, `"tmdb"`, resolves to a single `"not_found"` attempt — no need to also patch `_try_imdb`.)

Add to `flask_backend/tests/test_service/test_commands.py`, inside `class TestFetchPostersCommand`:

```python
    def test_creates_pipeline_run_with_success_status(self, app, runner):
        result_obj = PosterPipelineResult(processed=3, posters_found=3, errors=0)
        with patch(
            "flask_backend.service.poster_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-posters"])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="fetch-posters"
            ).one()
            assert run.status == "success"

    def test_creates_pipeline_run_with_warning_status_on_errors(self, app, runner):
        result_obj = PosterPipelineResult(processed=3, posters_found=1, errors=2)
        with patch(
            "flask_backend.service.poster_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["fetch-posters"])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="fetch-posters"
            ).one()
            assert run.status == "warning"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_poster_pipeline.py flask_backend/tests/test_service/test_commands.py -k "Tagged or FetchPostersCommand" -v`
Expected: FAIL

- [ ] **Step 3: Add `pipeline_run_id` to the attempts repository**

Modify `flask_backend/repository/poster_fetch_attempts.py::create` (lines 8-22):

```python
def create(
    screening_id: int,
    source: str,
    status: str,
    error_message: Optional[str] = None,
    pipeline_run_id: Optional[int] = None,
) -> PosterFetchAttempt:
    attempt = PosterFetchAttempt(
        screening_id=screening_id,
        source=source,
        status=status,
        attempted_at=datetime.now(),
        error_message=error_message,
        pipeline_run_id=pipeline_run_id,
    )
    db_session.add(attempt)
    db_session.commit()
    db_session.refresh(attempt)
    return attempt
```

- [ ] **Step 4: Thread `pipeline_run_id` through `run_pipeline`**

In `flask_backend/service/poster_pipeline.py`, change the signature (line 96) and all three `create_attempt(...)` calls (around lines 163-168, 180-184, 226-230) to pass `pipeline_run_id=pipeline_run_id` through, the same way Task 3 did for `movie_metadata_pipeline.py`:

```python
def run_pipeline(
    current_app,
    limit: Optional[int] = None,
    dry_run: bool = False,
    pipeline_run_id: Optional[int] = None,
) -> PipelineResult:
```

Add `pipeline_run_id=pipeline_run_id` as a kwarg to each of the three `create_attempt(...)` calls (error/not_found/success), same pattern as Task 3 Step 4.

- [ ] **Step 5: Wrap the `fetch-posters` command**

Replace the `fetch_posters` command body in `flask_backend/commands.py` (currently lines 98-127):

```python
def fetch_posters(limit, dry_run, verbose):
    """Busca posters para sessões sem imagem.

    Tenta fontes na ordem: TMDB, IMDB.
    Registra cada tentativa para evitar repetição.
    """
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.poster_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhuma requisição será feita ===\n")

    run = pipeline_runs.start("fetch-posters")
    try:
        result = run_pipeline(
            current_app, limit=limit, dry_run=dry_run, pipeline_run_id=run.id
        )
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise

    status = "warning" if result.errors > 0 else "success"
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "processed": result.processed,
                "posters_found": result.posters_found,
                "posters_not_found": result.posters_not_found,
                "errors": result.errors,
                "skipped_all_sources_tried": result.skipped_all_sources_tried,
            }
        ),
    )

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da busca de posters:")
    click.echo(f"  Processadas:          {result.processed}")
    click.echo(f"  Posters encontrados:  {result.posters_found}")
    click.echo(f"  Posters não encontr.: {result.posters_not_found}")
    click.echo(f"  Erros:                {result.errors}")
    click.echo(f"  Fontes esgotadas:     {result.skipped_all_sources_tried}")
    click.echo(f"{'=' * 40}")

    if result.skipped_all_sources_tried > 0:
        click.echo(
            f"\n⚠ {result.skipped_all_sources_tried} sessão(ões) já tentaram todas "
            "as fontes sem sucesso. Use 'flask poster-review' para listá-las."
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_poster_pipeline.py flask_backend/tests/test_service/test_commands.py -v`
Expected: PASS

- [ ] **Step 7: Lint and format**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add flask_backend/repository/poster_fetch_attempts.py \
  flask_backend/service/poster_pipeline.py flask_backend/commands.py \
  flask_backend/tests/test_service/test_poster_pipeline.py \
  flask_backend/tests/test_service/test_commands.py
git commit -m "feat: track fetch-posters runs in PipelineRun"
```

---

## Task 5: Instrument the `generate-alerts` command

**Files:**
- Modify: `flask_backend/repository/alerts.py:12-31` (add `pipeline_run_id` param to `create`)
- Modify: `flask_backend/service/alert_pipeline.py` (thread `pipeline_run_id` through `run_pipeline`/`_record_candidate`)
- Modify: `flask_backend/commands.py` (wrap `generate_alerts` command)
- Modify: `flask_backend/tests/test_service/test_alert_pipeline.py`
- Modify: `flask_backend/tests/test_service/test_commands.py`

**Interfaces:**
- Consumes: `flask_backend.repository.pipeline_runs.start`, `.finish` (Task 1)
- Produces: `Alert` rows now carry `pipeline_run_id` when `run_pipeline(..., pipeline_run_id=...)` is passed one. Per the spec, `generate-alerts` has no "warning" state — any completed run is `"success"` (0 alerts created is a normal outcome), only an uncaught exception yields `"error"`.

- [ ] **Step 1: Write the failing unit test for alert tagging**

Add to `flask_backend/tests/test_service/test_alert_pipeline.py`, inside `class TestRunPipelineCorePass` (the file already imports `Alert`, `db_session`, `run_pipeline`, and defines the `_create_movie`/`_create_screening` helpers used below — no new imports needed). This mirrors `test_creates_alerts_for_a_due_screening`, which already establishes that a fresh movie with one screening at "capitolio" fires exactly two rules (`new_movie` + `single_screening`):

```python
    def test_alerts_are_tagged_with_pipeline_run_id(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme Tagueado", "filme-tagueado")
            _create_screening(movie, "capitolio")

            run_pipeline(pipeline_run_id=42)

            alerts = db_session.query(Alert).filter_by(movie_id=movie.id).all()
            assert len(alerts) == 2
            assert all(alert.pipeline_run_id == 42 for alert in alerts)
```

Add to `flask_backend/tests/test_service/test_commands.py`, inside a `class TestGenerateAlertsCommand` (new class — none exists yet; add `from flask_backend.service.alert_pipeline import AlertPipelineResult` to the top-level imports):

```python
class TestGenerateAlertsCommand:
    def test_creates_pipeline_run_with_success_status(self, app, runner):
        result_obj = AlertPipelineResult(
            screenings_evaluated=2, movies_evaluated=1, alerts_created=1
        )
        with patch(
            "flask_backend.service.alert_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["generate-alerts"])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="generate-alerts"
            ).one()
            assert run.status == "success"
            assert '"alerts_created": 1' in run.summary

    def test_zero_alerts_created_is_still_success(self, app, runner):
        result_obj = AlertPipelineResult(screenings_evaluated=2, movies_evaluated=1)
        with patch(
            "flask_backend.service.alert_pipeline.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["generate-alerts"])

        with app.app_context():
            run = db_session.query(PipelineRun).filter_by(
                pipeline_name="generate-alerts"
            ).one()
            assert run.status == "success"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_alert_pipeline.py flask_backend/tests/test_service/test_commands.py -k "Tagged or GenerateAlertsCommand" -v`
Expected: FAIL

- [ ] **Step 3: Add `pipeline_run_id` to the alerts repository**

Modify `flask_backend/repository/alerts.py::create` (lines 12-31):

```python
def create(
    rule_name: str,
    movie_id: int,
    screening_id: Optional[int],
    dedup_key: str,
    drafted_text: str,
    context: Optional[str] = None,
    commit: bool = True,
    pipeline_run_id: Optional[int] = None,
) -> Alert:
    alert = Alert(
        rule_name=rule_name,
        movie_id=movie_id,
        screening_id=screening_id,
        dedup_key=dedup_key,
        drafted_text=drafted_text,
        context=context,
        status="pending",
        created_at=datetime.now(),
        pipeline_run_id=pipeline_run_id,
    )
    db_session.add(alert)
    if commit:
        db_session.commit()
        db_session.refresh(alert)
    return alert
```

- [ ] **Step 4: Thread `pipeline_run_id` through `run_pipeline`**

In `flask_backend/service/alert_pipeline.py`, change `_record_candidate` (line 38) and `run_pipeline` (line 63) to accept and pass through `pipeline_run_id`:

```python
def _record_candidate(
    candidate,
    dry_run: bool,
    result: AlertPipelineResult,
    pipeline_run_id: Optional[int] = None,
) -> None:
    if exists_by_dedup_key(candidate.dedup_key):
        return
    if not dry_run:
        create_alert(
            rule_name=candidate.rule_name,
            movie_id=candidate.movie_id,
            screening_id=candidate.screening_id,
            dedup_key=candidate.dedup_key,
            drafted_text=candidate.drafted_text,
            context=json.dumps(candidate.context) if candidate.context else None,
            commit=False,
            pipeline_run_id=pipeline_run_id,
        )
    result.alerts_created += 1
    result.alerts_by_rule[candidate.rule_name] = (
        result.alerts_by_rule.get(candidate.rule_name, 0) + 1
    )
    logger.info(
        "Alerta '%s' gerado para filme %d%s",
        candidate.rule_name,
        candidate.movie_id,
        f" (sessão {candidate.screening_id})" if candidate.screening_id else "",
    )


def run_pipeline(
    limit: Optional[int] = None,
    dry_run: bool = False,
    pipeline_run_id: Optional[int] = None,
) -> AlertPipelineResult:
    result = AlertPipelineResult()

    screenings = get_screenings_due_for_core_alert_evaluation()
    if limit is not None:
        screenings = screenings[:limit]

    for screening in screenings:
        for rule_fn in CORE_SCREENING_RULES:
            candidate = rule_fn(screening)
            if candidate is not None:
                _record_candidate(candidate, dry_run, result, pipeline_run_id)
        if not dry_run:
            screening.core_alerts_evaluated_at = datetime.now()
            db_session.add(screening)
        result.screenings_evaluated += 1

    if not dry_run and screenings:
        db_session.commit()

    remaining_limit = None
    if limit is not None:
        remaining_limit = limit - len(screenings)

    if remaining_limit is None or remaining_limit > 0:
        movies = get_movies_due_for_metadata_alert_evaluation()
        if remaining_limit is not None:
            movies = movies[:remaining_limit]

        for movie in movies:
            for rule_fn in METADATA_MOVIE_RULES:
                candidate = rule_fn(movie)
                if candidate is not None:
                    _record_candidate(candidate, dry_run, result, pipeline_run_id)
            if not dry_run:
                movie.metadata_alerts_evaluated_at = datetime.now()
                db_session.add(movie)
            result.movies_evaluated += 1

        if not dry_run and movies:
            db_session.commit()

    return result
```

- [ ] **Step 5: Wrap the `generate-alerts` command**

Replace the `generate_alerts` command body in `flask_backend/commands.py` (currently lines 266-292):

```python
def generate_alerts(limit, dry_run, verbose):
    """Avalia as regras de alerta (filme novo, sessão única, sessão
    comentada, mostra, estreia/retorno de diretor, nova combinação de
    gênero, sequência/franquia) e grava os alertas pendentes.

    Revise-os em /admin/alerts.
    """
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.alert_pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if dry_run:
        click.echo("=== Modo dry-run: nenhum alerta será gravado ===\n")

    run = pipeline_runs.start("generate-alerts")
    try:
        result = run_pipeline(limit=limit, dry_run=dry_run, pipeline_run_id=run.id)
    except Exception as exc:
        pipeline_runs.finish(run.id, status="error", error_message=str(exc)[:500])
        raise

    pipeline_runs.finish(
        run.id,
        status="success",
        summary=json.dumps(
            {
                "screenings_evaluated": result.screenings_evaluated,
                "movies_evaluated": result.movies_evaluated,
                "alerts_created": result.alerts_created,
            }
        ),
    )

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da geração de alertas:")
    click.echo(f"  Sessões avaliadas:    {result.screenings_evaluated}")
    click.echo(f"  Filmes avaliados:     {result.movies_evaluated}")
    click.echo(f"  Alertas gerados:      {result.alerts_created}")
    if result.alerts_by_rule:
        click.echo("  Por regra:")
        for rule_name, count in sorted(result.alerts_by_rule.items()):
            click.echo(f"    {rule_name}: {count}")
    click.echo(f"{'=' * 40}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_alert_pipeline.py flask_backend/tests/test_service/test_commands.py -v`
Expected: PASS

- [ ] **Step 7: Lint and format**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add flask_backend/repository/alerts.py flask_backend/service/alert_pipeline.py \
  flask_backend/commands.py flask_backend/tests/test_service/test_alert_pipeline.py \
  flask_backend/tests/test_service/test_commands.py
git commit -m "feat: track generate-alerts runs in PipelineRun"
```

---

## Task 6: Admin pipelines index and history pages

**Files:**
- Create: `flask_backend/routes/admin/pipelines.py`
- Modify: `flask_backend/__init__.py:59-61` (register the new blueprint)
- Create: `flask_backend/templates/pipelines/admin/index.html`
- Create: `flask_backend/templates/pipelines/admin/history.html`
- Modify: `flask_backend/templates/base.html` (nav link, both occurrences)
- Create: `flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py`

**Interfaces:**
- Consumes: `flask_backend.repository.pipeline_runs.get_latest_by_pipeline`, `.get_paginated`, `.display_status` (Task 1)
- Produces: `admin_pipelines.index` route at `/admin/pipelines`, `admin_pipelines.history` route at `/admin/pipelines/<pipeline_name>`. Both reused by Task 7's detail page link and by `PIPELINE_GROUPS` (defined here, consumed by Task 7).

- [ ] **Step 1: Write the failing route tests**

Create `flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py`:

```python
"""
Tests the basic functionality of /admin/pipelines/* endpoints.
"""

from flask_backend.db import db_session
from flask_backend.repository import pipeline_runs


class TestAdminPipelinesIndex:
    def test_requires_login(self, client):
        response = client.get("/admin/pipelines")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200_with_no_runs(self, auth_headers):
        response = auth_headers.get("/admin/pipelines")
        assert response.status_code == 200
        assert "Nunca executado".encode() in response.data

    def test_shows_latest_status_per_group(self, app, auth_headers):
        with app.app_context():
            run = pipeline_runs.start(
                "import-json", source="capitolio,paulo-amorim,sala-redencao"
            )
            pipeline_runs.finish(run.id, status="success", summary='{"created": 3}')
            db_session.commit()

        response = auth_headers.get("/admin/pipelines")
        assert response.status_code == 200
        assert b"Sucesso" in response.data

    def test_shows_interrupted_for_stale_running_run(self, app, auth_headers):
        from datetime import datetime, timedelta

        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            run.started_at = datetime.now() - timedelta(hours=2)
            db_session.commit()

        response = auth_headers.get("/admin/pipelines")
        assert response.status_code == 200
        assert "Interrompida".encode() in response.data


class TestAdminPipelinesHistory:
    def test_requires_login(self, client):
        response = client.get("/admin/pipelines/fetch-posters")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200_with_no_runs(self, auth_headers):
        response = auth_headers.get("/admin/pipelines/fetch-posters")
        assert response.status_code == 200

    def test_invalid_pagination_returns_400(self, auth_headers):
        response = auth_headers.get(
            "/admin/pipelines/fetch-posters?page=invalid&limit=10"
        )
        assert response.status_code == 400

    def test_zero_limit_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/pipelines/fetch-posters?limit=0")
        assert response.status_code == 400

    def test_lists_runs_for_pipeline(self, app, auth_headers):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            pipeline_runs.finish(run.id, status="success", summary='{"processed": 4}')
            db_session.commit()

        response = auth_headers.get("/admin/pipelines/fetch-posters")
        assert response.status_code == 200
        assert b"Sucesso" in response.data

    def test_filters_by_source(self, app, auth_headers):
        with app.app_context():
            run_a = pipeline_runs.start("import-json", source="cinebancarios")
            pipeline_runs.finish(run_a.id, status="success", summary='{"created": 1}')
            run_b = pipeline_runs.start("import-json", source="cine-cinco")
            pipeline_runs.finish(run_b.id, status="success", summary='{"created": 2}')
            db_session.commit()

        response = auth_headers.get(
            "/admin/pipelines/import-json?source=cinebancarios"
        )
        assert response.status_code == 200
        assert b'"created": 1' in response.data
        assert b'"created": 2' not in response.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py -v`
Expected: FAIL — `/admin/pipelines` returns 404 (blueprint doesn't exist yet).

- [ ] **Step 3: Write the routes**

Create `flask_backend/routes/admin/pipelines.py`:

```python
from flask import Blueprint, abort, render_template, request

from flask_backend.repository import pipeline_runs
from flask_backend.routes.auth import login_required

bp = Blueprint("admin_pipelines", __name__)

# Each entry is one health row on /admin/pipelines. import-json shares one
# CLI command across three cinema groups that run on very different
# schedules (see docs/superpowers/specs/2026-07-21-admin-pipeline-dashboard-design.md),
# so it needs three separate groups here rather than one. The `source`
# value must stay in sync with flask_backend/commands.py::_run_import_json,
# which builds it as sorted(cinema_slugs) joined with ",".
PIPELINE_GROUPS = [
    {
        "pipeline_name": "import-json",
        "source": "capitolio,paulo-amorim,sala-redencao",
        "label": "Importação — Capitólio, Paulo Amorim, Sala Redenção",
    },
    {
        "pipeline_name": "import-json",
        "source": "cinebancarios",
        "label": "Importação — CineBancários",
    },
    {
        "pipeline_name": "import-json",
        "source": "cine-cinco",
        "label": "Importação — Cine Cinco",
    },
    {
        "pipeline_name": "fetch-posters",
        "source": None,
        "label": "Busca de Posters",
    },
    {
        "pipeline_name": "fetch-movie-metadata",
        "source": None,
        "label": "Busca de Metadados de Filmes",
    },
    {
        "pipeline_name": "generate-alerts",
        "source": None,
        "label": "Geração de Alertas",
    },
]


def _group_label(pipeline_name, source):
    for group in PIPELINE_GROUPS:
        if group["pipeline_name"] == pipeline_name and group["source"] == source:
            return group["label"]
    return pipeline_name


@bp.route("/admin/pipelines")
@login_required
def index():
    """Health overview: latest run per tracked pipeline/source group."""
    rows = []
    for group in PIPELINE_GROUPS:
        latest = pipeline_runs.get_latest_by_pipeline(
            group["pipeline_name"], source=group["source"]
        )
        rows.append(
            {
                "pipeline_name": group["pipeline_name"],
                "source": group["source"],
                "label": group["label"],
                "latest_run": latest,
                "display_status": (
                    pipeline_runs.display_status(latest) if latest else None
                ),
            }
        )
    return render_template("pipelines/admin/index.html", rows=rows)


@bp.route("/admin/pipelines/<pipeline_name>")
@login_required
def history(pipeline_name):
    """Paginated run history for one pipeline (optionally one source)."""
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        abort(400)

    if page < 1 or limit < 1:
        abort(400)

    source = request.args.get("source") or None
    runs, pages, qtt_runs = pipeline_runs.get_paginated(
        pipeline_name, page, limit, source=source
    )

    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < pages else None

    return render_template(
        "pipelines/admin/history.html",
        pipeline_name=pipeline_name,
        source=source,
        label=_group_label(pipeline_name, source),
        runs=runs,
        display_statuses={run.id: pipeline_runs.display_status(run) for run in runs},
        curr_page=page,
        prev_page=prev_page,
        next_page=next_page,
        pages=pages,
        limit=limit,
        qtt_runs=qtt_runs,
    )
```

- [ ] **Step 4: Register the blueprint**

In `flask_backend/__init__.py`, add right after the `admin_alerts` registration (currently lines 59-61):

```python
    from .routes.admin import alerts as admin_alerts

    app.register_blueprint(admin_alerts.bp)

    from .routes.admin import pipelines as admin_pipelines

    app.register_blueprint(admin_pipelines.bp)

    from .routes import page
```

- [ ] **Step 5: Write the templates**

Create `flask_backend/templates/pipelines/admin/index.html`:

```html
{% extends "base.html" %}
{% block title %}
    Pipelines
{% endblock title %}
{% block header %}
    <div>
        <h1>Pipelines</h1>
        <p>Saúde das rotinas automatizadas de importação e enriquecimento de dados</p>
    </div>
{% endblock header %}
{% block content %}
    {% set status_labels = {
        "running": "Em execução",
        "success": "Sucesso",
        "warning": "Alerta",
        "error": "Erro",
        "interrupted": "Interrompida"
    } %}
    {% set status_classes = {
        "running": "bg-info text-dark",
        "success": "bg-success",
        "warning": "bg-warning text-dark",
        "error": "bg-danger",
        "interrupted": "bg-secondary"
    } %}
    <div class="table-responsive">
        <table class="table table-striped align-middle">
            <thead>
                <tr>
                    <th>Pipeline</th>
                    <th>Status</th>
                    <th>Última execução</th>
                    <th>Resumo</th>
                </tr>
            </thead>
            <tbody>
                {% for row in rows %}
                    <tr>
                        <td>
                            <a href="{{ url_for('admin_pipelines.history', pipeline_name=row.pipeline_name, source=row.source) }}">
                                {{ row.label }}
                            </a>
                        </td>
                        <td>
                            {% if row.display_status %}
                                <span class="badge {{ status_classes[row.display_status] }}">{{ status_labels[row.display_status] }}</span>
                            {% else %}
                                <span class="badge bg-secondary">Nunca executado</span>
                            {% endif %}
                        </td>
                        <td>
                            {% if row.latest_run %}
                                <time datetime="{{ row.latest_run.started_at.isoformat() }}">{{ row.latest_run.started_at.strftime("%d/%m/%Y %H:%M") }}</time>
                            {% else %}
                                —
                            {% endif %}
                        </td>
                        <td>
                            {% if row.latest_run and row.latest_run.error_message %}
                                {{ row.latest_run.error_message }}
                            {% elif row.latest_run and row.latest_run.summary %}
                                {{ row.latest_run.summary }}
                            {% else %}
                                —
                            {% endif %}
                        </td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
{% endblock content %}
```

Create `flask_backend/templates/pipelines/admin/history.html`:

```html
{% extends "base.html" %}
{% block title %}
    {{ label }}
{% endblock title %}
{% block header %}
    <div>
        <h1>{{ label }}</h1>
        <p>
            <a href="{{ url_for('admin_pipelines.index') }}">← Voltar para Pipelines</a>
        </p>
    </div>
{% endblock header %}
{% block content %}
    {% set status_labels = {
        "running": "Em execução",
        "success": "Sucesso",
        "warning": "Alerta",
        "error": "Erro",
        "interrupted": "Interrompida"
    } %}
    {% set status_classes = {
        "running": "bg-info text-dark",
        "success": "bg-success",
        "warning": "bg-warning text-dark",
        "error": "bg-danger",
        "interrupted": "bg-secondary"
    } %}
    {% if runs %}
        <div class="table-responsive">
            <table class="table table-striped align-middle">
                <thead>
                    <tr>
                        <th>Início</th>
                        <th>Status</th>
                        <th>Resumo</th>
                    </tr>
                </thead>
                <tbody>
                    {% for run in runs %}
                        <tr>
                            <td>
                                <a href="{{ url_for('admin_pipelines.detail', pipeline_name=run.pipeline_name, run_id=run.id) }}">
                                    <time datetime="{{ run.started_at.isoformat() }}">{{ run.started_at.strftime("%d/%m/%Y %H:%M") }}</time>
                                </a>
                            </td>
                            <td>
                                <span class="badge {{ status_classes[display_statuses[run.id]] }}">{{ status_labels[display_statuses[run.id]] }}</span>
                            </td>
                            <td>
                                {% if run.error_message %}
                                    {{ run.error_message }}
                                {% elif run.summary %}
                                    {{ run.summary }}
                                {% else %}
                                    —
                                {% endif %}
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% if pages > 1 %}
            <nav aria-label="Navegação do admin">
                <ul class="pagination justify-content-center">
                    {% if prev_page %}
                        <li class="page-item">
                            <a class="page-link"
                               href="{{ url_for('admin_pipelines.history', pipeline_name=pipeline_name, source=source, page=prev_page, limit=limit) }}">Anterior</a>
                        </li>
                    {% endif %}
                    {% for page_num in range(1, pages + 1) %}
                        <li class="page-item {% if page_num == curr_page %}active{% endif %}">
                            <a class="page-link"
                               href="{{ url_for('admin_pipelines.history', pipeline_name=pipeline_name, source=source, page=page_num, limit=limit) }}">{{ page_num }}</a>
                        </li>
                    {% endfor %}
                    {% if next_page %}
                        <li class="page-item">
                            <a class="page-link"
                               href="{{ url_for('admin_pipelines.history', pipeline_name=pipeline_name, source=source, page=next_page, limit=limit) }}">Próximo</a>
                        </li>
                    {% endif %}
                </ul>
            </nav>
        {% endif %}
    {% else %}
        <p>Nenhuma execução registrada ainda.</p>
    {% endif %}
{% endblock content %}
```

(`history.html` links to `admin_pipelines.detail`, added in Task 7 — this is expected to be a broken `url_for` until Task 7 lands; if this task is reviewed/merged standalone before Task 7, that link will 500 when clicked but the page itself still renders and all tests in this task pass, since none of them click through to the detail page.)

- [ ] **Step 6: Add the nav link**

In `flask_backend/templates/base.html`, both dropdown blocks (the mobile one starting around line 148 and the desktop one starting around line 218) have this exact three-line pattern right after the "Alertas" link:

```html
                                <li>
                                    <a class="dropdown-item {% if request.path == url_for('admin_alerts.index') %}active{% endif %}"
                                       href="{{ url_for("admin_alerts.index") }}">Alertas</a>
                                </li>
```

After **each** occurrence, insert:

```html
                                <li>
                                    <a class="dropdown-item {% if request.path.startswith('/admin/pipelines') %}active{% endif %}"
                                       href="{{ url_for("admin_pipelines.index") }}">Pipelines</a>
                                </li>
```

(Indentation differs slightly between the two occurrences in the file — match whatever indentation the surrounding "Alertas" `<li>` uses at each spot; `djlint --reformat` in the final verification task will normalize it regardless.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py -v`
Expected: PASS

Run the full suite:

Run: `pytest flask_backend/tests -x -q`
Expected: PASS

- [ ] **Step 8: Lint, format, and lint templates**

```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```

Expected: no errors (fix anything djlint flags before continuing).

- [ ] **Step 9: Commit**

```bash
git add flask_backend/routes/admin/pipelines.py flask_backend/__init__.py \
  flask_backend/templates/pipelines flask_backend/templates/base.html \
  flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py
git commit -m "feat: add admin pipelines index and history pages"
```

---

## Task 7: Admin pipeline run detail page

**Files:**
- Modify: `flask_backend/repository/screenings.py` (add `get_by_pipeline_run_id`)
- Modify: `flask_backend/repository/movie_metadata_fetch_attempts.py` (add `get_by_pipeline_run_id`)
- Modify: `flask_backend/repository/poster_fetch_attempts.py` (add `get_by_pipeline_run_id`)
- Modify: `flask_backend/repository/alerts.py` (add `get_by_pipeline_run_id`)
- Modify: `flask_backend/routes/admin/pipelines.py` (add `detail` route)
- Create: `flask_backend/templates/pipelines/admin/detail.html`
- Modify: `flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py`

**Interfaces:**
- Consumes: `PIPELINE_GROUPS`, `_group_label` from Task 6's `flask_backend/routes/admin/pipelines.py`; `pipeline_runs.get_by_id`, `.display_status` (Task 1)
- Produces: `admin_pipelines.detail` route at `/admin/pipelines/<pipeline_name>/<int:run_id>` — the link Task 6's `history.html` already points to.

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py`:

```python
class TestAdminPipelinesDetail:
    def test_requires_login(self, app, client):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            db_session.commit()
            run_id = run.id

        response = client.get(f"/admin/pipelines/fetch-posters/{run_id}")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_unknown_run(self, auth_headers):
        response = auth_headers.get("/admin/pipelines/fetch-posters/99999")
        assert response.status_code == 404

    def test_returns_404_when_pipeline_name_mismatches_run(self, app, auth_headers):
        with app.app_context():
            run = pipeline_runs.start("fetch-posters")
            db_session.commit()
            run_id = run.id

        response = auth_headers.get(f"/admin/pipelines/generate-alerts/{run_id}")
        assert response.status_code == 404

    def test_shows_screenings_created_for_import_json_run(
        self, app, auth_headers, setup_cinemas
    ):
        from flask_backend.models import Movie, Screening
        from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug

        with app.app_context():
            run = pipeline_runs.start(
                "import-json", source="capitolio,paulo-amorim,sala-redencao"
            )
            pipeline_runs.finish(run.id, status="success", summary='{"created": 1}')
            movie = Movie(title="Filme do Run", slug="filme-do-run")
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                pipeline_run_id=run.id,
            )
            db_session.add(screening)
            db_session.commit()
            run_id = run.id

        response = auth_headers.get(f"/admin/pipelines/import-json/{run_id}")
        assert response.status_code == 200
        assert "Filme do Run".encode() in response.data

    def test_shows_alerts_created_for_generate_alerts_run(self, app, auth_headers):
        from flask_backend.models import Alert, Movie

        with app.app_context():
            run = pipeline_runs.start("generate-alerts")
            pipeline_runs.finish(run.id, status="success")
            movie = Movie(title="Filme Alertado", slug="filme-alertado")
            db_session.add(movie)
            db_session.commit()
            alert = Alert(
                rule_name="new_movie",
                movie_id=movie.id,
                screening_id=None,
                dedup_key=f"new_movie:{movie.id}",
                drafted_text="texto",
                status="pending",
                pipeline_run_id=run.id,
            )
            db_session.add(alert)
            db_session.commit()
            run_id = run.id

        response = auth_headers.get(f"/admin/pipelines/generate-alerts/{run_id}")
        assert response.status_code == 200
        assert "Filme Alertado".encode() in response.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py -k Detail -v`
Expected: FAIL — 404 for every case (route doesn't exist yet).

- [ ] **Step 3: Add `get_by_pipeline_run_id` to each repository**

Append to `flask_backend/repository/screenings.py`:

```python
def get_by_pipeline_run_id(pipeline_run_id: int) -> List[Screening]:
    return (
        db_session.query(Screening)
        .filter(Screening.pipeline_run_id == pipeline_run_id)
        .order_by(Screening.id)
        .all()
    )
```

Append to `flask_backend/repository/movie_metadata_fetch_attempts.py`:

```python
def get_by_pipeline_run_id(pipeline_run_id: int) -> List[MovieMetadataFetchAttempt]:
    return (
        db_session.query(MovieMetadataFetchAttempt)
        .filter(MovieMetadataFetchAttempt.pipeline_run_id == pipeline_run_id)
        .order_by(MovieMetadataFetchAttempt.id)
        .all()
    )
```

Append to `flask_backend/repository/poster_fetch_attempts.py`:

```python
def get_by_pipeline_run_id(pipeline_run_id: int) -> List[PosterFetchAttempt]:
    return (
        db_session.query(PosterFetchAttempt)
        .filter(PosterFetchAttempt.pipeline_run_id == pipeline_run_id)
        .order_by(PosterFetchAttempt.id)
        .all()
    )
```

In `flask_backend/repository/alerts.py`, change the existing `from typing import Optional, Tuple` (line 2) to:

```python
from typing import List, Optional, Tuple
```

Then append:

```python
def get_by_pipeline_run_id(pipeline_run_id: int) -> List[Alert]:
    return (
        db_session.query(Alert)
        .filter(Alert.pipeline_run_id == pipeline_run_id)
        .order_by(Alert.id)
        .all()
    )
```

(`screenings.py`, `movie_metadata_fetch_attempts.py`, and `poster_fetch_attempts.py` already import `List` — no import change needed for those three.)

- [ ] **Step 4: Add the `detail` route**

Append to `flask_backend/routes/admin/pipelines.py` (add these imports to the top of the file alongside the existing ones):

```python
from flask_backend.repository.alerts import get_by_pipeline_run_id as get_alerts_by_run
from flask_backend.repository.movie_metadata_fetch_attempts import (
    get_by_pipeline_run_id as get_metadata_attempts_by_run,
)
from flask_backend.repository.poster_fetch_attempts import (
    get_by_pipeline_run_id as get_poster_attempts_by_run,
)
from flask_backend.repository.screenings import (
    get_by_pipeline_run_id as get_screenings_by_run,
)
```

```python
@bp.route("/admin/pipelines/<pipeline_name>/<int:run_id>")
@login_required
def detail(pipeline_name, run_id):
    """Full item list for one specific run."""
    run = pipeline_runs.get_by_id(run_id)
    if run is None or run.pipeline_name != pipeline_name:
        abort(404)

    screenings, metadata_attempts, poster_attempts, alerts = [], [], [], []
    if pipeline_name == "import-json":
        screenings = get_screenings_by_run(run_id)
    elif pipeline_name == "fetch-movie-metadata":
        metadata_attempts = get_metadata_attempts_by_run(run_id)
    elif pipeline_name == "fetch-posters":
        poster_attempts = get_poster_attempts_by_run(run_id)
    elif pipeline_name == "generate-alerts":
        alerts = get_alerts_by_run(run_id)

    return render_template(
        "pipelines/admin/detail.html",
        run=run,
        label=_group_label(run.pipeline_name, run.source),
        display_status=pipeline_runs.display_status(run),
        screenings=screenings,
        metadata_attempts=metadata_attempts,
        poster_attempts=poster_attempts,
        alerts=alerts,
    )
```

- [ ] **Step 5: Write the template**

Create `flask_backend/templates/pipelines/admin/detail.html`:

```html
{% extends "base.html" %}
{% block title %}
    {{ label }}
{% endblock title %}
{% block header %}
    <div>
        <h1>{{ label }}</h1>
        <p>
            <a href="{{ url_for('admin_pipelines.history', pipeline_name=run.pipeline_name, source=run.source) }}">← Voltar para o histórico</a>
        </p>
    </div>
{% endblock header %}
{% block content %}
    {% set status_labels = {
        "running": "Em execução",
        "success": "Sucesso",
        "warning": "Alerta",
        "error": "Erro",
        "interrupted": "Interrompida"
    } %}
    {% set status_classes = {
        "running": "bg-info text-dark",
        "success": "bg-success",
        "warning": "bg-warning text-dark",
        "error": "bg-danger",
        "interrupted": "bg-secondary"
    } %}
    <p>
        <span class="badge {{ status_classes[display_status] }}">{{ status_labels[display_status] }}</span>
        Início: <time datetime="{{ run.started_at.isoformat() }}">{{ run.started_at.strftime("%d/%m/%Y %H:%M") }}</time>
        {% if run.finished_at %}
            — Fim: <time datetime="{{ run.finished_at.isoformat() }}">{{ run.finished_at.strftime("%d/%m/%Y %H:%M") }}</time>
        {% endif %}
    </p>
    {% if run.error_message %}
        <div class="alert alert-danger">{{ run.error_message }}</div>
    {% endif %}
    {% if run.pipeline_name == "import-json" %}
        <h2>Sessões criadas ({{ screenings | length }})</h2>
        {% if screenings %}
            <ul>
                {% for screening in screenings %}
                    <li>{{ screening.movie.title }} — {{ screening.cinema.name }}</li>
                {% endfor %}
            </ul>
        {% else %}
            <p>Nenhuma sessão criada neste run.</p>
        {% endif %}
    {% elif run.pipeline_name == "fetch-movie-metadata" %}
        <h2>Filmes processados ({{ metadata_attempts | length }})</h2>
        {% if metadata_attempts %}
            <ul>
                {% for attempt in metadata_attempts %}
                    <li>
                        {{ attempt.movie.title }} — {{ attempt.source }} —
                        <span class="badge {% if attempt.status == "success" %}bg-success{% elif attempt.status == "not_found" %}bg-warning text-dark{% else %}bg-danger{% endif %}">
                            {{ attempt.status }}
                        </span>
                        {% if attempt.error_message %}({{ attempt.error_message }}){% endif %}
                    </li>
                {% endfor %}
            </ul>
        {% else %}
            <p>Nenhum filme processado neste run.</p>
        {% endif %}
    {% elif run.pipeline_name == "fetch-posters" %}
        <h2>Sessões processadas ({{ poster_attempts | length }})</h2>
        {% if poster_attempts %}
            <ul>
                {% for attempt in poster_attempts %}
                    <li>
                        {{ attempt.screening.movie.title }} — {{ attempt.source }} —
                        <span class="badge {% if attempt.status == "success" %}bg-success{% elif attempt.status == "not_found" %}bg-warning text-dark{% else %}bg-danger{% endif %}">
                            {{ attempt.status }}
                        </span>
                        {% if attempt.error_message %}({{ attempt.error_message }}){% endif %}
                    </li>
                {% endfor %}
            </ul>
        {% else %}
            <p>Nenhuma sessão processada neste run.</p>
        {% endif %}
    {% elif run.pipeline_name == "generate-alerts" %}
        <h2>Alertas gerados ({{ alerts | length }})</h2>
        {% if alerts %}
            <ul>
                {% for alert in alerts %}
                    <li>{{ alert.rule_name }} — {{ alert.movie.title }}</li>
                {% endfor %}
            </ul>
        {% else %}
            <p>Nenhum alerta gerado neste run.</p>
        {% endif %}
    {% endif %}
{% endblock content %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py -v`
Expected: PASS

Run the full suite:

Run: `pytest flask_backend/tests -x -q`
Expected: PASS

- [ ] **Step 7: Lint, format, and lint templates**

```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```

Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add flask_backend/repository/screenings.py \
  flask_backend/repository/movie_metadata_fetch_attempts.py \
  flask_backend/repository/poster_fetch_attempts.py \
  flask_backend/repository/alerts.py \
  flask_backend/routes/admin/pipelines.py \
  flask_backend/templates/pipelines/admin/detail.html \
  flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py
git commit -m "feat: add admin pipeline run detail page"
```

---

## Task 8: Full verification pass

**Files:** none (verification only)

**Interfaces:** none — this task only runs checks across everything built in Tasks 1–7.

- [ ] **Step 1: Run the full test suite with coverage**

Run: `coverage run -m pytest && coverage report -m`
Expected: PASS, no regressions in unrelated modules.

- [ ] **Step 2: Run every lint/format command from CLAUDE.md**

```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```

Expected: no errors or unstaged formatting diffs remain.

- [ ] **Step 3: Check for dead code**

Run: `uv run vulture flask_backend scrapers cinemaempoa.py vulture_whitelist.py --exclude "*/tests/*" --min-confidence 80`
Expected: no new unused-code warnings introduced by this feature (`PIPELINE_RUN_STATUSES` may be flagged as unused since nothing enforces it at runtime — if so, add it to `vulture_whitelist.py` rather than deleting it, since it documents the valid `status` values for `PipelineRun` the same way `ALERT_STATUSES` documents `Alert.status`).

- [ ] **Step 4: Check complexity**

Run: `uv run xenon --max-absolute B --max-modules A --max-average A flask_backend scrapers --exclude "*/tests/*"`
Expected: no new violations. If `commands.py`'s wrapped command functions trip the threshold, extract the summary-building `json.dumps({...})` calls into small named helpers per pipeline rather than leaving them inline.

- [ ] **Step 5: Manually verify the dashboard in a running app**

```bash
flask --app flask_backend run --debug
```

Log in as an admin, run e.g. `flask --app flask_backend fetch-movie-metadata --dry-run` in another terminal (or trigger one of the four commands against a seeded dev DB), then visit `/admin/pipelines` and confirm: the health row updates, clicking through reaches the history page, and clicking a run reaches its detail page with the expected item list.

- [ ] **Step 6: Commit any fixups from this task**

Only if Steps 3–4 required code changes:

```bash
git add -A
git commit -m "chore: address lint/complexity findings from pipeline dashboard feature"
```
