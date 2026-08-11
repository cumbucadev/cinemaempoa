# Cinema-Aware Title Collision Resolution on Import (#316) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the scraper import pipeline from silently attaching a screening to the wrong movie when its title collides with an existing movie's slug family (base slug + `create_distinct`-style numbered siblings, e.g. `noite` / `noite-2`) — resolve via the incoming cinema when it unambiguously picks one candidate, otherwise keep today's fallback but flag it for admin review.

**Architecture:** A new repository function `resolve_for_screening(title, cinema_id, pipeline_run_id=None)` in `flask_backend/repository/movies.py` replaces the plain-slug lookup used by the import pipeline. It finds the base-slug movie's disambiguated siblings (exact `^{base}-\d+$` slug pattern, not the fuzzy ilike-based `get_movies_with_similar_titles`), and — only when siblings exist — picks whichever single candidate already has a screening at the incoming cinema. `import_scrapped_results` (`flask_backend/service/screening.py`) is wired to call it and records unresolved collisions on a new `ImportSummary.ambiguous_collisions` field. `commands.py::_run_import_json` folds that list into the JSON `summary` it already writes to `pipeline_runs` (visible today, with zero template changes, on `/admin/pipelines` via its generic `| tojson` dump) and sets `status="warning"` when any collision was flagged.

**Tech Stack:** Flask, SQLAlchemy, `python-slugify`, `re` (stdlib), pytest.

## Global Constraints

