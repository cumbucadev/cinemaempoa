# Admin Alerts Radical Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 8-rule `Alert` pipeline behind `/admin/alerts` with a live-computed Pendentes view (per-`Screening` rows classified única/recorrente straight from the schedule) plus a small `alert_actions` log for posting history and reminders, per `docs/superpowers/specs/2026-07-24-admin-alerts-usability-design.md` (issue #258).

**Architecture:** Build the new system additively alongside the old one first (new model, repository, service, route/template cutover, integration-point porting) so the test suite stays green after every task. Only once nothing depends on the old system anymore does a final removal sweep delete `alert_rules.py`, `alert_pipeline.py`, `alert_text.py`, `repository/alerts.py`, the `Alert` model/table, the `generate-alerts` CLI/cron, and their entry in `/admin/pipelines`.

**Tech Stack:** Flask, SQLAlchemy (Alembic migrations), Jinja2, pytest, `python-dateutil` (already a dependency, used for the 6-month grace period).

## Global Constraints

- Branch: `refactor/#258-simplify-alerts`. Spec: `docs/superpowers/specs/2026-07-24-admin-alerts-usability-design.md`.
- Row granularity is per-`Screening` (movie+cinema pairing), never per-`Movie`.
- Única vs. recorrente counts `ScreeningDate`s where `date >= today - RECORRENTE_GRACE_PERIOD` (default 6 months via `dateutil.relativedelta`), not just future dates — this is what keeps a long-running screening classified Recorrente on its last scheduled day.
- The reminder date input gets an HTML `max` attribute (front-end only, no server-side re-validation) equal to the screening's last upcoming date.
- `collections`/`movies.collection_id`, `screenings.title_cleaning_rules`/`raw_title`, and all other pipelines (`import-json`, `fetch-posters`, `fetch-movie-metadata`) are out of scope and must not be touched.
- Run `uv run ruff check --fix`, `uv run ruff format`, and `uv run djlint --reformat flask_backend/templates --format-css --format-js` before the final task's verification pass (per `AGENTS.md`).
- Never add an AI/agent co-author trailer to commits.

---

### Task 1: `AlertAction` model, migration, and repository

**Files:**
- Modify: `flask_backend/models.py`
- Create: `migrations/versions/20260724_000000_add_alert_actions.py`
- Create: `flask_backend/repository/alert_actions.py`
- Modify: `flask_backend/tests/conftest.py`
- Test: `flask_backend/tests/test_repository/test_alert_actions.py`

**Interfaces:**
- Produces: `flask_backend.models.AlertAction` (columns: `id`, `screening_id`, `action`, `remind_at`, `created_at`, `created_by_user_id`), `flask_backend.models.ALERT_ACTIONS = ["posted", "dismissed"]`.
- Produces: `flask_backend.repository.alert_actions.create(screening_id: int, action: str, remind_at: Optional[date] = None, created_by_user_id: Optional[int] = None, commit: bool = True) -> AlertAction`, `.get_latest_by_screening_ids(screening_ids: List[int]) -> Dict[int, AlertAction]`, `.get_paginated(action: Optional[str], current_page: int, per_page: int) -> Tuple[List[AlertAction], int, int]`, `.delete_for_screening(screening_id: int) -> None`, `.repoint_to_screening(old_screening_id: int, new_screening_id: int) -> None`.

- [ ] **Step 1: Write the failing repository tests**

Create `flask_backend/tests/test_repository/test_alert_actions.py`:

```python
from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import AlertAction, Movie, Screening, ScreeningDate, User
from flask_backend.repository import alert_actions
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


def _create_screening(app, movie_title="Filme", movie_slug="filme"):
    with app.app_context():
        movie = Movie(title=movie_title, slug=movie_slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug("capitolio")
        screening = Screening(
            movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
        )
        db_session.add(screening)
        db_session.commit()
        db_session.add(
            ScreeningDate(
                screening_id=screening.id,
                date=date.today() + timedelta(days=1),
                time="20:00",
            )
        )
        db_session.commit()
        return screening.id


class TestCreate:
    def test_creates_action_without_reminder(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            action = alert_actions.create(screening_id=screening_id, action="posted")

            assert action.id is not None
            assert action.screening_id == screening_id
            assert action.action == "posted"
            assert action.remind_at is None
            assert action.created_at is not None

    def test_creates_action_with_reminder_and_user(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            user = User(username="admin", password="pwd")
            db_session.add(user)
            db_session.commit()

            remind_at = date.today() + timedelta(days=3)
            action = alert_actions.create(
                screening_id=screening_id,
                action="dismissed",
                remind_at=remind_at,
                created_by_user_id=user.id,
            )

            assert action.remind_at == remind_at
            assert action.created_by_user_id == user.id


class TestGetLatestByScreeningIds:
    def test_returns_most_recent_action_per_screening(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            older = AlertAction(
                screening_id=screening_id,
                action="dismissed",
                created_at=datetime(2026, 1, 1),
            )
            newer = AlertAction(
                screening_id=screening_id,
                action="posted",
                created_at=datetime(2026, 1, 2),
            )
            db_session.add_all([older, newer])
            db_session.commit()

            latest = alert_actions.get_latest_by_screening_ids([screening_id])

            assert latest[screening_id].action == "posted"

    def test_ignores_screenings_with_no_actions(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            latest = alert_actions.get_latest_by_screening_ids([screening_id])

            assert latest == {}

    def test_returns_empty_dict_for_empty_input(self, app):
        with app.app_context():
            assert alert_actions.get_latest_by_screening_ids([]) == {}


class TestGetPaginated:
    def test_filters_by_action(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

            posted, pages, count = alert_actions.get_paginated("posted", 1, 20)

            assert count == 1
            assert posted[0].action == "posted"

    def test_none_action_returns_everything(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

            actions, pages, count = alert_actions.get_paginated(None, 1, 20)

            assert count == 2


class TestDeleteForScreening:
    def test_removes_all_actions_for_the_screening(self, app, setup_cinemas):
        screening_id = _create_screening(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

            alert_actions.delete_for_screening(screening_id)
            db_session.commit()

            remaining = (
                db_session.query(AlertAction)
                .filter_by(screening_id=screening_id)
                .count()
            )
            assert remaining == 0


class TestRepointToScreening:
    def test_moves_actions_to_the_new_screening(self, app, setup_cinemas):
        old_screening_id = _create_screening(app, "Filme A", "filme-a")
        new_screening_id = _create_screening(app, "Filme B", "filme-b")
        with app.app_context():
            action = alert_actions.create(
                screening_id=old_screening_id, action="posted"
            )
            action_id = action.id

            alert_actions.repoint_to_screening(old_screening_id, new_screening_id)
            db_session.commit()

            refreshed = db_session.query(AlertAction).filter_by(id=action_id).one()
            assert refreshed.screening_id == new_screening_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_alert_actions.py -v`
Expected: FAIL/ERROR — `AlertAction` and `flask_backend.repository.alert_actions` don't exist yet.

- [ ] **Step 3: Add the `AlertAction` model**

In `flask_backend/models.py`, insert after line 28 (`PIPELINE_RUN_STATUSES = [...]`):

```python
ALERT_ACTIONS = ["posted", "dismissed"]
```

Then insert a new class right after the existing `Alert` class ends (after `resolved_by: Mapped[Optional["User"]] = relationship()`, before `class BlogPost(Base):`):

```python
class AlertAction(Base):
    """One posted/dismissed action taken on a Screening from /admin/alerts
    (issue #258). Append-only log - a screening can accumulate several rows
    over its run (e.g. posted once, resurfaces via `remind_at`, dismissed
    later), which is what gives the admin a real posting history instead of
    a single mutable status. Replaces the Alert model."""

    __tablename__ = "alert_actions"

    id = Column(Integer, primary_key=True)
    screening_id = Column(
        Integer, ForeignKey("screenings.id"), nullable=False, index=True
    )
    action = Column(String, nullable=False, index=True)
    # If set, this screening is excluded from Pendentes until this date
    # arrives (see flask_backend/service/screening_alerts.py). NULL means
    # excluded indefinitely.
    remind_at = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    screening: Mapped["Screening"] = relationship()
    created_by: Mapped[Optional["User"]] = relationship()
```

- [ ] **Step 4: Write the migration**

Create `migrations/versions/20260724_000000_add_alert_actions.py`:

```python
"""Adds alert_actions (issue #258): the append-only posted/dismissed log
for the live-computed /admin/alerts Pendentes view. The old `alerts` table
and its generation pipeline are removed in a later migration once the
route and CLI stop depending on them.

Revision ID: 20260724_000000
Revises: 20260721_000000
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260724_000000"
down_revision: Union[str, None] = "20260721_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("screening_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("remind_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["screening_id"], ["screenings.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_alert_actions_screening_id", "alert_actions", ["screening_id"]
    )
    op.create_index("ix_alert_actions_action", "alert_actions", ["action"])


def downgrade() -> None:
    op.drop_index("ix_alert_actions_action", table_name="alert_actions")
    op.drop_index("ix_alert_actions_screening_id", table_name="alert_actions")
    op.drop_table("alert_actions")
```

- [ ] **Step 5: Write the repository module**

Create `flask_backend/repository/alert_actions.py`:

```python
"""Data access for AlertAction rows - the append-only posted/dismissed
action log behind /admin/alerts (issue #258). Replaces repository/alerts.py:
unlike the old Alert rows, these aren't generated by a pipeline - they're
only ever created by an admin action, and "which screenings are currently
pending" is answered live (see flask_backend/service/screening_alerts.py),
not by querying this table directly.
"""

from datetime import date, datetime
from math import ceil
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import AlertAction


def create(
    screening_id: int,
    action: str,
    remind_at: Optional[date] = None,
    created_by_user_id: Optional[int] = None,
    commit: bool = True,
) -> AlertAction:
    alert_action = AlertAction(
        screening_id=screening_id,
        action=action,
        remind_at=remind_at,
        created_at=datetime.now(),
        created_by_user_id=created_by_user_id,
    )
    db_session.add(alert_action)
    if commit:
        db_session.commit()
        db_session.refresh(alert_action)
    return alert_action


def get_latest_by_screening_ids(screening_ids: List[int]) -> Dict[int, AlertAction]:
    """Most recent AlertAction per screening_id (ties broken by id), for
    whichever of `screening_ids` have at least one action."""
    if not screening_ids:
        return {}
    rows = (
        db_session.query(AlertAction)
        .filter(AlertAction.screening_id.in_(screening_ids))
        .order_by(
            AlertAction.screening_id,
            AlertAction.created_at.desc(),
            AlertAction.id.desc(),
        )
        .all()
    )
    latest: Dict[int, AlertAction] = {}
    for row in rows:
        if row.screening_id not in latest:
            latest[row.screening_id] = row
    return latest


def get_paginated(
    action: Optional[str], current_page: int, per_page: int
) -> Tuple[List[AlertAction], int, int]:
    offset_value = (current_page - 1) * per_page

    query = db_session.query(AlertAction)
    if action is not None:
        query = query.filter(AlertAction.action == action)

    query = (
        query.order_by(AlertAction.created_at.desc())
        .limit(per_page)
        .offset(offset_value)
    )
    actions = query.all()

    count_query = db_session.query(func.count(AlertAction.id))
    if action is not None:
        count_query = count_query.filter(AlertAction.action == action)
    total_count = count_query.scalar()
    total_pages = ceil(total_count / per_page) if total_count else 0

    return (actions, total_pages, total_count)


def delete_for_screening(screening_id: int) -> None:
    db_session.query(AlertAction).filter(
        AlertAction.screening_id == screening_id
    ).delete(synchronize_session=False)


def repoint_to_screening(old_screening_id: int, new_screening_id: int) -> None:
    db_session.query(AlertAction).filter(
        AlertAction.screening_id == old_screening_id
    ).update({"screening_id": new_screening_id})
```

- [ ] **Step 6: Register `AlertAction` in the test-DB cleanup fixture**

In `flask_backend/tests/conftest.py`, add `AlertAction` to the import list (alongside `Alert`, which stays for now):

```python
        from flask_backend.models import (
            Alert,
            AlertAction,
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
        db_session.query(AlertAction).delete()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_alert_actions.py -v`
Expected: PASS (all tests green)

- [ ] **Step 8: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add flask_backend/models.py migrations/versions/20260724_000000_add_alert_actions.py flask_backend/repository/alert_actions.py flask_backend/tests/conftest.py flask_backend/tests/test_repository/test_alert_actions.py
git commit -m "feat: add AlertAction model, migration and repository (#258)"
```

---

### Task 2: `service/screening_alerts.py` — classification with grace period

**Files:**
- Create: `flask_backend/service/screening_alerts.py`
- Test: `flask_backend/tests/test_service/test_screening_alerts.py`

**Interfaces:**
- Consumes: `flask_backend.models.Screening` (`.dates` → list of `ScreeningDate` with `.date`).
- Produces: `UNICA = "unica"`, `RECORRENTE = "recorrente"`, `RECORRENTE_GRACE_PERIOD` (a `dateutil.relativedelta.relativedelta`), `classify(screening: Screening, today: Optional[date] = None) -> str`, `last_upcoming_date(screening: Screening, today: Optional[date] = None) -> Optional[date]`.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_service/test_screening_alerts.py`:

```python
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.screening_alerts import (
    RECORRENTE,
    UNICA,
    classify,
    last_upcoming_date,
)


def _create_movie(title="Filme", slug="filme"):
    movie = Movie(title=title, slug=slug, created_at=datetime.now())
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _create_screening(movie, dates, cinema_slug="capitolio"):
    cinema = get_cinema_by_slug(cinema_slug)
    screening = Screening(
        movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
    )
    db_session.add(screening)
    db_session.commit()
    for screening_date in dates:
        db_session.add(
            ScreeningDate(screening_id=screening.id, date=screening_date, time="20:00")
        )
    db_session.commit()
    db_session.refresh(screening)
    return screening


class TestClassify:
    def test_single_upcoming_date_is_unica(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])

            assert classify(screening, today=date(2026, 7, 24)) == UNICA

    def test_multiple_upcoming_dates_is_recorrente(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(
                movie, [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)]
            )

            assert classify(screening, today=date(2026, 7, 24)) == RECORRENTE

    def test_last_day_of_a_long_run_stays_recorrente(self, client, app, setup_cinemas):
        # Regression: without the grace-period window, a recorring
        # screening's remaining-future-date count drops to 1 on its last
        # scheduled day, misclassifying it as "unica" right when it's
        # wrapping up a long run.
        with client.application.app_context():
            movie = _create_movie()
            past_dates = [date(2026, 6, day) for day in range(1, 21)]
            screening = _create_screening(movie, past_dates + [date(2026, 7, 24)])

            assert classify(screening, today=date(2026, 7, 24)) == RECORRENTE

    def test_prior_occurrence_outside_grace_window_resets_to_unica(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(
                movie, [date(2025, 11, 20), date(2026, 8, 1)]
            )

            assert classify(screening, today=date(2026, 7, 24)) == UNICA

    def test_grace_window_boundary_is_inclusive(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            today = date(2026, 7, 24)
            boundary_date = today - relativedelta(months=6)
            screening = _create_screening(movie, [boundary_date, date(2026, 8, 1)])

            assert classify(screening, today=today) == RECORRENTE


class TestLastUpcomingDate:
    def test_returns_the_latest_upcoming_date(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(
                movie, [date(2026, 8, 1), date(2026, 8, 10), date(2026, 6, 1)]
            )

            assert last_upcoming_date(
                screening, today=date(2026, 7, 24)
            ) == date(2026, 8, 10)

    def test_returns_none_without_upcoming_dates(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 1, 1)])

            assert last_upcoming_date(screening, today=date(2026, 7, 24)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_screening_alerts.py -v`
Expected: FAIL — `flask_backend.service.screening_alerts` doesn't exist yet.

- [ ] **Step 3: Implement classification**

Create `flask_backend/service/screening_alerts.py`:

