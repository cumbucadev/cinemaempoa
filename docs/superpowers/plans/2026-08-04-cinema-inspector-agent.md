# Cinema Inspector Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `flask inspect-movies`, a batch CLI pipeline that uses an LLM tool-calling agent to check whether a movie's linked TMDB entry actually matches what cinemas published about it, auto-fixes confidently-wrong matches, flags uncertain ones for manual review, and gives admins a dashboard to audit/revert what it did.

**Architecture:** A new `atomic-agents`-based orchestrator agent (`AtomicAgent[OrchestratorInput, OrchestratorDecision]`, powered by Gemini via Instructor) runs a bounded tool-calling loop per movie: it can search TMDB for candidates, fetch TMDB details, or re-fetch a screening's source page, then must conclude with a verdict (`consistent` / `fixed` / `needs_review`). The surrounding Python loop (not the framework) drives iteration, executes tools, and applies the verdict. Every inspection is persisted as an append-only audit row (`MovieInspection`), mirroring the existing `AlertAction`/`MovieMetadataFetchAttempt` patterns already in this codebase.

**Tech Stack:** Flask, SQLAlchemy, Alembic, Click, `atomic-agents`, `instructor[google-genai]`, existing `TMDBClient` (`flask_backend/service/tmdb.py`), existing `apply_tmdb_details`/`clear_tmdb_metadata` (`flask_backend/service/movie_metadata_pipeline.py`).

## Global Constraints

- v1 only detects/fixes wrong TMDB movie matches — it does not detect or split screenings whose description bundles multiple films (`mostra-ufrgs` case), and it does not touch showtimes, posters, or any screening field.
- The agent's only external web access is re-fetching a screening's own `url` — no general web search.
- The agent's only write tool is re-linking a movie to a different TMDB id (reusing `apply_tmdb_details`/`clear_tmdb_metadata`). It applies fixes automatically (no pre-approval gate), but every fix is recorded with a before/after snapshot so a human can revert it from `/admin/movies/inspections`.
- The agent may only reach verdict `fixed` after positively identifying the replacement id via its own TMDB search/details tools — it must return `needs_review` if uncertain, never guess.
- No test may call the real Gemini or TMDB APIs — mock at the client boundary, matching `test_service/test_gemini_api.py` and `test_service/test_tmdb.py`.
- Run `uv run ruff check --fix`, `uv run ruff format`, `uv run djlint flask_backend/templates --lint --profile=jinja`, and `uv run djlint --reformat flask_backend/templates --format-css --format-js` before considering any template/route task done.

---

## Task 1: `movie_inspections` data model and repository

**Files:**
- Create: `migrations/versions/20260804_000000_add_movie_inspections.py`
- Modify: `flask_backend/models.py`
- Modify: `flask_backend/tests/conftest.py`
- Create: `flask_backend/repository/movie_inspections.py`
- Test: `flask_backend/tests/test_repository/test_movie_inspections.py`

**Interfaces:**
- Produces (used by Tasks 2–7):
  - `flask_backend.models.MOVIE_INSPECTION_STATUSES: List[str]` = `["consistent", "fixed", "needs_review", "error", "reverted"]`
  - `flask_backend.models.MovieInspection` with columns `id`, `movie_id`, `status`, `reasoning`, `checked_tmdb_id`, `previous_snapshot`, `new_snapshot`, `pipeline_run_id`, `created_at`, and a `movie` relationship.
  - `repository.movie_inspections.create(movie_id: int, status: str, reasoning: str, checked_tmdb_id: Optional[int] = None, previous_snapshot: Optional[str] = None, new_snapshot: Optional[str] = None, pipeline_run_id: Optional[int] = None) -> MovieInspection`
  - `repository.movie_inspections.get_movies_needing_inspection() -> List[Movie]`
  - `repository.movie_inspections.get_by_id(inspection_id: int) -> Optional[MovieInspection]`
  - `repository.movie_inspections.get_paginated(status: Optional[str], current_page: int, per_page: int) -> Tuple[List[MovieInspection], int, int]`

- [ ] **Step 1: Write a failing test for `create`**

Create `flask_backend/tests/test_repository/test_movie_inspections.py`:

```python
from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspection
from flask_backend.repository import movie_inspections


def _create_movie(title="Filme de Teste", tmdb_id=None):
    movie = Movie(title=title, slug="filme-de-teste", tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


class TestCreate:
    def test_persists_all_fields(self, app):
        with app.app_context():
            movie = _create_movie()

            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Diretor e ano não coincidiam com o TMDB.",
                checked_tmdb_id=42,
                previous_snapshot='{"tmdb_id": 1}',
                new_snapshot='{"tmdb_id": 42}',
            )

            assert inspection.id is not None
            stored = db_session.query(MovieInspection).filter_by(id=inspection.id).one()
            assert stored.movie_id == movie.id
            assert stored.status == "fixed"
            assert stored.checked_tmdb_id == 42
            assert stored.previous_snapshot == '{"tmdb_id": 1}'
            assert stored.new_snapshot == '{"tmdb_id": 42}'
            assert stored.created_at is not None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest flask_backend/tests/test_repository/test_movie_inspections.py -v`
Expected: FAIL — `ImportError: cannot import name 'MovieInspection' from 'flask_backend.models'` (or similar).

- [ ] **Step 3: Add the migration**

Create `migrations/versions/20260804_000000_add_movie_inspections.py`:

```python
"""Adds movie_inspections: the append-only audit log for the movie
inspector agent (flask_backend/service/movie_inspector.py), which checks
whether a movie's TMDB match is consistent with what cinemas published
about it, and records what it found/fixed for /admin/movies/inspections.

Revision ID: 20260804_000000
Revises: 20260801_000000
Create Date: 2026-08-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260804_000000"
down_revision: Union[str, None] = "20260801_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movie_inspections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("checked_tmdb_id", sa.Integer(), nullable=True),
        sa.Column("previous_snapshot", sa.Text(), nullable=True),
        sa.Column("new_snapshot", sa.Text(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_movie_inspections_movie_id", "movie_inspections", ["movie_id"]
    )
    op.create_index(
        "ix_movie_inspections_pipeline_run_id",
        "movie_inspections",
        ["pipeline_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_movie_inspections_pipeline_run_id", table_name="movie_inspections"
    )
    op.drop_index("ix_movie_inspections_movie_id", table_name="movie_inspections")
    op.drop_table("movie_inspections")
```

- [ ] **Step 4: Add the model**

In `flask_backend/models.py`, add near the other status-list constants (after `ALERT_ACTIONS`):

```python
MOVIE_INSPECTION_STATUSES = ["consistent", "fixed", "needs_review", "error", "reverted"]
```

Then add the model near the bottom of the file (after `MovieMetadataFetchAttempt`, before `AlertAction`):

```python
class MovieInspection(Base):
    """One audit row per automated consistency check of a movie's TMDB
    match against what the cinema itself published about it (see
    flask_backend/service/movie_inspector.py). Append-only: reverting a
    "fixed" row creates a new row with status="reverted" instead of
    mutating history - same log-not-mutate shape as AlertAction."""

    __tablename__ = "movie_inspections"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    status = Column(String, nullable=False)  # see MOVIE_INSPECTION_STATUSES
    reasoning = Column(Text, nullable=False)
    checked_tmdb_id = Column(Integer, nullable=True)
    previous_snapshot = Column(Text, nullable=True)
    new_snapshot = Column(Text, nullable=True)
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    movie: Mapped["Movie"] = relationship()
```

- [ ] **Step 5: Add the repository module**

Create `flask_backend/repository/movie_inspections.py`:

```python
"""Data access for MovieInspection rows - the append-only audit log
behind the movie inspector agent and /admin/movies/inspections."""

from datetime import datetime
from math import ceil
from typing import List, Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspection


def create(
    movie_id: int,
    status: str,
    reasoning: str,
    checked_tmdb_id: Optional[int] = None,
    previous_snapshot: Optional[str] = None,
    new_snapshot: Optional[str] = None,
    pipeline_run_id: Optional[int] = None,
) -> MovieInspection:
    inspection = MovieInspection(
        movie_id=movie_id,
        status=status,
        reasoning=reasoning,
        checked_tmdb_id=checked_tmdb_id,
        previous_snapshot=previous_snapshot,
        new_snapshot=new_snapshot,
        pipeline_run_id=pipeline_run_id,
        created_at=datetime.now(),
    )
    db_session.add(inspection)
    db_session.commit()
    db_session.refresh(inspection)
    return inspection


def get_by_id(inspection_id: int) -> Optional[MovieInspection]:
    return (
        db_session.query(MovieInspection)
        .filter(MovieInspection.id == inspection_id)
        .first()
    )


def _get_latest_checked_tmdb_id(movie_id: int) -> Optional[int]:
    row = (
        db_session.query(MovieInspection.checked_tmdb_id)
        .filter(MovieInspection.movie_id == movie_id)
        .order_by(MovieInspection.id.desc())
        .first()
    )
    return row[0] if row else None


def get_movies_needing_inspection() -> List[Movie]:
    """Movies linked to TMDB whose match hasn't been inspected yet, or has
    changed since the last inspection (e.g. a prior fix, or a manual
    re-match via /admin/movies/<id>)."""
    candidates = db_session.query(Movie).filter(Movie.tmdb_id.isnot(None)).all()
    return [
        movie
        for movie in candidates
        if _get_latest_checked_tmdb_id(movie.id) != movie.tmdb_id
    ]


def get_paginated(
    status: Optional[str], current_page: int, per_page: int
) -> Tuple[List[MovieInspection], int, int]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(MovieInspection)
    if status is not None:
        query = query.filter(MovieInspection.status == status)

    inspections = (
        query.order_by(MovieInspection.created_at.desc(), MovieInspection.id.desc())
        .limit(per_page)
        .offset(offset_value)
        .all()
    )

    count_query = db_session.query(func.count(MovieInspection.id))
    if status is not None:
        count_query = count_query.filter(MovieInspection.status == status)
    total_count = count_query.scalar()
    total_pages = ceil(total_count / per_page) if total_count else 0

    return (inspections, total_pages, total_count)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest flask_backend/tests/test_repository/test_movie_inspections.py -v`
Expected: PASS

- [ ] **Step 7: Add tests for `get_movies_needing_inspection`**

Append to the same test file:

```python
class TestGetMoviesNeedingInspection:
    def test_ignores_movies_without_a_tmdb_match(self, app):
        with app.app_context():
            _create_movie(title="Sem TMDB", tmdb_id=None)

            assert movie_inspections.get_movies_needing_inspection() == []

    def test_includes_matched_movie_never_inspected(self, app):
        with app.app_context():
            movie = _create_movie(title="Nunca Inspecionado", tmdb_id=42)

            result = movie_inspections.get_movies_needing_inspection()

            assert [m.id for m in result] == [movie.id]

    def test_excludes_movie_already_checked_at_its_current_tmdb_id(self, app):
        with app.app_context():
            movie = _create_movie(title="Já Checado", tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="Ok.",
                checked_tmdb_id=42,
            )

            assert movie_inspections.get_movies_needing_inspection() == []

    def test_includes_movie_whose_match_changed_since_last_check(self, app):
        with app.app_context():
            movie = _create_movie(title="Rematched", tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="Ok na época.",
                checked_tmdb_id=1,
            )

            result = movie_inspections.get_movies_needing_inspection()

            assert [m.id for m in result] == [movie.id]
```