- No database migration — this design adds no columns or tables.
- Do not touch `flask_backend/scripts/dedupper.py` or `flask_backend/scripts/dupechecker.py` (`dupe-check` / `run-dedupper`) — extending them to also report title-family collisions is explicitly out of scope for this ticket (see spec's Non-goals).
- Do not touch `/screening/<id>/movie`, `force_new_movie`, or `create_distinct` — they're the existing fix-up path for whatever this design flags, not something this design changes.
- Sibling detection MUST use the exact pattern `^{base_slug}-\d+$` (what `create_distinct` produces). Do NOT reuse `get_movies_with_similar_titles` for this — it does a substring `ilike` match and would treat unrelated titles (e.g. "Noites Paraguayas" next to "Noite") as siblings.
- `resolve_for_screening` must never raise for the ambiguous case — it always returns a usable `Movie` (the base-slug movie), matching today's behavior, so the import pipeline can't regress to a hard failure.
- Run `uv run ruff check --fix <files>` and `uv run ruff format <files>` on every Python file touched, before each task's commit.
- Never add an AI/agent co-author trailer to commits (project rule, `CLAUDE.md`).

---

### Task 1: `resolve_for_screening` repository function

**Files:**
- Modify: `flask_backend/repository/movies.py` (imports at lines 1-16; insert new code between `create_distinct` (ends line 121) and `get_movies_with_similar_titles` (starts line 124))
- Test: `flask_backend/tests/test_repository/test_movies.py`

**Interfaces:**
- Produces: `resolve_for_screening(title: str, cinema_id: int, pipeline_run_id: Optional[int] = None) -> Tuple[Movie, bool, bool, List[int]]` in `flask_backend/repository/movies.py`, importable as `from flask_backend.repository.movies import resolve_for_screening`. Returns `(movie, created, ambiguous, candidate_movie_ids)`:
  - `created`: `True` only when no movie existed for this slug at all (brand-new base movie).
  - `ambiguous`: `True` when the title collides with a disambiguated family (base slug + numbered siblings) and `cinema_id` doesn't unambiguously pick one of them (zero or more than one candidate already has a screening there). The base-slug movie is still returned in that case.
  - `candidate_movie_ids`: the colliding family's movie ids (`[base_movie.id, *sibling_ids]`), populated only when `ambiguous` is `True`; `[]` otherwise.
- Consumes: `get_by_movie_id_and_cinema_id` from `flask_backend/repository/screenings.py` (existing, unchanged) — confirmed safe to import into `movies.py` (`screenings.py` does not import `movies.py`, so no circular import).

- [ ] **Step 1: Write the failing tests**

In `flask_backend/tests/test_repository/test_movies.py`, update the top imports:

```python
from datetime import date

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository import pipeline_runs
from flask_backend.repository.movies import (
    create,
    create_distinct,
    get_by_title_or_create,
    get_movies_with_similar_titles,
    resolve_for_screening,
)
```

Append this new class at the end of the file (after `TestCreateDistinct`):

```python
class TestResolveForScreening:
    def test_creates_a_new_movie_when_none_exists(self, app):
        with app.app_context():
            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Filme Inédito", cinema_id=1
            )

            assert created is True
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.slug == "filme-inedito"

    def test_returns_base_movie_when_no_siblings_exist(self, app):
        with app.app_context():
            base, _ = get_by_title_or_create("Filme Solo")

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Filme Solo", cinema_id=1
            )

            assert created is False
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.id == base.id

    def test_resolves_to_sibling_with_matching_cinema_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            get_by_title_or_create("Noite")
            sibling = create_distinct("Noite")
            db_session.add(
                Screening(
                    movie_id=sibling.id,
                    cinema_id=2,  # sala-redencao
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            db_session.commit()
            sibling_id = sibling.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=2
            )

            assert created is False
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.id == sibling_id

    def test_resolves_to_base_movie_when_base_has_the_matching_cinema_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            db_session.add(
                Screening(
                    movie_id=base.id,
                    cinema_id=1,  # capitolio
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            create_distinct("Noite")
            db_session.commit()
            base_id = base.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=1
            )

            assert created is False
            assert ambiguous is False
            assert candidate_ids == []
            assert movie.id == base_id

    def test_flags_ambiguous_when_no_candidate_has_the_cinema_screening(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            sibling = create_distinct("Noite")
            db_session.add(
                Screening(
                    movie_id=base.id,
                    cinema_id=1,  # capitolio
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            db_session.commit()
            base_id, sibling_id = base.id, sibling.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=3  # cinebancarios: neither candidate plays here
            )

            assert created is False
            assert ambiguous is True
            assert movie.id == base_id
            assert set(candidate_ids) == {base_id, sibling_id}

    def test_flags_ambiguous_when_more_than_one_candidate_matches_the_cinema(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            sibling = create_distinct("Noite")
            db_session.add_all(
                [
                    Screening(
                        movie_id=base.id,
                        cinema_id=1,
                        description="",
                        dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                    ),
                    Screening(
                        movie_id=sibling.id,
                        cinema_id=1,
                        description="",
                        dates=[ScreeningDate(date=date(2026, 8, 11), time="21:00")],
                    ),
                ]
            )
            db_session.commit()
            base_id = base.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=1
            )

            assert ambiguous is True
            assert movie.id == base_id

    def test_does_not_treat_a_same_substring_title_as_a_sibling(
        self, app, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            db_session.add(Movie(title="Noites Paraguayas", slug="noites-paraguayas"))
            db_session.add(
                Screening(
                    movie_id=base.id,
                    cinema_id=1,
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 10), time="19:00")],
                )
            )
            db_session.commit()
            base_id = base.id

            movie, created, ambiguous, candidate_ids = resolve_for_screening(
                "Noite", cinema_id=1
            )

            assert ambiguous is False
            assert movie.id == base_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_movies.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_for_screening'`

- [ ] **Step 3: Implement `resolve_for_screening`**

In `flask_backend/repository/movies.py`, change the import block (currently lines 1-16):

```python
from datetime import datetime
from math import ceil
from typing import List, Optional, Tuple

from slugify import slugify
from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import (
    Movie,
    MovieMetadataFetchAttempt,
    PosterFetchAttempt,
    Screening,
)
from flask_backend.repository import alert_actions
```

to:

```python
import re
from datetime import datetime
from math import ceil
from typing import List, Optional, Tuple

from slugify import slugify
from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import (
    Movie,
    MovieMetadataFetchAttempt,
    PosterFetchAttempt,
    Screening,
)
from flask_backend.repository import alert_actions
from flask_backend.repository.screenings import (
    get_by_movie_id_and_cinema_id as get_screening_by_movie_id_and_cinema_id,
)
```

Then insert this new code between `create_distinct` (ends at line 121, `return create(title=title, slug=slug, pipeline_run_id=pipeline_run_id)`) and `def get_movies_with_similar_titles(...)`:

```python
def _get_disambiguated_siblings(base_slug: str) -> List[Movie]:
    """Movies whose slug is `base_slug` followed by a numeric suffix - the
    exact pattern create_distinct() produces (e.g. `noite-2`, `noite-3`).
    Deliberately not the fuzzy ilike match used by
    get_movies_with_similar_titles, which also matches unrelated titles
    that merely contain the same substring."""
    candidates = db_session.query(Movie).filter(Movie.slug.like(f"{base_slug}-%")).all()
    pattern = re.compile(rf"^{re.escape(base_slug)}-\d+$")
    return [movie for movie in candidates if pattern.match(movie.slug)]


def resolve_for_screening(
    title: str, cinema_id: int, pipeline_run_id: Optional[int] = None
) -> Tuple[Movie, bool, bool, List[int]]:
    """Resolves a scraped title to a Movie for a given cinema, aware of
    disambiguated slug siblings created via create_distinct (e.g. a title
    collides with an existing `noite` slug, but a separate `noite-2` movie
    already exists for a different film).

    Returns (movie, created, ambiguous, candidate_movie_ids):
    - created: True only when no movie existed for this slug at all.
    - ambiguous: True when the title collides with a disambiguated family
      and cinema_id doesn't unambiguously pick one of them (zero or more
      than one candidate already has a screening at that cinema). The
      base-slug movie is still returned in that case - same fallback as
      before this function existed, just flagged.
    - candidate_movie_ids: the colliding family's movie ids, populated only
      when ambiguous is True.
    """
    slug = slugify(title)
    base_movie = get_by_slug(slug)
    if base_movie is None:
        movie = create(title=title, slug=slug, pipeline_run_id=pipeline_run_id)
        return movie, True, False, []

    siblings = _get_disambiguated_siblings(slug)
    if not siblings:
        return base_movie, False, False, []

    candidates = [base_movie, *siblings]
    matches = [
        candidate
        for candidate in candidates
        if get_screening_by_movie_id_and_cinema_id(candidate.id, cinema_id) is not None
    ]
    if len(matches) == 1:
        return matches[0], False, False, []

    return base_movie, False, True, [candidate.id for candidate in candidates]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_movies.py -v`
Expected: PASS (all tests in the file, including the new `TestResolveForScreening` class)

- [ ] **Step 5: Run the full test suite to check for circular-import or regression issues**

Run: `pytest flask_backend/tests -x -q`
Expected: PASS

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check --fix flask_backend/repository/movies.py flask_backend/tests/test_repository/test_movies.py && uv run ruff format flask_backend/repository/movies.py flask_backend/tests/test_repository/test_movies.py`

- [ ] **Step 7: Commit**

```bash
git add flask_backend/repository/movies.py flask_backend/tests/test_repository/test_movies.py
git commit -m "feat: resolve movie title collisions by cinema match in resolve_for_screening"
```

---

### Task 2: Wire `resolve_for_screening` into `import_scrapped_results`

**Files:**
- Modify: `flask_backend/service/screening.py` (imports at lines 1-23; `ImportSummary` dataclass at lines 380-384; `import_scrapped_results` at lines 387-539)
- Test: `flask_backend/tests/test_service/test_screening.py`

**Interfaces:**
- Consumes: `resolve_for_screening(title: str, cinema_id: int, pipeline_run_id: Optional[int] = None) -> Tuple[Movie, bool, bool, List[int]]` from Task 1.
- Produces: `ImportSummary.ambiguous_collisions: List[dict]` (default `[]`), each entry shaped `{"screening_id": int, "title": str, "cinema": str, "attached_movie_id": int, "candidate_movie_ids": List[int]}`. `import_scrapped_results` return value now carries this field — Task 3 consumes it.

- [ ] **Step 1: Write the failing tests**

Append this new class at the end of `flask_backend/tests/test_service/test_screening.py` (no new imports needed — `Movie`, `Screening`, `ScreeningDate`, `import_scrapped_results`, `_create_scrapped_results_with_title` and `_get_date` are already imported/defined in this file):

```python
class TestImportScrappedResultsTitleCollisions:
    def test_attaches_to_the_disambiguated_sibling_with_a_matching_cinema_screening(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            base = Movie(
                title="Noite",
                slug="noite",
                screenings=[
                    Screening(
                        cinema_id=1,  # capitolio
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-01"), time="19:00")
                        ],
                    )
                ],
            )
            sibling = Movie(
                title="Noite",
                slug="noite-2",
                screenings=[
                    Screening(
                        cinema_id=2,  # sala-redencao
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-02"), time="21:00")
                        ],
                    )
                ],
            )
            db_session.add_all([base, sibling])
            db_session.commit()
            base_id, sibling_id = base.id, sibling.id

        summary = import_scrapped_results(
            _create_scrapped_results_with_title(
                "Sala Redenção", "sala-redencao", "Noite"
            ),
            app,
        )

        assert summary.movies_created == 0
        assert summary.ambiguous_collisions == []
        with client.application.app_context():
            sibling_screenings = (
                db_session.query(Screening).filter_by(movie_id=sibling_id).all()
            )
            assert len(sibling_screenings) == 1
            base_screenings = (
                db_session.query(Screening).filter_by(movie_id=base_id).all()
            )
            assert len(base_screenings) == 1

    def test_flags_ambiguous_collision_when_no_sibling_matches_the_cinema(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            base = Movie(
                title="Noite",
                slug="noite",
                screenings=[
                    Screening(
                        cinema_id=1,  # capitolio
                        description="",
                        dates=[
                            ScreeningDate(date=_get_date("2025-12-01"), time="19:00")
                        ],
                    )
                ],
            )
            sibling = Movie(title="Noite", slug="noite-2")
            db_session.add_all([base, sibling])
            db_session.commit()
            base_id, sibling_id = base.id, sibling.id

        summary = import_scrapped_results(
            _create_scrapped_results_with_title(
                "Paulo Amorim", "paulo-amorim", "Noite"
            ),
            app,
        )

        assert len(summary.ambiguous_collisions) == 1
        collision = summary.ambiguous_collisions[0]
        assert collision["attached_movie_id"] == base_id
        assert set(collision["candidate_movie_ids"]) == {base_id, sibling_id}
        assert collision["cinema"] == "paulo-amorim"
        with client.application.app_context():
            screening = db_session.get(Screening, collision["screening_id"])
            assert screening.movie_id == base_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_screening.py -k TestImportScrappedResultsTitleCollisions -v`
Expected: FAIL — the first test fails because the screening is created on the base movie (`noite`) instead of updating the sibling's (`noite-2`) existing screening (`len(sibling_screenings) == 1` fails, or `len(base_screenings) == 1` fails because a second screening was created on the base movie); the second test fails with `AttributeError: 'ImportSummary' object has no attribute 'ambiguous_collisions'`.

- [ ] **Step 3: Update the `ImportSummary` dataclass and imports**

In `flask_backend/service/screening.py`, change the dataclasses import (currently line 5):

```python
from dataclasses import dataclass
```

to:

```python
from dataclasses import dataclass, field
```

Change the movies import (currently lines 21-23):

```python
from flask_backend.repository.movies import (
    get_by_title_or_create as get_movie_by_title_or_create,
)
```

to:

```python
from flask_backend.repository.movies import (
    resolve_for_screening as resolve_movie_for_screening,
)
```

Change the `ImportSummary` dataclass (currently lines 380-384):

```python
@dataclass
class ImportSummary:
    movies_created: int
    screenings_created: int
    dates_registered: int
```

to:

```python
@dataclass
class ImportSummary:
    movies_created: int
    screenings_created: int
    dates_registered: int
    ambiguous_collisions: List[dict] = field(default_factory=list)
```

- [ ] **Step 4: Wire `resolve_for_screening` into the import loop**

In `flask_backend/service/screening.py`, in `import_scrapped_results`, change the function's local-state setup (currently lines 390-392):

```python
    movies_created = 0
    screenings_created = 0
    screenings_with_new_dates: Set[int] = set()
```

to:

```python
    movies_created = 0
    screenings_created = 0
    screenings_with_new_dates: Set[int] = set()
    ambiguous_collisions: List[dict] = []
```

Change the movie resolution call (currently lines 406-410):

```python
            movie, movie_created = get_movie_by_title_or_create(
                title_cleaning_result.cleaned_title, pipeline_run_id=pipeline_run_id
            )
            if movie_created:
                movies_created += 1
```

to:

```python
            movie, movie_created, ambiguous, candidate_movie_ids = (
                resolve_movie_for_screening(
                    title_cleaning_result.cleaned_title,
                    cinema.id,
                    pipeline_run_id=pipeline_run_id,
                )
            )
            if movie_created:
                movies_created += 1
```

Change the screening-creation branch (currently lines 450-466):

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
                screenings_created += 1
```

to:

```python
                new_screening = create_screening(
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
                if ambiguous:
                    ambiguous_collisions.append(
                        {
                            "screening_id": new_screening.id,
                            "title": title_cleaning_result.cleaned_title,
                            "cinema": cinema.slug,
                            "attached_movie_id": movie.id,
                            "candidate_movie_ids": candidate_movie_ids,
                        }
                    )
```

Change the end of the update (`else`) branch — the last line of the loop body (currently `update_screening_dates(screening, existing_dates)`) — to also record a collision:

```python
                update_screening_dates(screening, existing_dates)
                if ambiguous:
                    ambiguous_collisions.append(
                        {
                            "screening_id": screening.id,
                            "title": title_cleaning_result.cleaned_title,
                            "cinema": cinema.slug,
                            "attached_movie_id": movie.id,
                            "candidate_movie_ids": candidate_movie_ids,
                        }
                    )
```

Finally, change the return statement (currently lines 535-539):

```python
    return ImportSummary(
        movies_created=movies_created,
        screenings_created=screenings_created,
        dates_registered=len(screenings_with_new_dates),
    )
```

to:

```python
    return ImportSummary(
        movies_created=movies_created,
        screenings_created=screenings_created,
        dates_registered=len(screenings_with_new_dates),
        ambiguous_collisions=ambiguous_collisions,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening.py -k TestImportScrappedResultsTitleCollisions -v`
Expected: PASS

- [ ] **Step 6: Run the full service test file and the runner test to check for regressions**

Run: `pytest flask_backend/tests/test_service/test_screening.py flask_backend/tests/test_service/test_runner.py -v`
Expected: PASS — `test_runner.py::TestRunnerImportScrappedResults::test_import_scrapped_results_delegates_to_service` must still pass unmodified, since `ambiguous_collisions` has a default (`field(default_factory=list)`) and that test constructs `ImportSummary(movies_created=1, screenings_created=2, dates_registered=3)` without it.

- [ ] **Step 7: Run the full test suite**

Run: `pytest flask_backend/tests -x -q`
Expected: PASS

- [ ] **Step 8: Lint and format**

Run: `uv run ruff check --fix flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py && uv run ruff format flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py`

- [ ] **Step 9: Commit**

```bash
git add flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py
git commit -m "feat: use cinema-aware movie resolution in import_scrapped_results"
```

---

### Task 3: Surface ambiguous collisions in the pipeline-run summary

**Files:**
- Modify: `flask_backend/commands.py:84-98` (`_run_import_json`)
- Test: `flask_backend/tests/test_service/test_commands.py`

**Interfaces:**
- Consumes: `ImportSummary.ambiguous_collisions: List[dict]` from Task 2.
- Produces: no new interfaces for other tasks — this is the final, user-facing piece. The `pipeline_runs.summary` JSON column gains an `"ambiguous_collisions"` key (always present, `[]` when empty), and `status` becomes `"warning"` whenever that list is non-empty (in addition to the existing `features_processed == 0` warning trigger). `/admin/pipelines` (index, history, detail pages) already render `summary` generically via `| tojson`, so this requires no template changes.

- [ ] **Step 1: Write the failing test**

In `flask_backend/tests/test_service/test_commands.py`, update the top imports:

```python
from datetime import date
import json
import logging
from unittest.mock import patch

from flask_backend.db import db_session
from flask_backend.models import PipelineRun, Screening, ScreeningDate
from flask_backend.repository.movies import create_distinct, get_by_title_or_create
from flask_backend.service.image_resize_pipeline import (
    ResizePipelineResult,
)
from flask_backend.service.movie_inspector import (
    PipelineResult as InspectionPipelineResult,
)
from flask_backend.service.movie_metadata_pipeline import (
    PipelineResult as MetadataPipelineResult,
)
from flask_backend.service.poster_pipeline import PipelineResult as PosterPipelineResult
```

Append this test inside `TestImportJsonCommand` (after `test_reimporting_identical_payload_stays_success_not_warning`):

```python
    def test_ambiguous_title_collision_marks_run_as_warning(
        self, app, runner, tmp_path, setup_cinemas
    ):
        with app.app_context():
            base, _ = get_by_title_or_create("Noite")
            db_session.add(
                Screening(
                    movie_id=base.id,
                    cinema_id=1,  # capitolio
                    description="",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            )
            create_distinct("Noite")
            db_session.commit()
            base_id = base.id

        payload = [
            {
                "url": "",
                "cinema": "Cine Cinco",
                "slug": "cine-cinco",
                "features": [
                    {
                        "poster": "",
                        "time": ["2026-08-15T20:00"],
                        "title": "Noite",
                        "original_title": "",
                        "price": "",
                        "director": "",
                        "classification": "",
                        "general_info": "",
                        "excerpt": "",
                        "read_more": "",
                    }
                ],
            }
        ]
        json_path = tmp_path / "ambiguous.json"
        json_path.write_text(json.dumps(payload))

        runner.invoke(args=["import-json", str(json_path)])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="import-json")
                .one()
            )
            assert run.status == "warning"
            summary_obj = json.loads(run.summary)
            assert len(summary_obj["ambiguous_collisions"]) == 1
            collision = summary_obj["ambiguous_collisions"][0]
            assert collision["attached_movie_id"] == base_id
            assert collision["cinema"] == "cine-cinco"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k test_ambiguous_title_collision_marks_run_as_warning -v`
Expected: FAIL — `run.status == "warning"` fails (still `"success"`), since `_run_import_json` doesn't check `ambiguous_collisions` yet, and `summary_obj["ambiguous_collisions"]` raises `KeyError`.

- [ ] **Step 3: Update `_run_import_json`**

In `flask_backend/commands.py`, change (currently lines 84-98):

```python
    summary = runner.import_scrapped_results(current_app, pipeline_run_id=run.id)
    status = "warning" if features_processed == 0 else "success"
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
```

to:

```python
    summary = runner.import_scrapped_results(current_app, pipeline_run_id=run.id)
    status = (
        "warning"
        if features_processed == 0 or summary.ambiguous_collisions
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
                "ambiguous_collisions": summary.ambiguous_collisions,
            }
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k TestImportJsonCommand -v`
Expected: PASS (all tests in `TestImportJsonCommand`, including the new one, and the two existing summary-content assertions in `test_success_creates_pipeline_run_with_source_and_summary` and `test_reimporting_identical_payload_stays_success_not_warning` still pass — they check `in run.summary` substrings, unaffected by the added key)

- [ ] **Step 5: Run the full test suite**

Run: `pytest flask_backend/tests -x -q`
Expected: PASS

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check --fix flask_backend/commands.py flask_backend/tests/test_service/test_commands.py && uv run ruff format flask_backend/commands.py flask_backend/tests/test_service/test_commands.py`

- [ ] **Step 7: Commit**

```bash
git add flask_backend/commands.py flask_backend/tests/test_service/test_commands.py
git commit -m "feat: surface ambiguous title collisions in the import-json pipeline-run summary"
```

---

### Task 4: Manual verification against the reported #316 scenario

**Files:** none (verification only)

**Interfaces:** none — this task consumes Tasks 1-3 end-to-end and produces no code.

- [ ] **Step 1: Reproduce the ticket's scenario in the dev database**

Run: `flask --app flask_backend shell` and execute:

```python
from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.movies import create_distinct, get_by_title_or_create
from datetime import date

base, _ = get_by_title_or_create("Noite")
db_session.add(Screening(movie_id=base.id, cinema_id=1, description="", dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")]))
sibling = create_distinct("Noite")
db_session.add(Screening(movie_id=sibling.id, cinema_id=2, description="", dates=[ScreeningDate(date=date(2026, 8, 12), time="19:00")]))
db_session.commit()
print(base.id, base.slug, sibling.id, sibling.slug)
```

- [ ] **Step 2: Build a scrape JSON that reintroduces "Noite" at Sala Redenção**

Write a file `/tmp/noite-import.json` (or use the scratchpad directory) with:

```json
[
  {
    "url": "",
    "cinema": "Sala Redenção",
    "slug": "sala-redencao",
    "features": [
      {
        "poster": "",
        "time": ["2026-08-13T19:00"],
        "title": "Noite",
        "original_title": "",
        "price": "",
        "director": "",
        "classification": "",
        "general_info": "",
        "excerpt": "",
        "read_more": ""
      }
    ]
  }
]
```

- [ ] **Step 3: Run the import and confirm it resolves to the sibling**

Run: `flask --app flask_backend import-json /tmp/noite-import.json`

In the shell again, confirm the new date landed on `sibling`, not `base`:

```python
from flask_backend.repository.screenings import get_by_movie_id_and_cinema_id
screening = get_by_movie_id_and_cinema_id(sibling.id, 2)
print([d.date for d in screening.dates])  # should include 2026-08-13
print(get_by_movie_id_and_cinema_id(base.id, 2))  # should be None - no wrong screening created
```

- [ ] **Step 4: Confirm the ambiguous case surfaces on `/admin/pipelines`**

Run a second import for a cinema neither `base` nor `sibling` has a screening at yet (e.g. `cine-cinco`, same title "Noite"), then start the dev server (`flask --app flask_backend run --debug`), log in as an admin, and open `/admin/pipelines/import-json`. Confirm the latest `cine-cinco` run shows the "warning" badge and its summary JSON includes an `"ambiguous_collisions"` entry naming the base movie.

- [ ] **Step 5: Report results to the user**

No commit for this task — summarize what was observed in Steps 3 and 4 back to the user (does not require further action unless something didn't match expectations).