```python
"""Computes the admin's two alert categories (Sessão única / Recorrente)
live from the current schedule (issue #258), replacing the old detection-
rule pipeline in service/alert_rules.py + service/alert_pipeline.py. Pure
functions, no DB writes.
"""

from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from flask_backend.models import Screening

UNICA = "unica"
RECORRENTE = "recorrente"

# How far back to look when counting a screening's dates for
# classification, so a long-running screening doesn't misclassify as
# "unica" on its last scheduled day (only 1 future date left) - see the
# design doc's "Classification rule". Code constant, not user-configurable.
RECORRENTE_GRACE_PERIOD = relativedelta(months=6)


def classify(screening: Screening, today: Optional[date] = None) -> str:
    """Sessão única vs. recorrente: counts ScreeningDates within
    [today - RECORRENTE_GRACE_PERIOD, +inf), combining recent-past and
    future dates. Exactly 1 -> unica; more -> recorrente."""
    today = today or date.today()
    window_start = today - RECORRENTE_GRACE_PERIOD
    count = sum(1 for screening_date in screening.dates if screening_date.date >= window_start)
    return UNICA if count == 1 else RECORRENTE


def last_upcoming_date(screening: Screening, today: Optional[date] = None) -> Optional[date]:
    """The screening's last ScreeningDate that is still upcoming (>= today),
    or None if it has none. Unaffected by the grace period."""
    today = today or date.today()
    upcoming = [
        screening_date.date for screening_date in screening.dates if screening_date.date >= today
    ]
    return max(upcoming) if upcoming else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening_alerts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/screening_alerts.py flask_backend/tests/test_service/test_screening_alerts.py
git commit -m "feat: add unica/recorrente classification with grace period (#258)"
```

---

### Task 3: `build_drafted_text` — screening-scoped copyable post text

**Files:**
- Modify: `flask_backend/service/screening_alerts.py`
- Test: `flask_backend/tests/test_service/test_screening_alerts.py`

**Interfaces:**
- Consumes: `classify` (Task 2), `Screening.movie` (title, release_year, directors), `Screening.cinema.name`.
- Produces: `build_drafted_text(screening: Screening, today: Optional[date] = None) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_service/test_screening_alerts.py` (add `Director` to the existing `from flask_backend.models import ...` line, and `build_drafted_text` to the existing `from flask_backend.service.screening_alerts import ...` line):

```python
class TestBuildDraftedText:
    def test_unica_includes_emoji_year_director_next_date_and_cinema(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie(title="Duna", slug="duna")
            movie.release_year = 2021
            director = Director(tmdb_id=1, name="Denis Villeneuve")
            db_session.add(director)
            movie.directors.append(director)
            db_session.commit()

            screening = _create_screening(movie, [date(2026, 8, 1)])

            text = build_drafted_text(screening, today=date(2026, 7, 24))

            assert text == (
                "⏳ Duna (2021) de Denis Villeneuve\n\n"
                "01/08 20:00\nNa Cinemateca Capitólio"
            )

    def test_recorrente_uses_the_next_upcoming_date_not_the_last(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie(title="Duna", slug="duna")
            screening = _create_screening(
                movie, [date(2026, 8, 1), date(2026, 8, 5), date(2026, 8, 10)]
            )

            text = build_drafted_text(screening, today=date(2026, 7, 24))

            assert text.startswith("🔁 Duna\n\n01/08 20:00")

    def test_omits_year_and_director_when_absent(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie(title="Filme Sem Metadados", slug="filme-sem-meta")
            screening = _create_screening(movie, [date(2026, 8, 1)])

            text = build_drafted_text(screening, today=date(2026, 7, 24))

            assert text.startswith("⏳ Filme Sem Metadados\n\n")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_screening_alerts.py::TestBuildDraftedText -v`
Expected: FAIL — `build_drafted_text` and `Director` import don't exist in the test module yet / function undefined.

- [ ] **Step 3: Implement `build_drafted_text`**

Append to `flask_backend/service/screening_alerts.py`:

```python
CATEGORY_EMOJIS = {UNICA: "⏳", RECORRENTE: "🔁"}


def build_drafted_text(screening: Screening, today: Optional[date] = None) -> str:
    """Copyable post text for a Screening row on the Pendentes tab - title,
    release year, director(s), and this screening's own next upcoming date
    at its own cinema (not the movie's next showing at any cinema, since a
    row is scoped to one screening/cinema)."""
    today = today or date.today()
    movie = screening.movie
    emoji = CATEGORY_EMOJIS[classify(screening, today)]

    title_line = f"{emoji} {movie.title}".strip()
    if movie.release_year:
        title_line += f" ({movie.release_year})"
    if movie.directors:
        names = ", ".join(director.name for director in movie.directors)
        title_line += f" de {names}"

    upcoming = sorted(
        (d for d in screening.dates if d.date >= today),
        key=lambda d: (d.date, d.time or ""),
    )
    if not upcoming:
        body = "Sem sessão futura agendada"
    else:
        next_date = upcoming[0]
        when = f"{next_date.date.strftime('%d/%m')} {next_date.time}"
        body = f"{when}\nNa {screening.cinema.name}"

    return f"{title_line}\n\n{body}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening_alerts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/screening_alerts.py flask_backend/tests/test_service/test_screening_alerts.py
git commit -m "feat: build screening-scoped drafted post text (#258)"
```

---

### Task 4: `repository/screenings.py::get_screenings_with_upcoming_dates`

**Files:**
- Modify: `flask_backend/repository/screenings.py`
- Test: `flask_backend/tests/test_repository/test_screenings.py`

**Interfaces:**
- Produces: `get_screenings_with_upcoming_dates() -> List[Screening]` — non-draft screenings with at least one `ScreeningDate >= today`.

- [ ] **Step 1: Write the failing test**

Create `flask_backend/tests/test_repository/test_screenings.py`:

```python
from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.screenings import get_screenings_with_upcoming_dates


def _create_screening(app, title, slug, dates, draft=False):
    with app.app_context():
        movie = Movie(title=title, slug=slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug("capitolio")
        screening = Screening(
            movie_id=movie.id,
            cinema_id=cinema.id,
            description="desc",
            draft=draft,
        )
        db_session.add(screening)
        db_session.commit()
        for screening_date in dates:
            db_session.add(
                ScreeningDate(screening_id=screening.id, date=screening_date, time="20:00")
            )
        db_session.commit()
        return screening.id


class TestGetScreeningsWithUpcomingDates:
    def test_includes_screening_with_a_future_date(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id in ids

    def test_excludes_screening_with_only_past_dates(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Filme Antigo", "filme-antigo", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id not in ids

    def test_excludes_draft_screenings(self, app, setup_cinemas):
        screening_id = _create_screening(
            app,
            "Rascunho",
            "rascunho",
            [date.today() + timedelta(days=1)],
            draft=True,
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert screening_id not in ids

    def test_does_not_duplicate_screenings_with_multiple_future_dates(
        self, app, setup_cinemas
    ):
        screening_id = _create_screening(
            app,
            "Recorrente",
            "recorrente",
            [date.today() + timedelta(days=1), date.today() + timedelta(days=2)],
        )

        with app.app_context():
            ids = [s.id for s in get_screenings_with_upcoming_dates()]
            assert ids.count(screening_id) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v`
Expected: FAIL — `get_screenings_with_upcoming_dates` doesn't exist yet.

- [ ] **Step 3: Implement the query**

In `flask_backend/repository/screenings.py`, append (near `get_screenings_due_for_core_alert_evaluation`, which will be removed in Task 9):

```python
def get_screenings_with_upcoming_dates() -> List[Screening]:
    """Non-draft screenings with at least one ScreeningDate >= today -
    candidates for the live-computed Pendentes view (issue #258, see
    flask_backend/service/screening_alerts.py)."""
    today = date.today()
    return (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(Screening.draft == False)  # noqa: E712
        .filter(func.date(ScreeningDate.date) >= today)
        .distinct()
        .all()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/tests/test_repository/test_screenings.py
git commit -m "feat: add repository query for screenings with upcoming dates (#258)"
```

---

### Task 5: `get_pending_rows` — ties classification, reminders, and sort together

**Files:**
- Modify: `flask_backend/service/screening_alerts.py`
- Test: `flask_backend/tests/test_service/test_screening_alerts.py`