- [ ] **Step 8: Run tests, verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_movie_inspections.py -v`
Expected: PASS (5 tests)

- [ ] **Step 9: Add tests for `get_paginated` and `get_by_id`**

Append:

```python
class TestGetPaginated:
    def test_filters_by_status(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="b",
                checked_tmdb_id=42,
            )

            fixed, pages, total = movie_inspections.get_paginated("fixed", 1, 20)

            assert total == 1
            assert pages == 1
            assert [i.status for i in fixed] == ["fixed"]

    def test_no_filter_returns_everything_newest_first(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            first = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            second = movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="b",
                checked_tmdb_id=42,
            )

            rows, _, total = movie_inspections.get_paginated(None, 1, 20)

            assert total == 2
            assert [r.id for r in rows] == [second.id, first.id]

    def test_paginates(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            for i in range(3):
                movie_inspections.create(
                    movie_id=movie.id,
                    status="consistent",
                    reasoning=f"row {i}",
                    checked_tmdb_id=42,
                )

            page_one, pages, total = movie_inspections.get_paginated(None, 1, 2)
            page_two, _, _ = movie_inspections.get_paginated(None, 2, 2)

            assert total == 3
            assert pages == 2
            assert len(page_one) == 2
            assert len(page_two) == 1


class TestGetById:
    def test_returns_none_for_missing_id(self, app):
        with app.app_context():
            assert movie_inspections.get_by_id(99999) is None

    def test_returns_the_matching_row(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            created = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )

            assert movie_inspections.get_by_id(created.id).id == created.id
```

- [ ] **Step 10: Run tests, verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_movie_inspections.py -v`
Expected: PASS (10 tests)

- [ ] **Step 11: Wire `MovieInspection` into the test db cleanup**

In `flask_backend/tests/conftest.py`, add `MovieInspection` to the import list inside `clean_db` and delete it **before** `Movie` (foreign key ordering):

```python
        from flask_backend.models import (
            AlertAction,
            BlogPost,
            Cinema,
            Collection,
            Country,
            Director,
            Genre,
            Movie,
            MovieInspection,
            MovieMetadataFetchAttempt,
            PipelineRun,
            PosterFetchAttempt,
            Screening,
            ScreeningDate,
            User,
            WantToWatch,
            movie_countries,
            movie_directors,
            movie_genres,
        )

        db_session.query(AlertAction).delete()
        db_session.query(BlogPost).delete()
        db_session.query(User).delete()
        db_session.query(MovieInspection).delete()
        db_session.query(MovieMetadataFetchAttempt).delete()
```

- [ ] **Step 12: Run the full repository + database isolation test suite**

Run: `pytest flask_backend/tests/test_repository flask_backend/tests/test_database_isolation.py -v`
Expected: PASS, no leakage between tests.

- [ ] **Step 13: Commit**

```bash
git add migrations/versions/20260804_000000_add_movie_inspections.py \
        flask_backend/models.py \
        flask_backend/tests/conftest.py \
        flask_backend/repository/movie_inspections.py \
        flask_backend/tests/test_repository/test_movie_inspections.py
git commit -m "feat: add movie_inspections audit log table and repository"
```

---

## Task 2: TMDB/source tools and the write-side rematch helper

**Files:**
- Create: `flask_backend/service/movie_inspector.py` (tool functions + snapshot helper only in this task)
- Test: `flask_backend/tests/test_service/test_movie_inspector.py`

**Interfaces:**
- Consumes: `TMDBClient` (`flask_backend/service/tmdb.py`, existing), `get_screening_by_id` (`flask_backend/repository/screenings.py`, existing), `apply_tmdb_details`/`clear_tmdb_metadata` (`flask_backend/service/movie_metadata_pipeline.py`, existing), `Movie` model.
- Produces (used by Task 3):
  - `movie_inspector._snapshot(movie: Movie) -> dict`
  - `movie_inspector._apply_rematch(movie: Movie, tmdb_id: Optional[int]) -> None`
  - `movie_inspector._run_search_tmdb_candidates(title: str) -> str`
  - `movie_inspector._run_get_tmdb_details(tmdb_id: int) -> str`
  - `movie_inspector._run_fetch_screening_source(screening_id: int) -> str`

- [ ] **Step 1: Write failing tests for `_snapshot` and `_apply_rematch`**

Create `flask_backend/tests/test_service/test_movie_inspector.py`:

```python
from unittest.mock import MagicMock, patch

from flask_backend.db import db_session
from flask_backend.models import Director, Movie
from flask_backend.service import movie_inspector


def _create_movie(tmdb_id=None):
    movie = Movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


class TestSnapshot:
    def test_captures_key_fields(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie.original_title = "Original"
            movie.release_year = 1979
            director = Director(tmdb_id=1, name="Jean-Michel Tchissoukou")
            db_session.add(director)
            movie.directors.append(director)
            db_session.add(movie)
            db_session.commit()

            snapshot = movie_inspector._snapshot(movie)

            assert snapshot == {
                "tmdb_id": 42,
                "title": "Filme de Teste",
                "original_title": "Original",
                "release_year": 1979,
                "directors": ["Jean-Michel Tchissoukou"],
                "countries": [],
            }


class TestApplyRematch:
    def test_applies_new_tmdb_details(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            details = {
                "directors": [{"id": 2, "name": "Jane Director"}],
                "genres": [],
                "countries": [{"iso_3166_1": "BR", "name": "Brasil"}],
                "collection": None,
                "original_title": "New Original",
                "release_year": 1979,
                "original_language": "pt",
            }
            with patch.object(
                movie_inspector.TMDBClient,
                "get_movie_details",
                return_value=details,
            ):
                movie_inspector._apply_rematch(movie, 42)

            assert movie.tmdb_id == 42
            assert movie.original_title == "New Original"
            assert [d.name for d in movie.directors] == ["Jane Director"]

    def test_clears_metadata_when_tmdb_id_is_none(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            movie.original_title = "Something"
            db_session.add(movie)
            db_session.commit()

            movie_inspector._apply_rematch(movie, None)

            assert movie.tmdb_id is None
            assert movie.original_title is None
            assert movie.tmdb_excluded is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flask_backend.service.movie_inspector'`

- [ ] **Step 3: Implement `_snapshot` and `_apply_rematch`**

Create `flask_backend/service/movie_inspector.py`:

```python
"""The movie inspector agent: checks whether a movie's linked TMDB entry
is consistent with what cinemas actually published about it (director,
year, country), fixing confidently-wrong matches and flagging uncertain
ones for manual review. See docs/superpowers/specs/2026-08-04-cinema-inspector-agent-design.md.
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository.screenings import get_screening_by_id
from flask_backend.service.movie_metadata_pipeline import (
    apply_tmdb_details,
    clear_tmdb_metadata,
)
from flask_backend.service.tmdb import TMDBClient

logger = logging.getLogger(__name__)


def _snapshot(movie: Movie) -> dict:
    """Captures the movie's current TMDB-derived identity, for the
    before/after audit trail on MovieInspection rows."""
    return {
        "tmdb_id": movie.tmdb_id,
        "title": movie.title,
        "original_title": movie.original_title,
        "release_year": movie.release_year,
        "directors": [d.name for d in movie.directors],
        "countries": [c.name for c in movie.countries],
    }


def _apply_rematch(movie: Movie, tmdb_id: Optional[int]) -> None:
    """Re-links `movie` to `tmdb_id`, or clears its TMDB link entirely if
    `tmdb_id` is None (used when reverting a fix back to "unmatched").
    Commits."""
    if tmdb_id is None:
        clear_tmdb_metadata(movie)
        movie.tmdb_id = None
        movie.tmdb_excluded = False
    else:
        details = TMDBClient().get_movie_details(tmdb_id)
        apply_tmdb_details(movie, tmdb_id, details)
    db_session.add(movie)
    db_session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write failing tests for the read tools**

Append to the test file:

```python
import requests


class TestRunSearchTmdbCandidates:
    def test_formats_candidates(self, app):
        with app.app_context():
            results = [
                {"id": 573412, "title": "A Capela", "release_date": "1979-01-01"},
                {"id": 999, "title": "A Capela (remake)", "release_date": ""},
            ]
            with patch.object(
                movie_inspector.TMDBClient, "search_movies", return_value=results
            ):
                observation = movie_inspector._run_search_tmdb_candidates("A Capela")

            assert "tmdb_id=573412" in observation
            assert "ano=1979" in observation
            assert "tmdb_id=999" in observation

    def test_reports_no_results(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient, "search_movies", return_value=[]
            ):
                observation = movie_inspector._run_search_tmdb_candidates("Xyz")

            assert "Nenhum resultado" in observation

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient,
                "search_movies",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = movie_inspector._run_search_tmdb_candidates("Xyz")

            assert "Erro" in observation


class TestRunGetTmdbDetails:
    def test_formats_details(self, app):
        with app.app_context():
            details = {
                "directors": [{"id": 1, "name": "Jean-Michel Tchissoukou"}],
                "countries": [{"iso_3166_1": "CG", "name": "Congo"}],
                "genres": [],
                "collection": None,
                "original_title": "A Capela",
                "release_year": 1979,
                "original_language": "fr",
            }
            with patch.object(
                movie_inspector.TMDBClient, "get_movie_details", return_value=details
            ):
                observation = movie_inspector._run_get_tmdb_details(573412)

            assert "Jean-Michel Tchissoukou" in observation
            assert "1979" in observation
            assert "Congo" in observation

    def test_reports_request_errors(self, app):
        with app.app_context():
            with patch.object(
                movie_inspector.TMDBClient,
                "get_movie_details",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = movie_inspector._run_get_tmdb_details(1)

            assert "Erro" in observation


class TestRunFetchScreeningSource:
    def test_reports_missing_screening(self, app):
        with app.app_context():
            observation = movie_inspector._run_fetch_screening_source(99999)

            assert "não encontrada" in observation

    def test_reports_missing_url(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                url=None,
            )
            db_session.add(screening)
            db_session.commit()

            observation = movie_inspector._run_fetch_screening_source(screening.id)

            assert "não tem URL" in observation

    def test_fetches_and_extracts_text(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                url="https://example.com/evento",
            )
            db_session.add(screening)
            db_session.commit()

            response = MagicMock()
            response.text = "<html><body><p>Jean-Michel Tchissoukou, 1979</p></body></html>"
            response.raise_for_status = MagicMock()
            with patch(
                "flask_backend.service.movie_inspector.requests.get",
                return_value=response,
            ):
                observation = movie_inspector._run_fetch_screening_source(
                    screening.id
                )

            assert "Jean-Michel Tchissoukou, 1979" in observation

    def test_reports_request_errors(self, app):
        from flask_backend.models import Cinema, Screening

        with app.app_context():
            cinema = Cinema(
                slug="cine-teste", name="Cine Teste", url="https://example.com"
            )
            db_session.add(cinema)
            db_session.commit()
            movie = _create_movie()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                url="https://example.com/evento",
            )
            db_session.add(screening)
            db_session.commit()

            with patch(
                "flask_backend.service.movie_inspector.requests.get",
                side_effect=requests.RequestException("timeout"),
            ):
                observation = movie_inspector._run_fetch_screening_source(
                    screening.id
                )

            assert "Erro" in observation
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: FAIL — `AttributeError: module 'flask_backend.service.movie_inspector' has no attribute '_run_search_tmdb_candidates'`

- [ ] **Step 7: Implement the read tools**

Add to `flask_backend/service/movie_inspector.py` (add `import requests` to the top-of-file imports alongside `from bs4 import BeautifulSoup`):

```python
def _run_search_tmdb_candidates(title: str) -> str:
    try:
        results = TMDBClient().search_movies(title)
    except requests.RequestException as exc:
        return f"Erro ao buscar '{title}' no TMDB: {exc}"
    if not results:
        return f"Nenhum resultado no TMDB para '{title}'."
    lines = [
        "- tmdb_id={} título='{}' ano={}".format(
            r["id"], r.get("title"), (r.get("release_date") or "????")[:4]
        )
        for r in results
    ]
    return "Candidatos no TMDB para '{}':\n{}".format(title, "\n".join(lines))


def _run_get_tmdb_details(tmdb_id: int) -> str:
    try:
        details = TMDBClient().get_movie_details(tmdb_id)
    except requests.RequestException as exc:
        return f"Erro ao buscar detalhes do TMDB id={tmdb_id}: {exc}"
    directors = ", ".join(d["name"] for d in details["directors"]) or "desconhecido"
    countries = ", ".join(c["name"] for c in details["countries"]) or "desconhecido"
    return (
        f"Detalhes do TMDB id={tmdb_id}: título original="
        f"'{details['original_title']}', ano={details['release_year']}, "
        f"diretor(es)={directors}, país(es)={countries}"
    )


def _run_fetch_screening_source(screening_id: int) -> str:
    screening = get_screening_by_id(screening_id)
    if screening is None:
        return f"Sessão #{screening_id} não encontrada."
    if not screening.url:
        return f"Sessão #{screening_id} não tem URL de origem cadastrada."
    try:
        response = requests.get(screening.url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        return f"Erro ao buscar {screening.url}: {exc}"
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    return f"Conteúdo de {screening.url}:\n{text[:4000]}"
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: PASS (12 tests)

- [ ] **Step 9: Commit**

```bash
git add flask_backend/service/movie_inspector.py flask_backend/tests/test_service/test_movie_inspector.py
git commit -m "feat: add movie inspector's TMDB/source tools and rematch helper"
```

---

## Task 3: Orchestrator schemas and the `inspect_movie` tool-calling loop

**Files:**
- Modify: `flask_backend/service/movie_inspector.py`
- Modify: `pyproject.toml` (via `uv add`)
- Test: `flask_backend/tests/test_service/test_movie_inspector.py`

**Interfaces:**
- Consumes: `movie_inspector._run_search_tmdb_candidates`, `_run_get_tmdb_details`, `_run_fetch_screening_source`, `_apply_rematch`, `_snapshot` (Task 2); `Gemini.MODEL` (`flask_backend/service/gemini_api.py`, existing); `GEMINI_API_KEY` (`flask_backend/env_config.py`, existing).
- Produces (used by Task 4 and Task 7):
  - `movie_inspector.MAX_TOOL_CALLS: int = 4`
  - `movie_inspector.ScreeningContext`, `OrchestratorInput`, `InspectionVerdict`, `OrchestratorDecision` (Pydantic/`BaseIOSchema` classes)
  - `movie_inspector.InspectionOutcome` dataclass: `status: str`, `reasoning: str`, `before_snapshot: Optional[dict] = None`, `after_snapshot: Optional[dict] = None`
  - `movie_inspector.inspect_movie(movie: Movie) -> InspectionOutcome`
  - `movie_inspector._build_agent() -> AtomicAgent[OrchestratorInput, OrchestratorDecision]` (patched in tests)

- [ ] **Step 1: Add the dependencies**

```bash
uv add atomic-agents
uv add "instructor[google-genai]"
```

- [ ] **Step 2: Write failing tests for `inspect_movie`**

Append to `flask_backend/tests/test_service/test_movie_inspector.py`:

```python
class TestInspectMovie:
    def _decision(self, **kwargs):
        defaults = {
            "action": "conclude",
            "search_title": None,
            "tmdb_id": None,
            "screening_id": None,
            "verdict": None,
        }
        defaults.update(kwargs)
        return movie_inspector.OrchestratorDecision(**defaults)

    def _verdict(self, **kwargs):
        defaults = {"status": "consistent", "reasoning": "Bate tudo.", "new_tmdb_id": None}
        defaults.update(kwargs)
        return movie_inspector.InspectionVerdict(**defaults)

    def test_consistent_verdict_leaves_movie_untouched(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie.original_title = "Original"
            db_session.add(movie)
            db_session.commit()

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(status="consistent", reasoning="Tudo ok.")
            )
            with patch.object(
                movie_inspector, "_build_agent", return_value=fake_agent
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "consistent"
            assert outcome.reasoning == "Tudo ok."
            assert movie.original_title == "Original"

    def test_fixed_verdict_applies_rematch_and_captures_snapshots(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            details = {
                "directors": [{"id": 1, "name": "Jean-Michel Tchissoukou"}],
                "genres": [],
                "countries": [],
                "collection": None,
                "original_title": "A Capela",
                "release_year": 1979,
                "original_language": "fr",
            }

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(
                    status="fixed",
                    reasoning="Diretor e ano batem com o TMDB id 573412.",
                    new_tmdb_id=573412,
                )
            )
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                patch.object(
                    movie_inspector.TMDBClient,
                    "get_movie_details",
                    return_value=details,
                ),
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "fixed"
            assert movie.tmdb_id == 573412
            assert outcome.before_snapshot["tmdb_id"] == 1
            assert outcome.after_snapshot["tmdb_id"] == 573412

    def test_fixed_verdict_without_new_tmdb_id_becomes_needs_review(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                verdict=self._verdict(status="fixed", reasoning="Sem id.", new_tmdb_id=None)
            )
            with patch.object(
                movie_inspector, "_build_agent", return_value=fake_agent
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert movie.tmdb_id == 1

    def test_dispatches_search_tool_then_concludes(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.side_effect = [
                self._decision(action="search_tmdb_candidates", search_title="A Capela"),
                self._decision(verdict=self._verdict(status="needs_review", reasoning="Incerto.")),
            ]
            with (
                patch.object(movie_inspector, "_build_agent", return_value=fake_agent),
                patch.object(
                    movie_inspector.TMDBClient,
                    "search_movies",
                    return_value=[{"id": 573412, "title": "A Capela", "release_date": "1979"}],
                ),
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert fake_agent.run.call_count == 2
            second_call_input = fake_agent.run.call_args_list[1].args[0]
            assert any(
                "573412" in observation for observation in second_call_input.observations
            )

    def test_stops_after_max_tool_calls_with_needs_review(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            fake_agent = MagicMock()
            fake_agent.run.return_value = self._decision(
                action="fetch_screening_source", screening_id=1
            )
            with patch.object(
                movie_inspector, "_build_agent", return_value=fake_agent
            ):
                outcome = movie_inspector.inspect_movie(movie)

            assert outcome.status == "needs_review"
            assert fake_agent.run.call_count == movie_inspector.MAX_TOOL_CALLS
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: FAIL — `AttributeError: module 'flask_backend.service.movie_inspector' has no attribute 'OrchestratorDecision'`

- [ ] **Step 4: Implement the schemas, agent builder, and loop**

Add to `flask_backend/service/movie_inspector.py`. First, extend the imports at the top of the file:

```python
from dataclasses import dataclass
from typing import List, Literal, Optional

import instructor
from atomic_agents import AgentConfig, AtomicAgent, BaseIOSchema
from atomic_agents.context import ChatHistory, SystemPromptGenerator
from pydantic import Field

from flask_backend.env_config import GEMINI_API_KEY
from flask_backend.service.gemini_api import Gemini
```

Then add the schemas and loop (after the tool functions from Task 2):

```python
MAX_TOOL_CALLS = 4


class ScreeningContext(BaseIOSchema):
    """One screening's cinema name and scraped description text, given to
    the inspector as evidence about the film actually being shown."""

    cinema_name: str = Field(..., description="Name of the cinema showing this screening.")
    description: str = Field(..., description="The scraped, free-text description of the screening.")


class OrchestratorInput(BaseIOSchema):
    """Everything the movie inspector knows so far about one movie: its
    current TMDB match, what the cinemas showing it actually published,
    and any tool results gathered in earlier steps of this inspection."""

    movie_title: str = Field(..., description="The movie's title in our database.")
    tmdb_original_title: Optional[str] = Field(None, description="Original title from the current TMDB match.")
    tmdb_release_year: Optional[int] = Field(None, description="Release year from the current TMDB match.")
    tmdb_original_language: Optional[str] = Field(None, description="ISO 639-1 original language from the current TMDB match.")
    tmdb_directors: List[str] = Field(default_factory=list, description="Director names from the current TMDB match.")
    tmdb_countries: List[str] = Field(default_factory=list, description="Production countries from the current TMDB match.")
    tmdb_genres: List[str] = Field(default_factory=list, description="Genres from the current TMDB match.")
    screenings: List[ScreeningContext] = Field(default_factory=list, description="Cinema-published descriptions for this movie.")
    observations: List[str] = Field(
        default_factory=list,
        description="Results of tools called in earlier steps of this same inspection, oldest first.",
    )


class InspectionVerdict(BaseIOSchema):
    """The inspector's final answer once it is done gathering evidence."""

    status: Literal["consistent", "fixed", "needs_review"] = Field(
        ..., description="'consistent' if the TMDB match agrees with the cinema descriptions, 'fixed' if a better match was positively identified, 'needs_review' if uncertain."
    )
    reasoning: str = Field(..., description="Explanation citing the specific evidence found.")
    new_tmdb_id: Optional[int] = Field(
        None, description="Required when status is 'fixed': the TMDB id positively identified via the search/details tools."
    )


class OrchestratorDecision(BaseIOSchema):
    """The inspector's next move: either call exactly one tool, or
    conclude the inspection with a final verdict."""

    action: Literal[
        "search_tmdb_candidates", "get_tmdb_details", "fetch_screening_source", "conclude"
    ] = Field(..., description="Which tool to call next, or 'conclude' to finish.")
    search_title: Optional[str] = Field(None, description="Title to search for. Required when action is 'search_tmdb_candidates'.")
    tmdb_id: Optional[int] = Field(None, description="TMDB id to fetch details for. Required when action is 'get_tmdb_details'.")
    screening_id: Optional[int] = Field(None, description="Screening id to re-fetch. Required when action is 'fetch_screening_source'.")
    verdict: Optional[InspectionVerdict] = Field(None, description="Final verdict. Required when action is 'conclude'.")


@dataclass
class InspectionOutcome:
    status: str
    reasoning: str
    before_snapshot: Optional[dict] = None
    after_snapshot: Optional[dict] = None


def _build_agent() -> AtomicAgent[OrchestratorInput, OrchestratorDecision]:
    client = instructor.from_provider(f"google/{Gemini.MODEL}", api_key=GEMINI_API_KEY)
    system_prompt_generator = SystemPromptGenerator(
        background=[
            "Você é um inspetor de dados de um portal de cinema.",
            "Sua tarefa é verificar se o filme vinculado no TMDB corresponde ao "
            "filme descrito pelos cinemas que o exibem - filmes com o mesmo "
            "título em português são frequentemente vinculados errado.",
        ],
        steps=[
            "Compare diretor, ano, país e gênero do TMDB com o texto das sessões.",
            "Se algo não bate, use as ferramentas disponíveis para investigar antes de concluir.",
            "Só conclua 'fixed' depois de identificar um tmdb_id correto usando "
            "search_tmdb_candidates/get_tmdb_details - nunca invente um id.",
            "Se não tiver certeza, conclua 'needs_review' em vez de arriscar um palpite.",
        ],
        output_instructions=[
            "Responda apenas com a próxima ação: um dos tools disponíveis, ou "
            "'conclude' acompanhado do veredito final.",
        ],
    )
    return AtomicAgent[OrchestratorInput, OrchestratorDecision](
        config=AgentConfig(
            client=client,
            model=Gemini.MODEL,
            system_prompt_generator=system_prompt_generator,
            history=ChatHistory(),
        )
    )


def _dispatch_tool(decision: OrchestratorDecision) -> str:
    if decision.action == "search_tmdb_candidates":
        if not decision.search_title:
            return "Ação 'search_tmdb_candidates' sem 'search_title'."
        return _run_search_tmdb_candidates(decision.search_title)
    if decision.action == "get_tmdb_details":
        if decision.tmdb_id is None:
            return "Ação 'get_tmdb_details' sem 'tmdb_id'."
        return _run_get_tmdb_details(decision.tmdb_id)
    if decision.action == "fetch_screening_source":
        if decision.screening_id is None:
            return "Ação 'fetch_screening_source' sem 'screening_id'."
        return _run_fetch_screening_source(decision.screening_id)
    return f"Ação desconhecida: {decision.action}"


def _apply_verdict(movie: Movie, verdict: InspectionVerdict) -> InspectionOutcome:
    if verdict.status == "fixed":
        if verdict.new_tmdb_id is None:
            return InspectionOutcome(
                status="needs_review",
                reasoning=(
                    "Veredito 'fixed' sem new_tmdb_id; tratado como revisão "
                    f"manual. Raciocínio original: {verdict.reasoning}"
                ),
            )
        before = _snapshot(movie)
        _apply_rematch(movie, verdict.new_tmdb_id)
        after = _snapshot(movie)
        return InspectionOutcome(
            status="fixed",
            reasoning=verdict.reasoning,
            before_snapshot=before,
            after_snapshot=after,
        )
    return InspectionOutcome(status=verdict.status, reasoning=verdict.reasoning)


def inspect_movie(movie: Movie) -> InspectionOutcome:
    """Runs the orchestrator's bounded tool-calling loop for one movie and
    returns the resulting outcome. If `verdict.status == "fixed"`, the
    movie's TMDB link has already been updated and committed."""
    agent_input = OrchestratorInput(
        movie_title=movie.title,
        tmdb_original_title=movie.original_title,
        tmdb_release_year=movie.release_year,
        tmdb_original_language=movie.original_language,
        tmdb_directors=[d.name for d in movie.directors],
        tmdb_countries=[c.name for c in movie.countries],
        tmdb_genres=[g.name for g in movie.genres],
        screenings=[
            ScreeningContext(cinema_name=s.cinema.name, description=s.description)
            for s in movie.screenings
        ],
    )
    agent = _build_agent()

    for _ in range(MAX_TOOL_CALLS):
        decision = agent.run(agent_input)

        if decision.action == "conclude":
            if decision.verdict is None:
                agent_input.observations.append(
                    "Ação 'conclude' enviada sem veredito; forneça o veredito."
                )
                continue
            return _apply_verdict(movie, decision.verdict)

        agent_input.observations.append(_dispatch_tool(decision))

    logger.info(
        "Filme %d ('%s') – inspeção inconclusiva após %d chamadas de ferramenta",
        movie.id,
        movie.title,
        MAX_TOOL_CALLS,
    )
    return InspectionOutcome(
        status="needs_review",
        reasoning=f"Inspeção inconclusiva após {MAX_TOOL_CALLS} chamadas de ferramenta.",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: PASS (17 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock flask_backend/service/movie_inspector.py flask_backend/tests/test_service/test_movie_inspector.py
git commit -m "feat: add movie inspector orchestrator loop (atomic-agents + Gemini)"
```

---

## Task 4: Batch pipeline (`run_pipeline`) and revert support

**Files:**
- Modify: `flask_backend/service/movie_inspector.py`
- Test: `flask_backend/tests/test_service/test_movie_inspector.py`

**Interfaces:**
- Consumes: `repository.movie_inspections.{create, get_movies_needing_inspection, get_by_id}` (Task 1); `inspect_movie`, `_apply_rematch`, `_snapshot` (Task 3/2).
- Produces (used by Task 5 and Task 7):
  - `movie_inspector.PipelineResult` dataclass: `processed: int = 0`, `consistent: int = 0`, `fixed: int = 0`, `needs_review: int = 0`, `errors: int = 0`
  - `movie_inspector.run_pipeline(limit: Optional[int] = None, pipeline_run_id: Optional[int] = None) -> PipelineResult`
  - `movie_inspector.revert_inspection(inspection_id: int) -> MovieInspection`

- [ ] **Step 1: Write failing tests for `run_pipeline`**

Append to `flask_backend/tests/test_service/test_movie_inspector.py`:

```python
from flask_backend.repository import movie_inspections


class TestRunPipeline:
    def test_records_one_row_per_movie_and_tallies_result(self, app):
        with app.app_context():
            movie_a = _create_movie(tmdb_id=1)
            movie_a.slug = "movie-a"
            movie_b = Movie(title="Filme B", slug="filme-b", tmdb_id=2)
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            outcomes = {
                movie_a.id: movie_inspector.InspectionOutcome(
                    status="consistent", reasoning="ok"
                ),
                movie_b.id: movie_inspector.InspectionOutcome(
                    status="needs_review", reasoning="incerto"
                ),
            }
            with patch.object(
                movie_inspector,
                "inspect_movie",
                side_effect=lambda movie: outcomes[movie.id],
            ):
                result = movie_inspector.run_pipeline()

            assert result.processed == 2
            assert result.consistent == 1
            assert result.needs_review == 1

            rows, _, total = movie_inspections.get_paginated(None, 1, 20)
            assert total == 2

    def test_respects_limit(self, app):
        with app.app_context():
            for i in range(3):
                movie = Movie(title=f"Filme {i}", slug=f"filme-{i}", tmdb_id=i + 1)
                db_session.add(movie)
            db_session.commit()

            with patch.object(
                movie_inspector,
                "inspect_movie",
                return_value=movie_inspector.InspectionOutcome(
                    status="consistent", reasoning="ok"
                ),
            ):
                result = movie_inspector.run_pipeline(limit=2)

            assert result.processed == 2

    def test_records_error_status_and_continues_on_exception(self, app):
        with app.app_context():
            movie_a = _create_movie(tmdb_id=1)
            movie_b = Movie(title="Filme B", slug="filme-b", tmdb_id=2)
            db_session.add(movie_b)
            db_session.commit()

            def fake_inspect(movie):
                if movie.id == movie_a.id:
                    raise RuntimeError("gemini indisponível")
                return movie_inspector.InspectionOutcome(status="consistent", reasoning="ok")

            with patch.object(movie_inspector, "inspect_movie", side_effect=fake_inspect):
                result = movie_inspector.run_pipeline()

            assert result.errors == 1
            assert result.consistent == 1
            assert result.processed == 2

            rows, _, _ = movie_inspections.get_paginated("error", 1, 20)
            assert len(rows) == 1
            assert "gemini indisponível" in rows[0].reasoning

    def test_tags_rows_with_pipeline_run_id(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)

            with patch.object(
                movie_inspector,
                "inspect_movie",
                return_value=movie_inspector.InspectionOutcome(
                    status="consistent", reasoning="ok"
                ),
            ):
                movie_inspector.run_pipeline(pipeline_run_id=99)

            rows, _, _ = movie_inspections.get_paginated(None, 1, 20)
            assert rows[0].pipeline_run_id == 99
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: FAIL — `AttributeError: module 'flask_backend.service.movie_inspector' has no attribute 'run_pipeline'`

- [ ] **Step 3: Implement `run_pipeline`**

Add to `flask_backend/service/movie_inspector.py` (add `from flask_backend.repository import movie_inspections` and `from flask_backend.repository.movies import get_by_id as get_movie_by_id` to the imports, plus `import json`):

```python
@dataclass
class PipelineResult:
    processed: int = 0
    consistent: int = 0
    fixed: int = 0
    needs_review: int = 0
    errors: int = 0


def run_pipeline(
    limit: Optional[int] = None, pipeline_run_id: Optional[int] = None
) -> PipelineResult:
    result = PipelineResult()
    movies = movie_inspections.get_movies_needing_inspection()
    if limit is not None:
        movies = movies[:limit]

    for movie in movies:
        try:
            outcome = inspect_movie(movie)
        except Exception as exc:
            logger.warning(
                "Filme %d ('%s') – erro na inspeção: %s", movie.id, movie.title, exc
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="error",
                reasoning=str(exc)[:500],
                checked_tmdb_id=movie.tmdb_id,
                pipeline_run_id=pipeline_run_id,
            )
            result.errors += 1
            result.processed += 1
            continue

        movie_inspections.create(
            movie_id=movie.id,
            status=outcome.status,
            reasoning=outcome.reasoning,
            checked_tmdb_id=movie.tmdb_id,
            previous_snapshot=json.dumps(outcome.before_snapshot)
            if outcome.before_snapshot
            else None,
            new_snapshot=json.dumps(outcome.after_snapshot)
            if outcome.after_snapshot
            else None,
            pipeline_run_id=pipeline_run_id,
        )
        if outcome.status == "consistent":
            result.consistent += 1
        elif outcome.status == "fixed":
            result.fixed += 1
        elif outcome.status == "needs_review":
            result.needs_review += 1
        result.processed += 1

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Write failing tests for `revert_inspection`**

Append to the test file:

```python
class TestRevertInspection:
    def test_reverts_to_the_previous_tmdb_id(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=573412)
            movie.original_title = "A Capela"
            db_session.add(movie)
            db_session.commit()
            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Rematched.",
                checked_tmdb_id=573412,
                previous_snapshot=json.dumps({"tmdb_id": 1, "title": "Filme de Teste"}),
                new_snapshot=json.dumps({"tmdb_id": 573412, "title": "A Capela"}),
            )

            details = {
                "directors": [],
                "genres": [],
                "countries": [],
                "collection": None,
                "original_title": None,
                "release_year": None,
                "original_language": None,
            }
            with patch.object(
                movie_inspector.TMDBClient, "get_movie_details", return_value=details
            ):
                reverted = movie_inspector.revert_inspection(inspection.id)

            assert movie.tmdb_id == 1
            assert reverted.status == "reverted"
            assert reverted.movie_id == movie.id

    def test_reverting_to_previously_unmatched_clears_tmdb_id(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=573412)
            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="fixed",
                reasoning="Rematched.",
                checked_tmdb_id=573412,
                previous_snapshot=json.dumps({"tmdb_id": None}),
                new_snapshot=json.dumps({"tmdb_id": 573412}),
            )

            movie_inspector.revert_inspection(inspection.id)

            assert movie.tmdb_id is None

    def test_raises_for_non_fixed_inspection(self, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=1)
            inspection = movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="ok",
                checked_tmdb_id=1,
            )

            with pytest.raises(ValueError):
                movie_inspector.revert_inspection(inspection.id)
```

Add `import json` and `import pytest` to the top of the test file if not already present.

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: FAIL — `AttributeError: module 'flask_backend.service.movie_inspector' has no attribute 'revert_inspection'`

- [ ] **Step 7: Implement `revert_inspection`**

Add to `flask_backend/service/movie_inspector.py`:

```python
def revert_inspection(inspection_id: int):
    inspection = movie_inspections.get_by_id(inspection_id)
    if inspection is None or inspection.status != "fixed":
        raise ValueError(f"Inspeção #{inspection_id} não pode ser revertida.")

    previous = json.loads(inspection.previous_snapshot)
    movie = get_movie_by_id(inspection.movie_id)
    before = _snapshot(movie)
    _apply_rematch(movie, previous.get("tmdb_id"))
    after = _snapshot(movie)

    return movie_inspections.create(
        movie_id=movie.id,
        status="reverted",
        reasoning=f"Revertido manualmente para o estado anterior à inspeção #{inspection_id}.",
        checked_tmdb_id=movie.tmdb_id,
        previous_snapshot=json.dumps(before),
        new_snapshot=json.dumps(after),
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: PASS (24 tests)

- [ ] **Step 9: Commit**

```bash
git add flask_backend/service/movie_inspector.py flask_backend/tests/test_service/test_movie_inspector.py
git commit -m "feat: add movie inspector batch pipeline and revert support"
```

---

## Task 5: `inspect-movies` CLI command

**Files:**
- Modify: `flask_backend/commands.py`
- Test: `flask_backend/tests/test_service/test_commands.py`

**Interfaces:**
- Consumes: `movie_inspector.run_pipeline`, `movie_inspector.PipelineResult` (Task 4); `pipeline_runs.start`/`finish` (`flask_backend/repository/pipeline_runs.py`, existing).
- Produces: `inspect-movies` Click command registered on the Flask CLI (`flask --app flask_backend inspect-movies [--limit N]`).

- [ ] **Step 1: Write failing tests for the command**

Append to `flask_backend/tests/test_service/test_commands.py` (add `from flask_backend.service.movie_inspector import PipelineResult as InspectionPipelineResult` to the imports at the top):

```python
class TestInspectMoviesCommand:
    def test_prints_summary(self, runner):
        result_obj = InspectionPipelineResult(
            processed=3, consistent=1, fixed=1, needs_review=1
        )
        with patch(
            "flask_backend.service.movie_inspector.run_pipeline",
            return_value=result_obj,
        ):
            result = runner.invoke(args=["inspect-movies"])
        assert "Processados:          3" in result.output

    def test_creates_pipeline_run_with_success_status(self, app, runner):
        result_obj = InspectionPipelineResult(processed=2, consistent=2, errors=0)
        with patch(
            "flask_backend.service.movie_inspector.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["inspect-movies"])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="inspect-movies")
                .one()
            )
            assert run.status == "success"
            assert '"processed": 2' in run.summary

    def test_creates_pipeline_run_with_warning_status_on_errors(self, app, runner):
        result_obj = InspectionPipelineResult(processed=2, consistent=1, errors=1)
        with patch(
            "flask_backend.service.movie_inspector.run_pipeline",
            return_value=result_obj,
        ):
            runner.invoke(args=["inspect-movies"])

        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="inspect-movies")
                .one()
            )
            assert run.status == "warning"

    def test_creates_pipeline_run_with_error_status_on_exception(self, app, runner):
        with patch(
            "flask_backend.service.movie_inspector.run_pipeline",
            side_effect=RuntimeError("gemini indisponível"),
        ):
            result = runner.invoke(args=["inspect-movies"])

        assert result.exception is not None
        with app.app_context():
            run = (
                db_session.query(PipelineRun)
                .filter_by(pipeline_name="inspect-movies")
                .one()
            )
            assert run.status == "error"
            assert "gemini indisponível" in run.error_message

    def test_passes_limit_option_through(self, runner):
        with patch(
            "flask_backend.service.movie_inspector.run_pipeline",
            return_value=InspectionPipelineResult(),
        ) as mock_run:
            runner.invoke(args=["inspect-movies", "--limit", "5"])

        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["limit"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k InspectMovies -v`
Expected: FAIL — `AssertionError` / Click "No such command 'inspect-movies'."

- [ ] **Step 3: Implement the command**

In `flask_backend/commands.py`, add after `movie_metadata_review` (and its blank lines):

```python
@click.command("inspect-movies")
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Número máximo de filmes a inspecionar. Sem limite por padrão.",
)
def inspect_movies(limit):
    """Verifica se o filme vinculado no TMDB é consistente com o que os
    cinemas publicaram sobre ele, corrigindo vínculos incorretos quando
    identifica um substituto com confiança e sinalizando os demais para
    revisão manual em /admin/movies/inspections.
    """
    from flask_backend.repository import pipeline_runs
    from flask_backend.service.movie_inspector import run_pipeline

    run = pipeline_runs.start("inspect-movies")
    try:
        result = run_pipeline(limit=limit, pipeline_run_id=run.id)
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
                "consistent": result.consistent,
                "fixed": result.fixed,
                "needs_review": result.needs_review,
                "errors": result.errors,
            }
        ),
    )

    click.echo(f"\n{'=' * 40}")
    click.echo("Resultado da inspeção de filmes:")
    click.echo(f"  Processados:          {result.processed}")
    click.echo(f"  Consistentes:         {result.consistent}")
    click.echo(f"  Corrigidos:           {result.fixed}")
    click.echo(f"  Aguardando revisão:   {result.needs_review}")
    click.echo(f"  Erros:                {result.errors}")
    click.echo(f"{'=' * 40}")

    if result.needs_review > 0:
        click.echo(
            f"\n⚠ {result.needs_review} filme(s) aguardam revisão manual em "
            "/admin/movies/inspections."
        )
```

Then register it in `register_commands`:

```python
    app.cli.add_command(fetch_movie_metadata)
    app.cli.add_command(movie_metadata_review)
    app.cli.add_command(inspect_movies)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_commands.py -k InspectMovies -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full command test file**

Run: `pytest flask_backend/tests/test_service/test_commands.py -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add flask_backend/commands.py flask_backend/tests/test_service/test_commands.py
git commit -m "feat: add inspect-movies CLI command"
```

---

## Task 6: `/admin/movies/inspections` dashboard

**Files:**
- Create: `flask_backend/routes/admin/inspections.py`
- Create: `flask_backend/templates/inspections/admin/index.html`
- Modify: `flask_backend/__init__.py`
- Modify: `flask_backend/templates/base.html`
- Test: `flask_backend/tests/test_routes/test_admin/test_admin_inspections.py`

**Interfaces:**
- Consumes: `repository.movie_inspections.get_paginated` (Task 1); `MOVIE_INSPECTION_STATUSES` (Task 1).
- Produces: `GET /admin/movies/inspections` (blueprint name `admin_inspections`, view name `index`), used by Task 7 for the revert button's redirect target.

- [ ] **Step 1: Write failing tests for the listing page**

Create `flask_backend/tests/test_routes/test_admin/test_admin_inspections.py`:

```python
"""Tests the basic functionality of /admin/movies/inspections."""

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository import movie_inspections


def _create_movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=None):
    movie = Movie(title=title, slug=slug, tmdb_id=tmdb_id)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


class TestAdminInspectionsIndex:
    def test_requires_login(self, client):
        response = client.get("/admin/movies/inspections")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200_with_no_rows(self, auth_headers):
        response = auth_headers.get("/admin/movies/inspections")
        assert response.status_code == 200

    def test_lists_an_inspection_row(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="Diretor não coincide com o TMDB.",
                checked_tmdb_id=42,
            )

        response = auth_headers.get("/admin/movies/inspections")
        assert response.status_code == 200
        assert b"Filme de Teste" in response.data
        assert "Diretor não coincide com o TMDB.".encode() in response.data

    def test_filters_by_status(self, app, auth_headers):
        # Deliberately avoids status="fixed" here: that renders a Revert
        # button pointing at admin_inspections.revert, which isn't added
        # until Task 7. Fixed-row rendering is covered there instead.
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            movie_inspections.create(
                movie_id=movie.id,
                status="consistent",
                reasoning="tudo ok",
                checked_tmdb_id=42,
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="needs_review",
                reasoning="b não deveria aparecer com filtro consistent",
                checked_tmdb_id=42,
            )

        response = auth_headers.get("/admin/movies/inspections?status=consistent")
        assert response.status_code == 200
        assert "não deveria aparecer".encode() not in response.data

    def test_invalid_status_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/movies/inspections?status=bogus")
        assert response.status_code == 400

    def test_invalid_pagination_returns_400(self, auth_headers):
        response = auth_headers.get(
            "/admin/movies/inspections?page=invalid&limit=10"
        )
        assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_inspections.py -v`
Expected: FAIL — 404s (`admin_inspections` blueprint doesn't exist yet).

- [ ] **Step 3: Implement the route**

Create `flask_backend/routes/admin/inspections.py`:

```python
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from flask_backend.models import MOVIE_INSPECTION_STATUSES
from flask_backend.repository import movie_inspections
from flask_backend.routes.auth import login_required

bp = Blueprint("admin_inspections", __name__)

STATUS_FILTERS = (*MOVIE_INSPECTION_STATUSES, "all")


@bp.route("/admin/movies/inspections")
@login_required
def index():
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        abort(400)

    if page < 1 or limit < 1:
        abort(400)

    status = request.args.get("status", "all")
    if status not in STATUS_FILTERS:
        abort(400)

    inspections, pages, total = movie_inspections.get_paginated(
        None if status == "all" else status, page, limit
    )
    prev_page = page - 1 if page > 1 else None

    return render_template(
        "inspections/admin/index.html",
        status=status,
        inspections=inspections,
        curr_page=page,
        prev_page=prev_page,
        next_page=page + 1 if page < pages else None,
        pages=pages,
        limit=limit,
        total=total,
    )
```

- [ ] **Step 4: Add the template**

Create `flask_backend/templates/inspections/admin/index.html`:

```jinja
{% extends "base.html" %}
{% block title %}
    Inspeções de Filmes
{% endblock title %}
{% block header %}
    <div>
        <h1>Inspeções de Filmes</h1>
        <p>Verificações automáticas do vínculo TMDB de cada filme contra o que os cinemas publicaram sobre ele.</p>
    </div>
{% endblock header %}
{% block content %}
    {% set status_labels = {
        "consistent": "Consistente",
        "fixed": "Corrigido",
        "needs_review": "Revisão manual",
        "error": "Erro",
        "reverted": "Revertido",
        "all": "Todos"
    } %}
    {% set status_classes = {
        "consistent": "bg-success",
        "fixed": "bg-info text-dark",
        "needs_review": "bg-warning text-dark",
        "error": "bg-danger",
        "reverted": "bg-secondary"
    } %}
    <ul class="nav nav-tabs mb-3">
        {% for filter_status in ["all", "needs_review", "fixed", "consistent", "error", "reverted"] %}
            <li class="nav-item">
                <a class="nav-link {% if status == filter_status %}active{% endif %}"
                   href="{{ url_for('admin_inspections.index', status=filter_status) }}">{{ status_labels[filter_status] }}</a>
            </li>
        {% endfor %}
    </ul>
    {% if inspections %}
        <div class="table-responsive">
            <table class="table table-striped align-middle">
                <thead>
                    <tr>
                        <th>Quando</th>
                        <th>Filme</th>
                        <th>Status</th>
                        <th>Raciocínio</th>
                        <th>Ação</th>
                    </tr>
                </thead>
                <tbody>
                    {% for inspection in inspections %}
                        <tr>
                            <td>
                                <time datetime="{{ inspection.created_at.isoformat() }}">{{ inspection.created_at.strftime("%d/%m/%Y %H:%M") }}</time>
                            </td>
                            <td>
                                <a href="{{ url_for('admin_movies.edit', movie_id=inspection.movie_id) }}">{{ inspection.movie.title }}</a>
                            </td>
                            <td>
                                <span class="badge {{ status_classes[inspection.status] }}">{{ status_labels[inspection.status] }}</span>
                            </td>
                            <td>{{ inspection.reasoning }}</td>
                            <td>
                                {% if inspection.status == "fixed" %}
                                    <form method="post"
                                          action="{{ url_for('admin_inspections.revert', inspection_id=inspection.id) }}">
                                        <input type="hidden" name="status" value="{{ status }}">
                                        <button type="submit" class="btn btn-sm btn-outline-danger">Reverter</button>
                                    </form>
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
                               href="{{ url_for('admin_inspections.index', status=status, page=prev_page, limit=limit) }}">Anterior</a>
                        </li>
                    {% endif %}
                    {% for page_num in range(1, pages + 1) %}
                        <li class="page-item {% if page_num == curr_page %}active{% endif %}">
                            <a class="page-link"
                               href="{{ url_for('admin_inspections.index', status=status, page=page_num, limit=limit) }}">{{ page_num }}</a>
                        </li>
                    {% endfor %}
                    {% if next_page %}
                        <li class="page-item">
                            <a class="page-link"
                               href="{{ url_for('admin_inspections.index', status=status, page=next_page, limit=limit) }}">Próximo</a>
                        </li>
                    {% endif %}
                </ul>
            </nav>
        {% endif %}
    {% else %}
        <p>Nenhuma inspeção registrada ainda.</p>
    {% endif %}
{% endblock content %}
```

Note: this template references `admin_inspections.revert`, which is only added in Task 7. That's fine for this task: none of Step 1's fixtures use `status="fixed"` (see the comment in `test_filters_by_status`), so the Revert button branch never renders yet, and `url_for('admin_inspections.revert', ...)` is never evaluated. It resolves naturally once Task 7 registers that endpoint.

- [ ] **Step 5: Register the blueprint**

In `flask_backend/__init__.py`, add after the `admin_movies` registration:

```python
    from .routes.admin import movies as admin_movies

    app.register_blueprint(admin_movies.bp)

    from .routes.admin import inspections as admin_inspections

    app.register_blueprint(admin_inspections.bp)
```

- [ ] **Step 6: Add the nav link**

In `flask_backend/templates/base.html`, add a dropdown item after the Pipelines link:

```html
                            <li>
                                <a class="dropdown-item {% if request.path.startswith('/admin/pipelines') %}active{% endif %}"
                                   href="{{ url_for("admin_pipelines.index") }}">Pipelines</a>
                            </li>
                            <li>
                                <a class="dropdown-item {% if request.path.startswith('/admin/movies/inspections') %}active{% endif %}"
                                   href="{{ url_for("admin_inspections.index") }}">Inspeções de Filmes</a>
                            </li>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_inspections.py -v`
Expected: PASS (6 tests)

- [ ] **Step 8: Commit**

```bash
git add flask_backend/routes/admin/inspections.py \
        flask_backend/templates/inspections/admin/index.html \
        flask_backend/__init__.py \
        flask_backend/templates/base.html \
        flask_backend/tests/test_routes/test_admin/test_admin_inspections.py
git commit -m "feat: add /admin/movies/inspections dashboard"
```

---

## Task 7: Revert action

**Files:**
- Modify: `flask_backend/routes/admin/inspections.py`
- Test: `flask_backend/tests/test_routes/test_admin/test_admin_inspections.py`

**Interfaces:**
- Consumes: `movie_inspector.revert_inspection` (Task 4); `repository.movie_inspections.get_by_id` (Task 1).
- Produces: `POST /admin/movies/inspections/<int:inspection_id>/revert` (view name `admin_inspections.revert`), which the Task 6 template already links to.

- [ ] **Step 1: Write failing tests for revert**

Append to `flask_backend/tests/test_routes/test_admin/test_admin_inspections.py`:

```python
from unittest.mock import patch


class TestAdminInspectionsRevert:
    def test_requires_login(self, client, app):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            inspection_id = inspection.id

        response = client.post(f"/admin/movies/inspections/{inspection_id}/revert")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_missing_inspection(self, auth_headers):
        response = auth_headers.post("/admin/movies/inspections/99999/revert")
        assert response.status_code == 404

    def test_returns_400_for_non_fixed_inspection(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id, status="consistent", reasoning="ok", checked_tmdb_id=42
            )
            inspection_id = inspection.id

        response = auth_headers.post(
            f"/admin/movies/inspections/{inspection_id}/revert"
        )
        assert response.status_code == 400

    def test_reverts_and_redirects(self, app, auth_headers):
        with app.app_context():
            movie = _create_movie(tmdb_id=42)
            inspection = movie_inspections.create(
                movie_id=movie.id, status="fixed", reasoning="a", checked_tmdb_id=42
            )
            inspection_id = inspection.id

        with patch(
            "flask_backend.routes.admin.inspections.revert_inspection"
        ) as mock_revert:
            response = auth_headers.post(
                f"/admin/movies/inspections/{inspection_id}/revert",
                data={"status": "fixed"},
            )

        mock_revert.assert_called_once_with(inspection_id)
        assert response.status_code == 302
        assert response.headers["Location"].endswith(
            "/admin/movies/inspections?status=fixed"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_inspections.py -k Revert -v`
Expected: FAIL — 404 (`admin_inspections.revert` doesn't exist yet).

- [ ] **Step 3: Implement the route**

In `flask_backend/routes/admin/inspections.py`, add the import and the view:

```python
from flask_backend.service.movie_inspector import revert_inspection
```

```python
@bp.route("/admin/movies/inspections/<int:inspection_id>/revert", methods=("POST",))
@login_required
def revert(inspection_id):
    inspection = movie_inspections.get_by_id(inspection_id)
    if inspection is None:
        abort(404)
    if inspection.status != "fixed":
        abort(400)

    revert_inspection(inspection_id)
    flash("Correção revertida.", "success")
    return redirect(
        url_for("admin_inspections.index", status=request.form.get("status", "all"))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_inspections.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest flask_backend/tests`
Expected: PASS, no regressions anywhere.

- [ ] **Step 6: Lint and format**

```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```

Fix anything flagged, then re-run `pytest flask_backend/tests` to confirm formatting changes didn't break anything.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/routes/admin/inspections.py flask_backend/tests/test_routes/test_admin/test_admin_inspections.py
git commit -m "feat: add revert action for movie inspection fixes"
```

---

## Manual Verification (after Task 7)

The automated suite mocks Gemini/TMDB everywhere, so it never proves the real `inspect-movies` command works end-to-end against live services. Before considering this feature done:

1. Copy `example.env` to `.env` if not already done, and ensure `GEMINI_API_KEY` and `TMDB_API_TOKEN` are set.
2. Pick or create a movie in `development.sqlite` with a known-wrong `tmdb_id` (e.g. reproduce the `a-capela` case from the design doc).
3. Run `flask --app flask_backend inspect-movies --limit 1` and confirm it either fixes the match or reports `needs_review` with sensible reasoning.
4. Visit `/admin/movies/inspections`, confirm the row renders correctly, and if it was `fixed`, click **Reverter** and confirm the movie's TMDB link reverts.
