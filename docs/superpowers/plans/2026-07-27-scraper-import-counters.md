# Accurate Scraper Import Counters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single misleading "created_features" counter in the scraper import pipeline with three accurate counts — movies created, screenings created, dates registered — and fix the Capitólio comparison bug that made every re-scraped day look "new."

**Architecture:** Add a `pipeline_run_id` FK to `movies` (mirroring the existing one on `screenings`), thread a `was_created` boolean out of `movies.get_by_title_or_create`, and replace `import_scrapped_results`'s bare int return with an `ImportSummary` dataclass computed by comparing each touched screening's date/time set *before* any mutation (fixing the Capitólio false-positive along the way). `commands.py` consumes the new dataclass to build the `/admin/pipelines` summary JSON and decide success/warning status.

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, Alembic, pytest, uv.

## Global Constraints

- Full design/rationale: `docs/superpowers/specs/2026-07-27-scraper-import-counters-design.md`.
- No `/admin/pipelines` template changes — index/history already render the summary dict generically via `| tojson`.
- No schema change to `ScreeningDate`; new-date detection stays in-memory only, computed by comparing date/time sets, not by tracking new rows.
- `update_screening_dates` storage behavior (delete-all/recreate-all, including Capitólio's day-filter step) is unchanged — only the *counting* logic around it changes.
- `dates_registered` counts once **per screening** touched this run that got at least one new date/time — not once per individual date row.
- Migration must be additive/nullable, no backfill needed.
- Run `uv run ruff check --fix`, `uv run ruff format`, `uv run djlint flask_backend/templates --lint --profile=jinja`, and `uv run djlint --reformat flask_backend/templates --format-css --format-js` before considering the branch PR-ready (per `AGENTS.md`).

---

### Task 1: `movies.pipeline_run_id` migration and model column

**Files:**
- Modify: `flask_backend/models.py` (Movie class, around line 109-130)
- Create: `migrations/versions/20260727_000000_add_movies_pipeline_run_id.py`

**Interfaces:**
- Produces: `Movie.pipeline_run_id` — nullable `Integer` FK to `pipeline_runs.id`, indexed. Consumed by Task 2.

- [ ] **Step 1: Add the column to the `Movie` model**

In `flask_backend/models.py`, inside `class Movie(Base):` (currently lines 109-129), add the column right after `collection_id` and before the `screenings` relationship:

```python
    collection_id = Column(
        Integer, ForeignKey("collections.id"), nullable=True, index=True
    )
    # Set when this movie was created by a tracked pipeline run (e.g.
    # import-json). NULL for movies created manually via /admin or by
    # scripts/dedupper.py.
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    screenings: Mapped[List["Screening"]] = relationship(back_populates="movie")
```

- [ ] **Step 2: Generate a migration skeleton**

Run: `flask --app flask_backend db-revision --autogenerate -m "add movies pipeline_run_id"`

This creates a new file under `migrations/versions/`. Rename/overwrite it so its filename is `20260727_000000_add_movies_pipeline_run_id.py` and its content matches Step 3 exactly (autogenerate on SQLite may not wrap the `ADD COLUMN` + FK in `batch_alter_table`, which is required for SQLite to add a foreign key constraint after table creation — the existing `20260721_000000_add_pipeline_runs.py` migration shows the required pattern).

- [ ] **Step 3: Ensure the migration content matches this exactly**

```python
"""Adds movies.pipeline_run_id so a pipeline run can be credited with
creating a specific movie, the same way screenings.pipeline_run_id already
works - see docs/superpowers/specs/2026-07-27-scraper-import-counters-design.md.

Revision ID: 20260727_000000
Revises: 20260726_000000
Create Date: 2026-07-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260727_000000"
down_revision: Union[str, None] = "20260726_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "movies", sa.Column("pipeline_run_id", sa.Integer(), nullable=True)
    )
    with op.batch_alter_table("movies") as batch_op:
        batch_op.create_foreign_key(
            "fk_movies_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
        )
    op.create_index("ix_movies_pipeline_run_id", "movies", ["pipeline_run_id"])


def downgrade() -> None:
    op.drop_index("ix_movies_pipeline_run_id", table_name="movies")
    with op.batch_alter_table("movies") as batch_op:
        batch_op.drop_constraint(
            "fk_movies_pipeline_run_id_pipeline_runs", type_="foreignkey"
        )
    op.drop_column("movies", "pipeline_run_id")
```

- [ ] **Step 4: Apply the migration to the local dev DB**

Run: `flask --app flask_backend db-upgrade`
Expected: command exits with no errors; `movies` table now has a `pipeline_run_id` column (verify with `sqlite3 development.sqlite ".schema movies"` if you want to double check).

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `pytest flask_backend/tests -q`
Expected: all tests pass (the test DB is built from the SQLAlchemy model metadata directly via `init_db()`, so the new nullable column is picked up automatically — no test should reference it yet).

- [ ] **Step 6: Commit**

```bash
git add flask_backend/models.py migrations/versions/20260727_000000_add_movies_pipeline_run_id.py
git commit -m "feat: add pipeline_run_id to movies for import-run correlation"
```

---

### Task 2: `movies.get_by_title_or_create` reports whether it created a movie

**Files:**
- Modify: `flask_backend/repository/movies.py:18-25` (`create`) and `:96-101` (`get_by_title_or_create`)
- Modify: `flask_backend/routes/screening.py:278` and `:388` (call sites)
- Create: `flask_backend/tests/test_repository/test_movies.py`

**Interfaces:**
- Consumes: `Movie.pipeline_run_id` from Task 1.
- Produces: `movies.create(title, slug=None, pipeline_run_id=None) -> Movie` and `movies.get_by_title_or_create(title, pipeline_run_id=None) -> Tuple[Movie, bool]` (the bool is `True` iff a new `Movie` row was inserted this call). Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_repository/test_movies.py`:

```python
from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository import pipeline_runs
from flask_backend.repository.movies import create, get_by_title_or_create


class TestGetByTitleOrCreate:
    def test_creates_a_new_movie_when_none_exists(self, app):
        with app.app_context():
            movie, was_created = get_by_title_or_create("Filme Novo")

            assert was_created is True
            assert movie.id is not None
            assert movie.slug == "filme-novo"

    def test_returns_existing_movie_without_creating_a_duplicate(self, app):
        with app.app_context():
            first, _ = get_by_title_or_create("Filme Repetido")
            second, was_created = get_by_title_or_create("Filme Repetido")

            assert was_created is False
            assert second.id == first.id
            assert (
                db_session.query(Movie).filter_by(slug="filme-repetido").count() == 1
            )

    def test_threads_pipeline_run_id_through_to_the_created_movie(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")
            movie, was_created = get_by_title_or_create(
                "Filme Via Pipeline", pipeline_run_id=run.id
            )

            assert was_created is True
            assert movie.pipeline_run_id == run.id

    def test_does_not_overwrite_pipeline_run_id_on_an_existing_movie(self, app):
        with app.app_context():
            run_a = pipeline_runs.start("import-json")
            run_b = pipeline_runs.start("import-json")
            first, _ = get_by_title_or_create(
                "Filme Existente", pipeline_run_id=run_a.id
            )
            second, was_created = get_by_title_or_create(
                "Filme Existente", pipeline_run_id=run_b.id
            )

            assert was_created is False
            assert second.pipeline_run_id == run_a.id


class TestCreate:
    def test_leaves_pipeline_run_id_null_by_default(self, app):
        with app.app_context():
            movie = create(title="Filme Manual")
            assert movie.pipeline_run_id is None

    def test_stores_given_pipeline_run_id(self, app):
        with app.app_context():
            run = pipeline_runs.start("import-json")
            movie = create(title="Filme Manual 2", pipeline_run_id=run.id)
            assert movie.pipeline_run_id == run.id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_movies.py -v`
Expected: failures — `create()` raises `TypeError: create() got an unexpected keyword argument 'pipeline_run_id'`, and `get_by_title_or_create()` returns a bare `Movie` so `movie, was_created = ...` raises a `TypeError` on unpacking.

- [ ] **Step 3: Implement the changes**

In `flask_backend/repository/movies.py`, replace:

```python
def create(title: str, slug: Optional[str] = None) -> Movie:
    if slug is None:
        slug = slugify(title)
    movie = Movie(title=title, slug=slug, created_at=datetime.now())
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie
```

with:

```python
def create(
    title: str, slug: Optional[str] = None, pipeline_run_id: Optional[int] = None
) -> Movie:
    if slug is None:
        slug = slugify(title)
    movie = Movie(
        title=title,
        slug=slug,
        created_at=datetime.now(),
        pipeline_run_id=pipeline_run_id,
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie
```

And replace:

```python
def get_by_title_or_create(title: str) -> Movie:
    slug = slugify(title)
    movie = get_by_slug(slug)
    if not movie:
        movie = create(title=title, slug=slug)
    return movie
```

with:

```python
def get_by_title_or_create(
    title: str, pipeline_run_id: Optional[int] = None
) -> Tuple[Movie, bool]:
    slug = slugify(title)
    movie = get_by_slug(slug)
    if movie:
        return movie, False
    movie = create(title=title, slug=slug, pipeline_run_id=pipeline_run_id)
    return movie, True
```

(`Tuple` is already imported at the top of this file: `from typing import List, Optional, Tuple`.)

- [ ] **Step 4: Update the two call sites in `routes/screening.py`**

At `flask_backend/routes/screening.py:278`, change:

```python
            movie = get_movie_by_title_or_create(movie_title)
```

to:

```python
            movie, _ = get_movie_by_title_or_create(movie_title)
```

At `flask_backend/routes/screening.py:388`, change:

```python
            movie = get_movie_by_title_or_create(movie_title)
```

to:

```python
            movie, _ = get_movie_by_title_or_create(movie_title)
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_movies.py -v`
Expected: all pass.

- [ ] **Step 6: Run the screening routes test suite to confirm no regression**

Run: `pytest flask_backend/tests/test_routes -q`
Expected: all pass (the admin create/edit screening flows still work with the tuple-unpacking call sites).

- [ ] **Step 7: Commit**

```bash
git add flask_backend/repository/movies.py flask_backend/routes/screening.py flask_backend/tests/test_repository/test_movies.py
git commit -m "feat: report whether get_by_title_or_create created a new movie"
```

---

### Task 3: `import_scrapped_results` returns accurate movies/screenings/dates counters

**Files:**
- Modify: `flask_backend/service/screening.py:1-37` (imports), `:366-488` (`import_scrapped_results`)
- Modify: `flask_backend/tests/test_service/test_screening.py`

**Interfaces:**
- Consumes: `movies.get_by_title_or_create(title, pipeline_run_id=None) -> Tuple[Movie, bool]` from Task 2.
- Produces: `ImportSummary` dataclass (`movies_created: int`, `screenings_created: int`, `dates_registered: int`) and `import_scrapped_results(...) -> ImportSummary`. Consumed by Task 4 and Task 5.

- [ ] **Step 1: Write the failing tests**

In `flask_backend/tests/test_service/test_screening.py`, add this helper near the existing `_create_scrapped_results_with_title` function (around line 87):

```python
def _create_scrapped_results_with_times(cinema, slug, times):
    return ScrappedResult(
        cinemas=[
            ScrappedCinema(
                url="",
                cinema=cinema,
                slug=slug,
                features=[
                    ScrappedFeature(
                        title="Lobo e Cão",
                        excerpt="cool film",
                        poster="",
                        original_title="",
                        price="",
                        director="",
                        classification="",
                        general_info="",
                        read_more="",
                        time=times,
                    )
                ],
            )
        ]
    )
```

Then add these test methods to `class TestImportScrappedResults:` (after `test_sala_redencao_appends_to_existing_records_for_each_day`, around line 323):

```python
    def test_counts_new_movie_and_new_screening_on_first_import(
        self, client, app, setup_cinemas
    ):
        summary = import_scrapped_results(
            _create_scrapped_results("Capitolio", "capitolio"), app
        )

        assert summary.movies_created == 1
        assert summary.screenings_created == 1
        assert summary.dates_registered == 0

    def test_capitolio_reimporting_identical_dates_registers_no_new_dates(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(_create_scrapped_results("Capitolio", "capitolio"), app)

        summary = import_scrapped_results(
            _create_scrapped_results("Capitolio", "capitolio"), app
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 0

    def test_capitolio_changed_time_and_new_date_register_as_dates_registered(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            _create_movie_on_db(db_session)

        summary = import_scrapped_results(
            _create_scrapped_results("Capitolio", "capitolio"), app
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 1

    def test_appends_a_new_date_to_an_existing_non_capitolio_screening(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(
            _create_scrapped_results("CineBancarios", "cinebancarios"), app
        )

        summary = import_scrapped_results(
            _create_scrapped_results_with_times(
                "CineBancarios",
                "cinebancarios",
                ["2025-12-25T12:00", "2025-12-28T10:00"],
            ),
            app,
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 1

    def test_reimporting_identical_non_capitolio_payload_registers_no_new_dates(
        self, client, app, setup_cinemas
    ):
        import_scrapped_results(
            _create_scrapped_results("CineBancarios", "cinebancarios"), app
        )

        summary = import_scrapped_results(
            _create_scrapped_results("CineBancarios", "cinebancarios"), app
        )

        assert summary.movies_created == 0
        assert summary.screenings_created == 0
        assert summary.dates_registered == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_screening.py -k TestImportScrappedResults -v`
Expected: the five new tests fail with `AttributeError: 'int' object has no attribute 'movies_created'` (the function still returns a bare `created_features` int).

- [ ] **Step 3: Add the `ImportSummary` dataclass**

In `flask_backend/service/screening.py`, add `dataclasses` to the imports — change:

```python
from collections import OrderedDict, defaultdict
from datetime import date, datetime, time, timedelta
```

to:

```python
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
```

Then, immediately above `def import_scrapped_results(` (currently line 366), add:

```python
@dataclass
class ImportSummary:
    movies_created: int
    screenings_created: int
    dates_registered: int
```

- [ ] **Step 4: Rewrite `import_scrapped_results`**

Replace the full function body (currently lines 366-488) with:

```python
def import_scrapped_results(
    scrapped_results: ScrappedResult, current_app, pipeline_run_id: Optional[int] = None
) -> ImportSummary:
    movies_created = 0
    screenings_created = 0
    dates_registered = 0
    scrapped_cinema: ScrappedCinema
    for scrapped_cinema in scrapped_results.cinemas:
        cinema = get_cinema_by_slug(scrapped_cinema.slug)
        scrapped_feature: ScrappedFeature
        for scrapped_feature in scrapped_cinema.features:
            title_cleaning_result = clean_title(scrapped_feature.title)
            if title_cleaning_result.changed:
                logger.info(
                    "Título limpo na importação: '%s' -> '%s' (regras: %s)",
                    title_cleaning_result.raw_title,
                    title_cleaning_result.cleaned_title,
                    ", ".join(title_cleaning_result.matched_rules),
                )
            movie, movie_created = get_movie_by_title_or_create(
                title_cleaning_result.cleaned_title, pipeline_run_id=pipeline_run_id
            )
            if movie_created:
                movies_created += 1

            description: str = ""
            screenings_dates = None
            if scrapped_feature.time:
                screenings_dates = build_dates(scrapped_feature.time)
            if scrapped_feature.original_title:
                description += f"\n{scrapped_feature.original_title.strip()}"
            if scrapped_feature.price:
                description += f"\n{scrapped_feature.price}"
            if scrapped_feature.director:
                description += f"\n{scrapped_feature.director}"
            if scrapped_feature.classification:
                description += f"\n{scrapped_feature.classification}"
            if scrapped_feature.general_info:
                description += f"\n{scrapped_feature.general_info}"
            if scrapped_feature.excerpt:
                description += f"\n{scrapped_feature.excerpt}"

            description = description.strip()

            if screenings_dates is None:
                screenings_dates = build_dates(
                    [datetime.now().strftime("%Y-%m-%dT%H:%M")]
                )
            screening = get_screening_by_movie_id_and_cinema_id(movie.id, cinema.id)

            if not screening:
                # only attempt to download the poster if the screening doesn't previously exists
                img, image_filename, image_width, image_height = None, None, None, None
                if scrapped_feature.poster:
                    img, filename = download_image_from_url(scrapped_feature.poster)

                if img is not None:
                    # if we fail to download or validate the image, just ignore it for now
                    image_filename, image_width, image_height = save_image(
                        img, current_app, filename
                    )

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
                screenings_created += 1
            else:
                update_title_cleaning_info(
                    screening,
                    title_cleaning_result.raw_title,
                    title_cleaning_result.matched_rules,
                )
                # captured before any of the filtering below mutates what
                # "existing" means, so it reflects what was truly on file
                # before this run - see issue #249
                original_date_time_pairs = {
                    (sd.date, sd.time) for sd in screening.dates
                }
                if cinema.slug == "capitolio":
                    # capitolio may occasionally change
                    # screening times for a given movie
                    # so records for any given day could become obsolete
                    # our strategy is, for every day included in the current run,
                    # we delete existing records and trust the new ones
                    # see issue #163

                    # ex. existing_dates_for_screening = [ 12/12/2025, 13/12/2025, 14/12/2025 ]
                    existing_dates_for_screening = list(screening.dates)

                    # ex. [13/12/2025, 14/12/2025]
                    received_dates_for_screening = [sd.date for sd in screenings_dates]

                    # we skip screening_dates for dates in the
                    # `received_dates_for_screening` list, so they can be recreated
                    # ex. existing_dates = [ 12/12/2025 ]
                    existing_dates = build_dates(
                        [
                            f"{sd.date}T{sd.time}"
                            for sd in existing_dates_for_screening
                            if sd.date not in received_dates_for_screening
                        ]
                    )
                else:
                    # create new ScreeningDate objects from existing ones
                    # to prevent reference errors
                    existing_dates = build_dates(
                        [f"{sd.date}T{sd.time}" for sd in screening.dates]
                    )
                # append new dates to the list by checking if there is no
                # other date with an equal date and time fields
                for new_date in screenings_dates:
                    already_registered = False
                    for existing_date in existing_dates:
                        same_date = existing_date.date == new_date.date
                        same_time = existing_date.time == new_date.time
                        if same_date and same_time:
                            already_registered = True
                            break
                    if not already_registered:
                        existing_dates.append(new_date)
                update_screening_dates(screening, existing_dates)

                got_new_date = any(
                    (nd.date, nd.time) not in original_date_time_pairs
                    for nd in screenings_dates
                )
                if got_new_date:
                    dates_registered += 1
    return ImportSummary(
        movies_created=movies_created,
        screenings_created=screenings_created,
        dates_registered=dates_registered,
    )
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening.py -k TestImportScrappedResults -v`
Expected: all pass, including the Capitólio regression test.

- [ ] **Step 6: Run the full service test file to confirm no regression**

Run: `pytest flask_backend/tests/test_service/test_screening.py -q`
Expected: all pass (existing behavioral tests for date storage/appending/title-cleaning are untouched by this change).

- [ ] **Step 7: Commit**

```bash
git add flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py
git commit -m "feat: replace scraper import feature counter with accurate movies/screenings/dates counts"
```

---

### Task 4: `Runner.import_scrapped_results` passes the new summary through

**Files:**
- Modify: `flask_backend/service/runner.py`
- Modify: `flask_backend/tests/test_service/test_runner.py`

**Interfaces:**
- Consumes: `ImportSummary` and `import_scrapped_results(...) -> ImportSummary` from Task 3.
- Produces: `Runner.import_scrapped_results(current_app, pipeline_run_id=None) -> ImportSummary`. Consumed by Task 5.

- [ ] **Step 1: Update the failing test**

In `flask_backend/tests/test_service/test_runner.py`, replace:

```python
from unittest.mock import MagicMock, patch

from flask_backend.service.runner import Runner
```

with:

```python
from unittest.mock import MagicMock, patch

from flask_backend.service.runner import Runner
from flask_backend.service.screening import ImportSummary
```

And replace the body of `test_import_scrapped_results_delegates_to_service`:

```python
    def test_import_scrapped_results_delegates_to_service(self):
        runner = Runner()
        runner.scrapped_results = MagicMock()
        fake_app = MagicMock()

        with patch(
            "flask_backend.service.runner.import_scrapped_results",
            return_value=5,
        ) as mock_import:
            result = runner.import_scrapped_results(fake_app)

        mock_import.assert_called_once_with(
            runner.scrapped_results, fake_app, pipeline_run_id=None
        )
        assert result == 5
```

with:

```python
    def test_import_scrapped_results_delegates_to_service(self):
        runner = Runner()
        runner.scrapped_results = MagicMock()
        fake_app = MagicMock()
        fake_summary = ImportSummary(
            movies_created=1, screenings_created=2, dates_registered=3
        )

        with patch(
            "flask_backend.service.runner.import_scrapped_results",
            return_value=fake_summary,
        ) as mock_import:
            result = runner.import_scrapped_results(fake_app)

        mock_import.assert_called_once_with(
            runner.scrapped_results, fake_app, pipeline_run_id=None
        )
        assert result is fake_summary
```

- [ ] **Step 2: Run the test to verify it still passes at the type level but reflects the new contract**

Run: `pytest flask_backend/tests/test_service/test_runner.py -v`
Expected: PASS — `Runner.import_scrapped_results` is a pure passthrough, so no implementation change is strictly required yet, but Step 3 updates the type hint for clarity and to keep it honest.

- [ ] **Step 3: Update the type hint**

In `flask_backend/service/runner.py`, replace:

```python
from typing import Optional

from flask_backend.import_json import ScrappedResult
from flask_backend.service.screening import import_scrapped_results


class Runner:
    def parse_scrapped_json(self, features):
        self.scrapped_results: ScrappedResult = ScrappedResult.from_jsonable(features)

    def import_scrapped_results(
        self, current_app, pipeline_run_id: Optional[int] = None
    ):
        return import_scrapped_results(
            self.scrapped_results, current_app, pipeline_run_id=pipeline_run_id
        )
```

with:

```python
from typing import Optional

from flask_backend.import_json import ScrappedResult
from flask_backend.service.screening import ImportSummary, import_scrapped_results


class Runner:
    def parse_scrapped_json(self, features):
        self.scrapped_results: ScrappedResult = ScrappedResult.from_jsonable(features)

    def import_scrapped_results(
        self, current_app, pipeline_run_id: Optional[int] = None
    ) -> ImportSummary:
        return import_scrapped_results(
            self.scrapped_results, current_app, pipeline_run_id=pipeline_run_id
        )
```

- [ ] **Step 4: Run the test again to confirm it still passes**

Run: `pytest flask_backend/tests/test_service/test_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/runner.py flask_backend/tests/test_service/test_runner.py
git commit -m "refactor: type Runner.import_scrapped_results as returning ImportSummary"
```

---

### Task 5: `import-json` CLI reports accurate summary and status

**Files:**
- Modify: `flask_backend/commands.py:70-78`
- Modify: `flask_backend/tests/test_service/test_commands.py`

**Interfaces:**
- Consumes: `Runner.import_scrapped_results(...) -> ImportSummary` from Task 4.

- [ ] **Step 1: Update the failing tests**

In `flask_backend/tests/test_service/test_commands.py`, in `test_success_imports_screenings` (around line 42-68), replace:

```python
        result = runner.invoke(args=["import-json", str(json_path)])
        assert "sessões criadas com sucesso" in result.output
```

with:

```python
        result = runner.invoke(args=["import-json", str(json_path)])
        assert "novos horários registrados" in result.output
```

In `test_success_creates_pipeline_run_with_source_and_summary` (around line 70-113), replace:

```python
            assert run.status == "success"
            assert run.source == "capitolio"
            assert run.finished_at is not None
            assert '"created": 1' in run.summary
```

with:

```python
            assert run.status == "success"
            assert run.source == "capitolio"
            assert run.finished_at is not None
            assert '"movies_created": 1' in run.summary
            assert '"screenings_created": 1' in run.summary
            assert '"dates_registered": 0' in run.summary
```

Leave `test_zero_screenings_created_marks_run_as_warning` (around line 115-137) unchanged — an empty-features payload should still yield `status == "warning"` under the new logic (all three counters are zero).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k TestImportJsonCommand -v`
Expected: the two updated tests fail against the current `commands.py` (old echo text and old `"created"` summary key).

- [ ] **Step 3: Update `_run_import_json`**

In `flask_backend/commands.py`, replace:

```python
    # all validations passed, import screenings :)
    created_features = runner.import_scrapped_results(
        current_app, pipeline_run_id=run.id
    )
    status = "warning" if created_features == 0 else "success"
    pipeline_runs.finish(
        run.id, status=status, summary=json.dumps({"created": created_features})
    )
    click.echo(f"«{created_features}» sessões criadas com sucesso!")
```

with:

```python
    # all validations passed, import screenings :)
    summary = runner.import_scrapped_results(current_app, pipeline_run_id=run.id)
    status = (
        "warning"
        if summary.movies_created == 0
        and summary.screenings_created == 0
        and summary.dates_registered == 0
        else "success"
    )
    pipeline_runs.finish(
        run.id,
        status=status,
        summary=json.dumps(
            {
                "movies_created": summary.movies_created,
                "screenings_created": summary.screenings_created,
                "dates_registered": summary.dates_registered,
            }
        ),
    )
    click.echo(
        f"«{summary.movies_created}» filmes, «{summary.screenings_created}» sessões "
        f"e «{summary.dates_registered}» novos horários registrados!"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k TestImportJsonCommand -v`
Expected: all pass.

- [ ] **Step 5: Run the full commands test file to confirm no regression**

Run: `pytest flask_backend/tests/test_service/test_commands.py -q`
Expected: all pass (unrelated commands — `fetch-posters`, `fetch-movie-metadata`, etc. — are untouched).

- [ ] **Step 6: Commit**

```bash
git add flask_backend/commands.py flask_backend/tests/test_service/test_commands.py
git commit -m "feat: report accurate movies/screenings/dates counts from import-json"
```

---

### Task 6: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest`
Expected: all tests pass, no failures.

- [ ] **Step 2: Run coverage**

Run: `coverage run -m pytest && coverage report -m`
Expected: passes; no significant coverage drop in `flask_backend/service/screening.py`, `flask_backend/repository/movies.py`, or `flask_backend/commands.py`.

- [ ] **Step 3: Lint and format**

Run each and fix anything flagged:

```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```

Expected: clean (no template files were touched by this change, so djlint should report nothing to do).

- [ ] **Step 4: Manual verification against a real import**

```bash
flask --app flask_backend init-db
flask --app flask_backend seed-db
```

Create a small scraped JSON fixture reusing the shape from `flask_backend/tests/test_service/test_commands.py`'s payloads (one Capitólio feature with a title and a `time` array), save it to a temp path, then run:

```bash
flask --app flask_backend import-json /path/to/fixture.json
```

Expected: echo line reads `«1» filmes, «1» sessões e «0» novos horários registrados!`. Run the exact same command again with the same file:

Expected: echo line reads `«0» filmes, «0» sessões e «0» novos horários registrados!` — confirming a true no-op re-import no longer claims anything was "created." Check `/admin/pipelines` in a running dev server (`flask --app flask_backend run --debug`) to confirm the index page's summary now shows `movies_created`/`screenings_created`/`dates_registered` instead of `created`, and that the second run is marked "Alerta" (warning) instead of "Sucesso."

- [ ] **Step 5: No commit needed for this task** (verification only — if Step 3 produced any lint/format fixes, commit those separately with `git commit -m "style: apply ruff/djlint fixes"`).