**Interfaces:**
- Consumes: `classify`, `last_upcoming_date`, `build_drafted_text` (this file); `flask_backend.models.AlertAction`.
- Produces: `PendingRow` (dataclass: `screening: Screening`, `category: str`, `last_upcoming_date: date`, `drafted_text: str`), `get_pending_rows(screenings: List[Screening], latest_actions: Dict[int, AlertAction], today: Optional[date] = None) -> List[PendingRow]`.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_service/test_screening_alerts.py` (add `get_pending_rows` to the existing import line):

```python
class TestGetPendingRows:
    def test_includes_screening_with_no_action(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])

            rows = get_pending_rows([screening], {}, today=date(2026, 7, 24))

            assert len(rows) == 1
            assert rows[0].screening.id == screening.id
            assert rows[0].category == UNICA
            assert rows[0].last_upcoming_date == date(2026, 8, 1)

    def test_excludes_screening_with_indefinite_action(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])
            action = AlertAction(
                screening_id=screening.id, action="posted", created_at=datetime.now()
            )

            rows = get_pending_rows(
                [screening], {screening.id: action}, today=date(2026, 7, 24)
            )

            assert rows == []

    def test_excludes_screening_whose_reminder_has_not_arrived(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])
            action = AlertAction(
                screening_id=screening.id,
                action="dismissed",
                created_at=datetime.now(),
                remind_at=date(2026, 7, 30),
            )

            rows = get_pending_rows(
                [screening], {screening.id: action}, today=date(2026, 7, 24)
            )

            assert rows == []

    def test_includes_screening_whose_reminder_has_arrived(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            movie = _create_movie()
            screening = _create_screening(movie, [date(2026, 8, 1)])
            action = AlertAction(
                screening_id=screening.id,
                action="posted",
                created_at=datetime.now(),
                remind_at=date(2026, 7, 24),
            )

            rows = get_pending_rows(
                [screening], {screening.id: action}, today=date(2026, 7, 24)
            )

            assert len(rows) == 1

    def test_sorts_by_nearest_upcoming_date_ascending(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie()
            later = _create_screening(movie, [date(2026, 9, 1)])
            sooner = _create_screening(
                _create_movie(title="Filme 2", slug="filme-2"), [date(2026, 8, 1)]
            )

            rows = get_pending_rows([later, sooner], {}, today=date(2026, 7, 24))

            assert [row.screening.id for row in rows] == [sooner.id, later.id]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_screening_alerts.py::TestGetPendingRows -v`
Expected: FAIL — `PendingRow`/`get_pending_rows` and the `AlertAction`/`datetime` imports don't exist in the test module yet.

Add `AlertAction` to the test module's `from flask_backend.models import ...` line (it already imports `Movie, Screening, ScreeningDate`).

- [ ] **Step 3: Implement `get_pending_rows`**

Append to `flask_backend/service/screening_alerts.py` (add `dataclass` and `Dict, List` to the existing imports, and `AlertAction` to the `flask_backend.models` import):

```python
from dataclasses import dataclass
...
from typing import Dict, List, Optional
...
from flask_backend.models import AlertAction, Screening


@dataclass(frozen=True)
class PendingRow:
    screening: Screening
    category: str
    last_upcoming_date: date
    drafted_text: str


def get_pending_rows(
    screenings: List[Screening],
    latest_actions: Dict[int, AlertAction],
    today: Optional[date] = None,
) -> List[PendingRow]:
    """Builds and sorts the Pendentes rows from `screenings` (expected to
    already be filtered to non-draft, has-an-upcoming-date, e.g. via
    repository.screenings.get_screenings_with_upcoming_dates), excluding
    any screening whose most recent action's remind_at hasn't arrived yet.
    Sorted ascending by nearest upcoming ScreeningDate."""
    today = today or date.today()
    rows = []
    for screening in screenings:
        latest_action = latest_actions.get(screening.id)
        if latest_action is not None and (
            latest_action.remind_at is None or latest_action.remind_at > today
        ):
            continue
        rows.append(
            PendingRow(
                screening=screening,
                category=classify(screening, today),
                last_upcoming_date=last_upcoming_date(screening, today),
                drafted_text=build_drafted_text(screening, today),
            )
        )
    rows.sort(
        key=lambda row: min(d.date for d in row.screening.dates if d.date >= today)
    )
    return rows
```

Note the full updated import block at the top of the file becomes:

```python
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from dateutil.relativedelta import relativedelta

from flask_backend.models import AlertAction, Screening
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening_alerts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/screening_alerts.py flask_backend/tests/test_service/test_screening_alerts.py
git commit -m "feat: compute and sort pending rows with reminder resolution (#258)"
```

---

### Task 6: Pendentes tab — route and template cutover

**Files:**
- Modify: `flask_backend/routes/admin/alerts.py`
- Modify: `flask_backend/templates/alerts/admin/index.html`
- Test: `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py`

**Interfaces:**
- Consumes: `repository.screenings.get_screenings_with_upcoming_dates` (Task 4), `repository.alert_actions.get_latest_by_screening_ids` (Task 1), `service.screening_alerts.get_pending_rows`/`PendingRow`/`UNICA`/`RECORRENTE` (Task 5).

This task fully replaces `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py` — the old file's tests assert against the `Alert`-based rendering this task removes. Delete its contents and start fresh (Tasks 7 and 8 append more classes to this same file).

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py` with:

```python
"""
Tests the basic functionality of /admin/alerts/* endpoints.
"""

from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import AlertAction, Movie, Screening, ScreeningDate
from flask_backend.repository import alert_actions
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


def _create_screening_with_future_date(app, title="Duna", slug="duna", days=1):
    with app.app_context():
        movie = Movie(title=title, slug=slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug("capitolio")
        screening = Screening(
            movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
        )
        db_session.add(screening)
        db_session.commit()
        db_session.add(
            ScreeningDate(
                screening_id=screening.id,
                date=date.today() + timedelta(days=days),
                time="20:00",
            )
        )
        db_session.commit()
        return screening.id


class TestAdminAlertsPendingView:
    def test_requires_login(self, client):
        response = client.get("/admin/alerts")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200(self, auth_headers):
        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200

    def test_invalid_pagination_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?page=invalid&limit=10")
        assert response.status_code == 400

    def test_invalid_status_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?status=bogus")
        assert response.status_code == 400

    def test_zero_limit_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?limit=0")
        assert response.status_code == 400

    def test_zero_page_returns_400(self, auth_headers):
        response = auth_headers.get("/admin/alerts?page=0")
        assert response.status_code == 400

    def test_shows_unica_screening_with_cinema_in_badge(
        self, app, auth_headers, setup_cinemas
    ):
        _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert "Sessão única — Cinemateca Capitólio".encode() in response.data

    def test_shows_recorrente_screening_with_until_date(
        self, app, auth_headers, setup_cinemas
    ):
        with app.app_context():
            movie = Movie(title="Duna", slug="duna", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
            )
            db_session.add(screening)
            db_session.commit()
            for offset in (1, 2, 3):
                db_session.add(
                    ScreeningDate(
                        screening_id=screening.id,
                        date=date.today() + timedelta(days=offset),
                        time="20:00",
                    )
                )
            db_session.commit()
        last_date = date.today() + timedelta(days=3)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Recorrente" in response.data
        assert f"até {last_date.strftime('%d/%m')}".encode() in response.data

    def test_excludes_screenings_with_only_past_dates(
        self, app, auth_headers, setup_cinemas
    ):
        _create_screening_with_future_date(
            app, title="Filme Antigo", slug="filme-antigo", days=-1
        )

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Filme Antigo" not in response.data

    def test_excludes_draft_screenings(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            movie = Movie(title="Rascunho", slug="rascunho", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=True
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() + timedelta(days=1),
                    time="20:00",
                )
            )
            db_session.commit()

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Rascunho" not in response.data

    def test_reminder_input_max_is_last_upcoming_date(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app, days=5)
        last_date = date.today() + timedelta(days=5)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert f'max="{last_date.isoformat()}"'.encode() in response.data
        assert screening_id is not None

    def test_shows_warning_when_no_image(self, app, auth_headers, setup_cinemas):
        _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert "Sem imagem disponível".encode() in response.data

    def test_shows_copyable_text(self, app, auth_headers, setup_cinemas):
        _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert "⏳ Duna\n\n".encode() in response.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_alerts.py -v`
Expected: FAIL — old route/template still renders `Alert`-based content, none of the new assertions match.

- [ ] **Step 3: Rewrite the route for the Pendentes branch**

Replace the top and `index()` of `flask_backend/routes/admin/alerts.py`:

```python
from math import ceil

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from flask_backend.models import ALERT_ACTIONS
from flask_backend.repository import alert_actions
from flask_backend.repository.screenings import get_screenings_with_upcoming_dates
from flask_backend.routes.auth import login_required
from flask_backend.service.screening_alerts import get_pending_rows

bp = Blueprint("admin_alerts", __name__)

STATUS_FILTERS = ("pending", *ALERT_ACTIONS, "all")


@bp.route("/admin/alerts")
@login_required
def index():
    """Admin alert review queue"""
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        abort(400)

    if page < 1 or limit < 1:
        abort(400)

    status = request.args.get("status", "pending")
    if status not in STATUS_FILTERS:
        abort(400)

    prev_page = page - 1 if page > 1 else None

    if status == "pending":
        screenings = get_screenings_with_upcoming_dates()
        latest_actions = alert_actions.get_latest_by_screening_ids(
            [screening.id for screening in screenings]
        )
        rows = get_pending_rows(screenings, latest_actions)
        qtt_alerts = len(rows)
        pages = ceil(qtt_alerts / limit) if qtt_alerts else 0
        offset = (page - 1) * limit
        return render_template(
            "alerts/admin/index.html",
            status=status,
            pending_rows=rows[offset : offset + limit],
            curr_page=page,
            prev_page=prev_page,
            next_page=page + 1 if page < pages else None,
            pages=pages,
            limit=limit,
            qtt_alerts=qtt_alerts,
        )

    actions, pages, qtt_alerts = alert_actions.get_paginated(
        None if status == "all" else status, page, limit
    )

    return render_template(
        "alerts/admin/index.html",
        status=status,
        actions=actions,
        curr_page=page,
        prev_page=prev_page,
        next_page=page + 1 if page < pages else None,
        pages=pages,
        limit=limit,
        qtt_alerts=qtt_alerts,
    )
```

Leave `mark_posted`/`dismiss` in place for now — Task 7 rewrites them.

- [ ] **Step 4: Rewrite the template**

Replace `flask_backend/templates/alerts/admin/index.html` in full:

```jinja
{% extends "base.html" %}
{% block title %}
    Alertas
{% endblock title %}
{% block header %}
    <div>
        <h1>Alertas</h1>
        <p>Sessões únicas e recorrentes detectadas na programação, prontas para postar nas redes sociais</p>
    </div>
{% endblock header %}
{% block content %}
    {% macro row_image(screening) %}
        {% if screening.image %}
            {# djlint:off #}
            <img loading="lazy"
                 src="{{ screening.image }}"
                 alt="{{ screening.image_alt or screening.movie.title }}"
                 class="img-fluid rounded"
                 style="max-width: 80px; max-height: 80px;">
            {# djlint:on #}
        {% else %}
            <span class="badge bg-warning text-dark">Sem imagem disponível</span>
        {% endif %}
    {% endmacro %}
    {% macro movie_link(movie) %}
        {% if movie.slug %}
            <a href="{{ url_for('movie.show', slug=movie.slug) }}" class="text-decoration-none">{{ movie.title }}</a>
        {% else %}
            {{ movie.title }}
        {% endif %}
    {% endmacro %}
    {% macro category_badge(row) %}
        {% if row.category == "unica" %}
            <span class="badge bg-info text-dark">Sessão única — {{ row.screening.cinema.name }}</span>
        {% else %}
            <span class="badge bg-primary">Recorrente — {{ row.screening.cinema.name }}</span>
        {% endif %}
    {% endmacro %}
    {% macro pending_actions(row, status, stacked=false) %}
        <div class="{% if stacked %}d-grid gap-2{% endif %}">
            <form method="post"
                  action="{{ url_for('admin_alerts.mark_posted', screening_id=row.screening.id) }}"
                  class="d-flex gap-1 align-items-center mb-1">
                <input type="hidden" name="status" value="{{ status }}">
                <input type="date"
                       name="remind_at"
                       class="form-control form-control-sm"
                       max="{{ row.last_upcoming_date.isoformat() }}"
                       aria-label="Lembrar em">
                <button type="submit" class="btn btn-outline-success {% if stacked %}w-100{% endif %}">
                    Marcar como postado
                </button>
            </form>
            <form method="post"
                  action="{{ url_for('admin_alerts.dismiss', screening_id=row.screening.id) }}"
                  class="d-flex gap-1 align-items-center">
                <input type="hidden" name="status" value="{{ status }}">
                <input type="date"
                       name="remind_at"
                       class="form-control form-control-sm"
                       max="{{ row.last_upcoming_date.isoformat() }}"
                       aria-label="Lembrar em">
                <button type="submit" class="btn btn-outline-danger {% if stacked %}w-100{% endif %}">
                    Descartar
                </button>
            </form>
        </div>
    {% endmacro %}
    <ul class="nav nav-tabs mb-3">
        {% for filter_status, label in [("pending", "Pendentes"), ("posted", "Postados"), ("dismissed", "Descartados"), ("all", "Todos")] %}
            <li class="nav-item">
                <a class="nav-link {% if status == filter_status %}active{% endif %}"
                   href="{{ url_for('admin_alerts.index', status=filter_status) }}">{{ label }}</a>
            </li>
        {% endfor %}
    </ul>
    {% if status == "pending" %}
        {% if pending_rows %}
            <div class="table-responsive d-none d-md-block">
                <table class="table table-striped align-middle">
                    <thead>
                        <tr>
                            <th>Regra</th>
                            <th>Filme</th>
                            <th>Imagem</th>
                            <th>Até quando</th>
                            <th>Texto sugerido</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in pending_rows %}
                            <tr>
                                <td>{{ category_badge(row) }}</td>
                                <td>{{ movie_link(row.screening.movie) }}</td>
                                <td>{{ row_image(row.screening) }}</td>
                                <td>
                                    {% if row.category == "recorrente" %}até {{ row.last_upcoming_date.strftime("%d/%m") }}{% endif %}
                                </td>
                                <td class="w-25">
                                    <div class="input-group input-group-sm">
                                        <textarea class="form-control" rows="5" readonly id="alert-text-{{ row.screening.id }}">{{ row.drafted_text }}</textarea>
                                        <button type="button"
                                                class="btn btn-outline-secondary"
                                                onclick="navigator.clipboard.writeText(document.getElementById('alert-text-{{ row.screening.id }}').value)">
                                            Copiar
                                        </button>
                                    </div>
                                </td>
                                <td>{{ pending_actions(row, status) }}</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            <div class="d-md-none">
                {% for row in pending_rows %}
                    <div class="card mb-3">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                {{ category_badge(row) }}
                                {% if row.category == "recorrente" %}
                                    <span class="text-muted small">até {{ row.last_upcoming_date.strftime("%d/%m") }}</span>
                                {% endif %}
                            </div>
                            <div class="d-flex align-items-center gap-2 mb-2">
                                <h6 class="card-title mb-0">{{ movie_link(row.screening.movie) }}</h6>
                                {{ row_image(row.screening) }}
                            </div>
                            <div class="input-group input-group-sm mb-3">
                                <textarea class="form-control" rows="5" readonly id="alert-text-mobile-{{ row.screening.id }}">{{ row.drafted_text }}</textarea>
                                <button type="button"
                                        class="btn btn-outline-secondary"
                                        onclick="navigator.clipboard.writeText(document.getElementById('alert-text-mobile-{{ row.screening.id }}').value)">
                                    Copiar
                                </button>
                            </div>
                            {{ pending_actions(row, status, stacked=true) }}
                        </div>
                    </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="text-center py-5">
                <h3>Nenhuma sessão pendente</h3>
                <p class="text-muted">Não há sessões únicas ou recorrentes aguardando revisão no momento.</p>
            </div>
        {% endif %}
    {% else %}
        {% if actions %}
            <div class="table-responsive">
                <table class="table table-striped align-middle">
                    <thead>
                        <tr>
                            <th>Ação</th>
                            <th>Filme</th>
                            <th>Cinema</th>
                            <th>Quando</th>
                            <th>Lembrete</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for action in actions %}
                            <tr>
                                <td>
                                    <span class="badge {% if action.action == "posted" %}bg-success{% else %}bg-secondary{% endif %}">
                                        {% if action.action == "posted" %}Postado{% else %}Descartado{% endif %}
                                    </span>
                                </td>
                                <td>{{ movie_link(action.screening.movie) }}</td>
                                <td>{{ action.screening.cinema.name }}</td>
                                <td>
                                    <time datetime="{{ action.created_at.isoformat() }}">{{ action.created_at.strftime("%d/%m/%Y %H:%M") }}</time>
                                </td>
                                <td>
                                    {% if action.remind_at %}
                                        <time datetime="{{ action.remind_at.isoformat() }}">{{ action.remind_at.strftime("%d/%m/%Y") }}</time>
                                    {% else %}
                                        —
                                    {% endif %}
                                </td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% else %}
            <div class="text-center py-5">
                <h3>Nenhum registro encontrado</h3>
            </div>
        {% endif %}
    {% endif %}
    {% if pages > 1 %}
        <nav aria-label="Navegação do admin">
            <ul class="pagination justify-content-center">
                {% if prev_page %}
                    <li class="page-item">
                        <a class="page-link"
                           href="{{ url_for('admin_alerts.index', page=prev_page, limit=limit, status=status) }}">Anterior</a>
                    </li>
                {% endif %}
                {% for page_num in range(1, pages + 1) %}
                    <li class="page-item {% if page_num == curr_page %}active{% endif %}">
                        <a class="page-link"
                           href="{{ url_for('admin_alerts.index', page=page_num, limit=limit, status=status) }}">{{ page_num }}</a>
                    </li>
                {% endfor %}
                {% if next_page %}
                    <li class="page-item">
                        <a class="page-link"
                           href="{{ url_for('admin_alerts.index', page=next_page, limit=limit, status=status) }}">Próximo</a>
                    </li>
                {% endif %}
            </ul>
        </nav>
    {% endif %}
{% endblock content %}
```

Note: `pending_actions` references `url_for('admin_alerts.mark_posted', screening_id=...)` and `.dismiss`, which Task 7 updates to accept `screening_id`. Until Task 7 runs, those two endpoints still take `alert_id` — this is fine within this task since none of Task 6's own tests submit those forms (they only assert the rendered `max="..."` attribute and text), but `url_for` will raise if the route's argument name doesn't match. Rename the URL rule's parameter in `mark_posted`/`dismiss` from `<int:alert_id>` to `<int:screening_id>` as part of this step too, without changing their bodies yet (the bodies still operate on the old `Alert`-based repository — Task 7 replaces that logic):

```python
@bp.route("/admin/alerts/<int:screening_id>/mark-posted", methods=("POST",))
@login_required
def mark_posted(screening_id):
    """Mark alert as posted"""
    if alerts.mark_posted(screening_id, user_id=g.user.id) is None:
        abort(404)
    flash("Alerta marcado como postado!", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )


@bp.route("/admin/alerts/<int:screening_id>/dismiss", methods=("POST",))
@login_required
def dismiss(screening_id):
    """Dismiss alert"""
    if alerts.dismiss(screening_id, user_id=g.user.id) is None:
        abort(404)
    flash("Alerta descartado.", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )
```

This still calls the old `flask_backend.repository.alerts` module by parameter name only (semantically wrong until Task 7, but syntactically valid — add back `from flask_backend.repository import alerts` to the imports for this intermediate state). Task 7 replaces both function bodies and this import.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_alerts.py -v`
Expected: PASS

- [ ] **Step 6: Run djlint on the template**

Run: `uv run djlint flask_backend/templates/alerts/admin/index.html --lint --profile=jinja`
Expected: no errors (fix any reported formatting issues, then re-run)

- [ ] **Step 7: Commit**

```bash
git add flask_backend/routes/admin/alerts.py flask_backend/templates/alerts/admin/index.html flask_backend/tests/test_routes/test_admin/test_admin_alerts.py
git commit -m "feat: cut over Pendentes tab to the live-computed view (#258)"
```

---

### Task 7: Mark posted / dismiss — screening-scoped actions with reminders

**Files:**
- Modify: `flask_backend/routes/admin/alerts.py`
- Test: `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py`

**Interfaces:**
- Consumes: `repository.alert_actions.create` (Task 1), `repository.screenings.get_screening_by_id` (existing).
- Produces: `POST /admin/alerts/<int:screening_id>/mark-posted`, `POST /admin/alerts/<int:screening_id>/dismiss`, each accepting an optional `remind_at` form field (`YYYY-MM-DD`).

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py`:

```python
class TestAdminAlertsMarkPosted:
    def test_requires_login(self, app, client, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = client.post(f"/admin/alerts/{screening_id}/mark-posted")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_nonexistent_screening_returns_404(self, auth_headers):
        response = auth_headers.post("/admin/alerts/99999/mark-posted")
        assert response.status_code == 404

    def test_records_action_without_reminder(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/mark-posted", follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            action = (
                db_session.query(AlertAction).filter_by(screening_id=screening_id).one()
            )
            assert action.action == "posted"
            assert action.remind_at is None
            assert action.created_by_user_id is not None

    def test_records_action_with_reminder(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app, days=10)
        remind_at = (date.today() + timedelta(days=5)).isoformat()

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/mark-posted",
            data={"remind_at": remind_at},
            follow_redirects=True,
        )
        assert response.status_code == 200

        with app.app_context():
            action = (
                db_session.query(AlertAction).filter_by(screening_id=screening_id).one()
            )
            assert action.remind_at == date.fromisoformat(remind_at)

    def test_invalid_reminder_format_returns_400(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/mark-posted",
            data={"remind_at": "not-a-date"},
        )
        assert response.status_code == 400

    def test_posted_screening_disappears_from_pending(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)

        auth_headers.post(f"/admin/alerts/{screening_id}/mark-posted")

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert b"Duna" not in response.data


class TestAdminAlertsDismiss:
    def test_requires_login(self, app, client, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = client.post(f"/admin/alerts/{screening_id}/dismiss")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_nonexistent_screening_returns_404(self, auth_headers):
        response = auth_headers.post("/admin/alerts/99999/dismiss")
        assert response.status_code == 404

    def test_records_action(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.post(
            f"/admin/alerts/{screening_id}/dismiss", follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            action = (
                db_session.query(AlertAction).filter_by(screening_id=screening_id).one()
            )
            assert action.action == "dismissed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_alerts.py::TestAdminAlertsMarkPosted flask_backend/tests/test_routes/test_admin/test_admin_alerts.py::TestAdminAlertsDismiss -v`
Expected: FAIL — the routes still call the old `alerts` repository, which won't find a matching `Alert.id` for a bare `screening_id` and always 404s; `AlertAction` rows are never created.

- [ ] **Step 3: Rewrite the action routes**

In `flask_backend/routes/admin/alerts.py`, replace the `from flask_backend.repository import alerts` import with:

```python
from datetime import date

from flask_backend.repository.screenings import get_screening_by_id
```

(keep the other imports from Task 6 as-is: `alert_actions`, `get_screenings_with_upcoming_dates`, `get_pending_rows`, `ALERT_ACTIONS`).

Add a small parsing helper and replace both route bodies:

```python
def _parse_remind_at(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        abort(400)


@bp.route("/admin/alerts/<int:screening_id>/mark-posted", methods=("POST",))
@login_required
def mark_posted(screening_id):
    """Mark a screening as posted, optionally with a reminder date."""
    remind_at = _parse_remind_at(request.form.get("remind_at"))
    if get_screening_by_id(screening_id) is None:
        abort(404)

    alert_actions.create(
        screening_id=screening_id,
        action="posted",
        remind_at=remind_at,
        created_by_user_id=g.user.id,
    )
    flash("Marcado como postado!", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )


@bp.route("/admin/alerts/<int:screening_id>/dismiss", methods=("POST",))
@login_required
def dismiss(screening_id):
    """Dismiss a screening, optionally with a reminder date."""
    remind_at = _parse_remind_at(request.form.get("remind_at"))
    if get_screening_by_id(screening_id) is None:
        abort(404)

    alert_actions.create(
        screening_id=screening_id,
        action="dismissed",
        remind_at=remind_at,
        created_by_user_id=g.user.id,
    )
    flash("Descartado.", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_alerts.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add flask_backend/routes/admin/alerts.py flask_backend/tests/test_routes/test_admin/test_admin_alerts.py
git commit -m "feat: mark screenings posted/dismissed with optional reminders (#258)"
```

---

### Task 8: Postados / Descartados / Todos history tabs

**Files:**
- Test: `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py`

The route (Task 6's `index()`) and template (Task 6's `{% else %}` branch) already handle the history tabs via `alert_actions.get_paginated`. This task is verification-only: prove the wiring works end-to-end with real data, including the reminder-date display.

**Interfaces:**
- Consumes: everything from Tasks 1 and 6 — no new production code.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py`:

```python
class TestAdminAlertsHistory:
    def test_posted_tab_shows_action(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        assert b"Postado" in response.data
        assert b"Duna" in response.data

    def test_dismissed_tab_shows_action(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="dismissed")

        response = auth_headers.get("/admin/alerts?status=dismissed")
        assert response.status_code == 200
        assert b"Descartado" in response.data

    def test_posted_tab_does_not_show_dismissed_actions(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="dismissed")

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        assert b"Descartado" not in response.data

    def test_all_tab_shows_both(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")
            alert_actions.create(screening_id=screening_id, action="dismissed")

        response = auth_headers.get("/admin/alerts?status=all")
        assert response.status_code == 200
        assert b"Postado" in response.data
        assert b"Descartado" in response.data

    def test_history_shows_reminder_date_when_set(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)
        remind_at = date.today() + timedelta(days=2)
        with app.app_context():
            alert_actions.create(
                screening_id=screening_id, action="posted", remind_at=remind_at
            )

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        assert remind_at.strftime("%d/%m/%Y").encode() in response.data

    def test_history_shows_dash_without_reminder(
        self, app, auth_headers, setup_cinemas
    ):
        screening_id = _create_screening_with_future_date(app)
        with app.app_context():
            alert_actions.create(screening_id=screening_id, action="posted")

        response = auth_headers.get("/admin/alerts?status=posted")
        assert response.status_code == 200
        assert "—".encode() in response.data
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_alerts.py::TestAdminAlertsHistory -v`
Expected: if any fail, it means Task 6's history branch has a bug — fix `index()` or the template's `{% else %}` block until all pass. If they already pass (likely, since Task 6 built this branch), that confirms the wiring is correct.

- [ ] **Step 3: Run the full suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add flask_backend/tests/test_routes/test_admin/test_admin_alerts.py
git commit -m "test: cover Postados/Descartados/Todos history tabs (#258)"
```

---

### Task 9: Removal sweep — delete the old Alert system

**Files:**
- Delete: `flask_backend/service/alert_rules.py`, `flask_backend/service/alert_pipeline.py`, `flask_backend/service/alert_text.py`, `flask_backend/repository/alerts.py`
- Delete: `flask_backend/tests/test_service/test_alert_rules.py`, `flask_backend/tests/test_service/test_alert_pipeline.py`, `flask_backend/tests/test_service/test_alert_text.py`
- Modify: `flask_backend/models.py`, `flask_backend/repository/movies.py`, `flask_backend/repository/screenings.py`, `flask_backend/service/movie_merge.py`, `flask_backend/commands.py`, `flask_backend/tests/conftest.py`
- Modify: `flask_backend/tests/test_service/test_delete_movie.py`, `flask_backend/tests/test_service/test_movie_merge.py` — these already exercise the old `Alert` cleanup/repoint behavior directly (found by grepping for `delete_for_movie`/`repoint_to_screening`/`repoint_to_movie` usage in tests during planning) and must be ported, not just left to fail.
- Create: `migrations/versions/20260724_000001_drop_alerts_table.py`

**Interfaces:**
- Nothing new produced. Everything this task removes was, by this point, only referenced by itself and the files listed above — verified by the greps run during planning (routes/admin/pipelines.py is handled separately in Task 10).

- [ ] **Step 1: Delete the old service and repository files**

```bash
git rm flask_backend/service/alert_rules.py flask_backend/service/alert_pipeline.py flask_backend/service/alert_text.py flask_backend/repository/alerts.py
git rm flask_backend/tests/test_service/test_alert_rules.py flask_backend/tests/test_service/test_alert_pipeline.py flask_backend/tests/test_service/test_alert_text.py
```

- [ ] **Step 2: Remove the `Alert` model, `ALERT_STATUSES`, and the two evaluated-at columns**

In `flask_backend/models.py`:
- Delete the line `ALERT_STATUSES = ["pending", "posted", "dismissed"]`.
- In `Movie`, delete the `metadata_alerts_evaluated_at` column and its preceding comment:
  ```python
      # Set once the alert pipeline's director/genre/collection rules have
      # been evaluated for this movie. NULL means "still due" - see
      # flask_backend/service/alert_pipeline.py.
      metadata_alerts_evaluated_at = Column(DateTime, nullable=True, index=True)
  ```
- In `Screening`, delete the `core_alerts_evaluated_at` column and its preceding comment:
  ```python
      # Set once the alert pipeline's core rules have been evaluated for this
      # screening. NULL means "still due" - see
      # flask_backend/service/alert_pipeline.py.
      core_alerts_evaluated_at = Column(DateTime, nullable=True, index=True)
  ```
- Delete the entire `Alert` class (from `class Alert(Base):` through `resolved_by: Mapped[Optional["User"]] = relationship()`), leaving `AlertAction` as the sole class in that region.

- [ ] **Step 3: Write the migration dropping `alerts` and the two columns**

Create `migrations/versions/20260724_000001_drop_alerts_table.py`:

```python
"""Removes the old alerts table and its generation-pipeline bookkeeping
columns (issue #258). The Alert model/pipeline is fully replaced by
alert_actions (added in 20260724_000000) plus the live-computed Pendentes
view - see docs/superpowers/specs/2026-07-24-admin-alerts-usability-design.md.

Revision ID: 20260724_000001
Revises: 20260724_000000
Create Date: 2026-07-24 00:00:01.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260724_000001"
down_revision: Union[str, None] = "20260724_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_alerts_pipeline_run_id", table_name="alerts")
    op.drop_index("ix_alerts_dedup_key", table_name="alerts")
    op.drop_index("ix_alerts_screening_id", table_name="alerts")
    op.drop_index("ix_alerts_movie_id", table_name="alerts")
    op.drop_index("ix_alerts_rule_name", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_screenings_core_alerts_evaluated_at", table_name="screenings")
    op.drop_column("screenings", "core_alerts_evaluated_at")

    op.drop_index("ix_movies_metadata_alerts_evaluated_at", table_name="movies")
    op.drop_column("movies", "metadata_alerts_evaluated_at")


def downgrade() -> None:
    op.add_column(
        "movies",
        sa.Column("metadata_alerts_evaluated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_movies_metadata_alerts_evaluated_at",
        "movies",
        ["metadata_alerts_evaluated_at"],
    )

    op.add_column(
        "screenings",
        sa.Column("core_alerts_evaluated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_screenings_core_alerts_evaluated_at",
        "screenings",
        ["core_alerts_evaluated_at"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_name", sa.String(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("screening_id", sa.Integer(), nullable=True),
        sa.Column("dedup_key", sa.String(), nullable=False),
        sa.Column("drafted_text", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["screening_id"], ["screenings.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_rule_name", "alerts", ["rule_name"])
    op.create_index("ix_alerts_movie_id", "alerts", ["movie_id"])
    op.create_index("ix_alerts_screening_id", "alerts", ["screening_id"])
    op.create_index("ix_alerts_dedup_key", "alerts", ["dedup_key"], unique=True)
    op.create_index("ix_alerts_pipeline_run_id", "alerts", ["pipeline_run_id"])
```

- [ ] **Step 4: Port `repository/movies.py` off the old `alerts` repository**

In `flask_backend/repository/movies.py`, replace the import block:

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

Replace `delete()`:

```python
def delete(movie: Movie) -> None:
    # delete all related screenings to maintain integrity
    for _scr in movie.screenings:
        db_session.query(PosterFetchAttempt).filter(
            PosterFetchAttempt.screening_id == _scr.id
        ).delete(synchronize_session=False)
        alert_actions.delete_for_screening(_scr.id)
        # delete all related dates
        for _dt in _scr.dates:
            db_session.delete(_dt)
        db_session.delete(_scr)
    db_session.query(MovieMetadataFetchAttempt).filter(
        MovieMetadataFetchAttempt.movie_id == movie.id
    ).delete(synchronize_session=False)
    db_session.delete(movie)
    db_session.commit()
```

Delete everything below it: `get_movies_due_for_metadata_alert_evaluation`, `_earlier_than`, `get_earlier_movies_with_director`, `get_earlier_movies_with_collection`, `get_earlier_genre_id_sets` — the whole rest of the file (their only caller, `alert_rules.py`, is gone).

- [ ] **Step 5: Port `repository/screenings.py` off the old `alerts` repository**

In `flask_backend/repository/screenings.py`, replace:

```python
from flask_backend.repository import alerts
```

with:

```python
from flask_backend.repository import alert_actions
```

Delete `get_screenings_due_for_core_alert_evaluation()` entirely.

Replace `delete()`:

```python
def delete(
    screening: Screening,
) -> None:
    # delete all related dates to maintain integrity
    for _date in screening.dates:
        db_session.delete(_date)
    alert_actions.delete_for_screening(screening.id)
    db_session.delete(screening)
    db_session.commit()
```

- [ ] **Step 6: Port `service/movie_merge.py` off the old `alerts` repository**

In `flask_backend/service/movie_merge.py`, replace:

```python
from flask_backend.repository import alerts
```

with:

```python
from flask_backend.repository import alert_actions
```

In `_merge_screenings`, replace `alerts.repoint_to_screening(screening.id, existing.id)` with `alert_actions.repoint_to_screening(screening.id, existing.id)`.

In `merge_movies`, delete the line `alerts.repoint_to_movie(duplicate.id, survivor.id)` — there is no equivalent: `alert_actions` rows are always reached via `screening_id`, and screenings already carry their history with them when they move to the survivor (via `survivor.screenings.append(screening)`) or get repointed in `_merge_screenings` above.

- [ ] **Step 7: Port `test_delete_movie.py` off `Alert`**

In `flask_backend/tests/test_service/test_delete_movie.py`, replace `Alert` with `AlertAction` in the `from flask_backend.models import (...)` block. Replace the `test_deletes_related_alerts` test (it creates one screening-scoped and one movie-scoped `Alert` — the new schema has no movie-scoped rows, `screening_id` is required):

```python
    def test_deletes_related_alert_actions(self, client, app, setup_cinemas):
        with client.application.app_context():
            movie = _create_movie("Filme", "filme")
            screening = _create_screening(
                movie, "capitolio", dates=[(date(2026, 1, 1), "20:00")]
            )
            db_session.add(
                AlertAction(
                    screening_id=screening.id,
                    action="posted",
                    created_at=datetime.now(),
                )
            )
            db_session.commit()
            movie_id = movie.id
            screening_id = screening.id

            deleted = delete_movie(movie_id, skip_confirmation=True)

            assert deleted is True
            assert (
                db_session.query(AlertAction)
                .filter_by(screening_id=screening_id)
                .count()
                == 0
            )
```

- [ ] **Step 8: Port `test_movie_merge.py` off `Alert`**

In `flask_backend/tests/test_service/test_movie_merge.py`, replace `Alert` with `AlertAction` in the `from flask_backend.models import (...)` block.

Delete `test_repoints_movie_scoped_alert_to_survivor` entirely — it tests `repoint_to_movie`, which Step 6 removed with no replacement (there are no movie-scoped `AlertAction` rows).

Replace `test_repoints_screening_scoped_alert_on_fold_in`:

```python
    def test_repoints_alert_action_on_screening_fold_in(
        self, client, app, setup_cinemas
    ):
        with client.application.app_context():
            survivor = _create_movie("Filme", "filme")
            duplicate = _create_movie("Cinema | Filme", "cinema-filme")
            survivor_screening = _create_screening(survivor, "capitolio")
            duplicate_screening = _create_screening(duplicate, "capitolio")
            db_session.add(
                AlertAction(
                    screening_id=duplicate_screening.id,
                    action="posted",
                    created_at=datetime.now(),
                )
            )
            db_session.commit()
            duplicate_screening_id = duplicate_screening.id

            merge_movies(survivor, [duplicate])
            db_session.commit()

            action = (
                db_session.query(AlertAction)
                .filter_by(screening_id=survivor_screening.id)
                .one()
            )
            assert action.screening_id != duplicate_screening_id
```

- [ ] **Step 9: Remove the `generate-alerts` CLI command**

In `flask_backend/commands.py`:
- Remove `app.cli.add_command(generate_alerts)` from `register_commands`.
- Delete the entire `generate_alerts` function and its `@click.command("generate-alerts")` decorator block (from `@click.command("generate-alerts")` through the final `click.echo(f"{'=' * 40}")` before `@click.command("delete-movie")`).

- [ ] **Step 10: Remove `Alert` from the test-DB cleanup fixture**

In `flask_backend/tests/conftest.py`, remove `Alert` from the `from flask_backend.models import (...)` block and delete the line `db_session.query(Alert).delete()` (keep `AlertAction` and its delete call, added in Task 1).

- [ ] **Step 11: Run the full suite**

Run: `pytest`
Expected: PASS except for `flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py`, which fails to collect (`routes/admin/pipelines.py` still imports `flask_backend.repository.alerts`, deleted in Step 1) — that's expected, Task 10 fixes it next.

- [ ] **Step 12: Commit**

```bash
git add -A flask_backend migrations
git commit -m "refactor: remove the old Alert model, rules, and pipeline (#258)"
```

---

### Task 10: Remove `generate-alerts` from the pipeline health dashboard

**Files:**
- Modify: `flask_backend/routes/admin/pipelines.py`, `flask_backend/templates/pipelines/admin/detail.html`, `flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py`
- Delete: `.github/workflows/generate-alerts.yml`

**Interfaces:** None — purely subtractive.

- [ ] **Step 1: Update the failing/obsolete pipeline tests**

In `flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py`:
- In `test_returns_404_when_pipeline_name_mismatches_run`, replace the mismatching URL from `f"/admin/pipelines/generate-alerts/{run_id}"` to `f"/admin/pipelines/fetch-movie-metadata/{run_id}"`.
- Delete the entire `test_shows_alerts_created_for_generate_alerts_run` test (it imports and creates an `Alert`, which no longer exists).

- [ ] **Step 2: Run tests to verify the expected failures**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py -v`
Expected: FAIL — `routes/admin/pipelines.py` still imports `flask_backend.repository.alerts`, which Task 9 deleted, so the whole module fails to import (collection error).

- [ ] **Step 3: Remove the `generate-alerts` group from `routes/admin/pipelines.py`**

Remove the import:

```python
from flask_backend.repository.alerts import get_by_pipeline_run_id as get_alerts_by_run
```

Remove this entry from `PIPELINE_GROUPS`:

```python
    {
        "pipeline_name": "generate-alerts",
        "source": None,
        "label": "Geração de Alertas",
    },
```

In `detail()`, remove the `alerts` local and its branch:

```python
    screenings, metadata_attempts, poster_attempts = [], [], []
    if pipeline_name == "import-json":
        screenings = get_screenings_by_run(run_id)
    elif pipeline_name == "fetch-movie-metadata":
        metadata_attempts = get_metadata_attempts_by_run(run_id)
    elif pipeline_name == "fetch-posters":
        poster_attempts = get_poster_attempts_by_run(run_id)

    return render_template(
        "pipelines/admin/detail.html",
        run=run,
        label=_group_label(run.pipeline_name, run.source),
        display_status=pipeline_runs.display_status(run),
        screenings=screenings,
        metadata_attempts=metadata_attempts,
        poster_attempts=poster_attempts,
    )
```

- [ ] **Step 4: Remove the `generate-alerts` branch from the detail template**

In `flask_backend/templates/pipelines/admin/detail.html`, delete:

```jinja
    {% elif run.pipeline_name == "generate-alerts" %}
        <h2>Alertas gerados ({{ alerts | length }})</h2>
        {% if alerts %}
            <ul>
                {% for alert in alerts %}<li>{{ alert.rule_name }} — {{ alert.movie.title }}</li>{% endfor %}
            </ul>
        {% else %}
            <p>Nenhum alerta gerado neste run.</p>
        {% endif %}
```

leaving the `{% elif run.pipeline_name == "fetch-posters" %}` block's `{% endif %}` as the block's closing tag.

- [ ] **Step 5: Delete the cron workflow**

```bash
git rm .github/workflows/generate-alerts.yml
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py -v`
Expected: PASS

- [ ] **Step 7: Run the full suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add flask_backend/routes/admin/pipelines.py flask_backend/templates/pipelines/admin/detail.html flask_backend/tests/test_routes/test_admin/test_admin_pipelines.py
git rm .github/workflows/generate-alerts.yml 2>/dev/null || true
git commit -m "chore: drop generate-alerts from the pipeline health dashboard (#258)"
```

---

### Task 11: Final verification

**Files:** None (verification only).

- [ ] **Step 1: Run the full test suite with coverage**

Run: `coverage run -m pytest && coverage report -m`
Expected: all tests pass; no coverage regressions in the files this plan touched.

- [ ] **Step 2: Lint and format**

Run:
```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```
Expected: clean (no remaining lint errors; formatting applied).

- [ ] **Step 3: Confirm no dangling references to the removed system**

Run:
```bash
grep -rn "alert_rules\|alert_pipeline\|alert_text\|repository.alerts\b\|generate-alerts\|generate_alerts\|ALERT_STATUSES\b" flask_backend .github --include=*.py --include=*.yml --include=*.html
```
Expected: no output (aside from this plan/spec's own doc files, which aren't covered by this grep's extensions).

- [ ] **Step 4: Re-run the full suite one last time**

Run: `pytest`
Expected: PASS

- [ ] **Step 5: Commit any formatting fixes**

```bash
git add -A
git commit -m "chore: lint and format after alerts redesign (#258)"
```

(Skip this step if `git status` shows nothing to commit.)
