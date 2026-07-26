# "Want to watch" Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let anonymous visitors on the reels mobile homepage mark a movie as "want to watch" with a tap, persisted server-side against a cookie-borne anonymous visitor identity, with a `/favoritos` page to review everything they've marked.

**Architecture:** A new `want_to_watch` table (movie_id + visitor_id, unique pair) backs a toggle endpoint and a repository module. Visitor identity is a dedicated, non-session `visitor_id` cookie, created lazily on first toggle. The existing reels-feed builder (`build_reels_feed`) gains a `wanted_movie_ids` param so homepage cards know their state; a new `build_favorites_feed` reuses it for `/favoritos` and falls back to a movie's last known screening when nothing upcoming remains. The reels card markup is extracted into a shared partial so both pages render identically, and a small star button (vanilla JS, optimistic UI) is added to it.

**Tech Stack:** Flask 3.0.3, SQLAlchemy, Alembic migrations, Jinja2 templates, vanilla JS/CSS (no frontend framework — matches the rest of the reels UI).

## Global Constraints

- Follow existing repository/route/service module patterns exactly — this codebase has no framework abstractions beyond plain SQLAlchemy queries in `flask_backend/repository/*.py`.
- No comments unless documenting genuinely non-obvious behavior (project convention, see `CLAUDE.md`).
- Run `uv run ruff check --fix`, `uv run ruff format`, `uv run djlint --reformat flask_backend/templates --format-css --format-js`, and `pytest` before considering any task done — CI fails on unformatted code.
- Never add an AI/agent co-author trailer to commits.
- Design spec: `docs/superpowers/specs/2026-07-26-want-to-watch-design.md` — every task below implements a specific section of it.

---

### Task 1: `WantToWatch` model, migration, and repository

**Files:**
- Modify: `flask_backend/models.py` (import + new class, inserted between `ScreeningDate` and `PipelineRun`)
- Modify: `flask_backend/tests/conftest.py` (`clean_db` fixture)
- Create: `migrations/versions/20260726_000000_add_want_to_watch.py`
- Create: `flask_backend/repository/want_to_watch.py`
- Test: `flask_backend/tests/test_repository/test_want_to_watch.py`

**Interfaces:**
- Produces: `flask_backend.models.WantToWatch` (columns: `id`, `movie_id`, `visitor_id`, `created_at`; unique on `(movie_id, visitor_id)`)
- Produces: `want_to_watch.toggle(movie_id: int, visitor_id: str) -> bool` — inserts/deletes the row, returns new state
- Produces: `want_to_watch.get_movie_ids_for_visitor(visitor_id: str) -> Set[int]`

- [ ] **Step 1: Write the failing repository test**

Create `flask_backend/tests/test_repository/test_want_to_watch.py`:

```python
from flask_backend.db import db_session
from flask_backend.models import Movie, WantToWatch
from flask_backend.repository.want_to_watch import (
    get_movie_ids_for_visitor,
    toggle,
)


def _movie(title="Test Movie"):
    movie = Movie(title=title, slug=title.lower().replace(" ", "-"))
    db_session.add(movie)
    db_session.commit()
    return movie.id


class TestToggle:
    def test_marks_a_movie_for_a_visitor(self, app):
        with app.app_context():
            movie_id = _movie()

            wanted = toggle(movie_id, "visitor-a")

            assert wanted is True
            assert (
                db_session.query(WantToWatch)
                .filter_by(movie_id=movie_id, visitor_id="visitor-a")
                .count()
                == 1
            )

    def test_toggling_twice_removes_the_mark(self, app):
        with app.app_context():
            movie_id = _movie()
            toggle(movie_id, "visitor-a")

            wanted = toggle(movie_id, "visitor-a")

            assert wanted is False
            assert (
                db_session.query(WantToWatch)
                .filter_by(movie_id=movie_id, visitor_id="visitor-a")
                .count()
                == 0
            )

    def test_marks_are_scoped_per_visitor(self, app):
        with app.app_context():
            movie_id = _movie()
            toggle(movie_id, "visitor-a")

            wanted_b = toggle(movie_id, "visitor-b")

            assert wanted_b is True
            assert (
                db_session.query(WantToWatch).filter_by(movie_id=movie_id).count() == 2
            )


class TestGetMovieIdsForVisitor:
    def test_returns_empty_set_for_unknown_visitor(self, app):
        with app.app_context():
            assert get_movie_ids_for_visitor("nobody") == set()

    def test_returns_marked_movie_ids(self, app):
        with app.app_context():
            movie_id_1 = _movie("Movie One")
            movie_id_2 = _movie("Movie Two")
            toggle(movie_id_1, "visitor-a")
            toggle(movie_id_2, "visitor-a")

            result = get_movie_ids_for_visitor("visitor-a")

            assert result == {movie_id_1, movie_id_2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_repository/test_want_to_watch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flask_backend.repository.want_to_watch'` (and `ImportError: cannot import name 'WantToWatch'`)

- [ ] **Step 3: Add the `WantToWatch` model**

In `flask_backend/models.py`, add `UniqueConstraint` to the existing `sqlalchemy` import:

```python
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
```

Insert this class between `ScreeningDate` and `PipelineRun`:

```python
class WantToWatch(Base):
    """One row per (movie, anonymous visitor) mark on the reels homepage's
    want-to-watch star. visitor_id is an opaque UUID from a dedicated
    cookie (flask_backend/utils/visitor.py) - not tied to Screening, so a
    mark survives across cinemas and past a specific showtime's dates."""

    __tablename__ = "want_to_watch"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    visitor_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (UniqueConstraint("movie_id", "visitor_id"),)

    movie: Mapped["Movie"] = relationship()
```

- [ ] **Step 4: Add the migration**

Create `migrations/versions/20260726_000000_add_want_to_watch.py`:

```python
"""Adds want_to_watch: the anonymous per-visitor "want to watch" mark on
the reels homepage star button - see
docs/superpowers/specs/2026-07-26-want-to-watch-design.md.

Revision ID: 20260726_000000
Revises: 20260724_000001
Create Date: 2026-07-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260726_000000"
down_revision: Union[str, None] = "20260724_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "want_to_watch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("visitor_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("movie_id", "visitor_id"),
    )
    op.create_index("ix_want_to_watch_movie_id", "want_to_watch", ["movie_id"])
    op.create_index("ix_want_to_watch_visitor_id", "want_to_watch", ["visitor_id"])


def downgrade() -> None:
    op.drop_index("ix_want_to_watch_visitor_id", table_name="want_to_watch")
    op.drop_index("ix_want_to_watch_movie_id", table_name="want_to_watch")
    op.drop_table("want_to_watch")
```

- [ ] **Step 5: Add the repository module**

Create `flask_backend/repository/want_to_watch.py`:

```python
from typing import Set

from flask_backend.db import db_session
from flask_backend.models import WantToWatch


def toggle(movie_id: int, visitor_id: str) -> bool:
    """Inserts or deletes the (movie_id, visitor_id) mark. Returns the new
    state: True if now marked, False if now unmarked."""
    existing = (
        db_session.query(WantToWatch)
        .filter(WantToWatch.movie_id == movie_id)
        .filter(WantToWatch.visitor_id == visitor_id)
        .first()
    )
    if existing:
        db_session.delete(existing)
        db_session.commit()
        return False
    db_session.add(WantToWatch(movie_id=movie_id, visitor_id=visitor_id))
    db_session.commit()
    return True


def get_movie_ids_for_visitor(visitor_id: str) -> Set[int]:
    rows = (
        db_session.query(WantToWatch.movie_id)
        .filter(WantToWatch.visitor_id == visitor_id)
        .all()
    )
    return {row[0] for row in rows}
```

- [ ] **Step 6: Update `clean_db` to clear the new table between tests**

In `flask_backend/tests/conftest.py`, add `WantToWatch` to the import list inside `clean_db`:

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
```

Add a delete call before `db_session.query(Movie).delete()` (it has a `movie_id` FK, so it must be cleared first):

```python
        db_session.query(ScreeningDate).delete()
        db_session.query(Screening).delete()
        db_session.query(WantToWatch).delete()
        db_session.query(Movie).delete()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_want_to_watch.py -v`
Expected: PASS (5 tests)

Run: `pytest flask_backend/tests` (full suite, confirm nothing else broke)
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add flask_backend/models.py flask_backend/tests/conftest.py \
  migrations/versions/20260726_000000_add_want_to_watch.py \
  flask_backend/repository/want_to_watch.py \
  flask_backend/tests/test_repository/test_want_to_watch.py
git commit -m "feat: add WantToWatch model, migration, and repository"
```

---

### Task 2: Visitor identity cookie + toggle route

**Files:**
- Create: `flask_backend/utils/visitor.py`
- Modify: `flask_backend/routes/screening.py` (new route + imports)
- Test: `flask_backend/tests/test_routes/test_screening.py` (new test class, appended)

**Interfaces:**
- Consumes: `want_to_watch.toggle(movie_id, visitor_id) -> bool` (Task 1), `repository.movies.get_by_id(movie_id) -> Optional[Movie]` (existing)
- Produces: `utils.visitor.VISITOR_COOKIE_NAME` (str constant, `"visitor_id"`), `utils.visitor.get_visitor_id(request) -> Optional[str]`, `utils.visitor.new_visitor_id() -> str`
- Produces route: `POST /movie/<int:movie_id>/want-to-watch` → `{"wanted": bool}` JSON, sets the `visitor_id` cookie

- [ ] **Step 1: Write the failing route test**

Add to `flask_backend/tests/test_routes/test_screening.py` (append at end of file; `Movie`, `Screening`, `db_session` are already imported at the top of this file):

```python
def _create_movie(title="Filme"):
    movie = Movie(title=title, slug=title.lower().replace(" ", "-"))
    db_session.add(movie)
    db_session.commit()
    return movie.id


class TestWantToWatchToggle:
    def test_first_toggle_marks_the_movie_and_sets_visitor_cookie(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            movie_id = _create_movie()

        response = client.post(f"/movie/{movie_id}/want-to-watch")

        assert response.status_code == 200
        assert response.get_json() == {"wanted": True}
        set_cookie_headers = response.headers.get_all("Set-Cookie")
        visitor_cookie = next(
            header for header in set_cookie_headers if header.startswith("visitor_id=")
        )
        assert "HttpOnly" in visitor_cookie

    def test_second_toggle_unmarks_using_the_same_visitor(self, client, setup_cinemas):
        with client.application.app_context():
            movie_id = _create_movie()

        first = client.post(f"/movie/{movie_id}/want-to-watch")
        second = client.post(f"/movie/{movie_id}/want-to-watch")

        assert first.get_json() == {"wanted": True}
        assert second.get_json() == {"wanted": False}

    def test_returns_404_for_unknown_movie(self, client, setup_cinemas):
        response = client.post("/movie/99999/want-to-watch")

        assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_routes/test_screening.py::TestWantToWatchToggle -v`
Expected: FAIL — 404 Not Found (route doesn't exist yet)

- [ ] **Step 3: Add the visitor cookie helper**

Create `flask_backend/utils/visitor.py`:

```python
import uuid
from typing import Optional

from flask import Request

VISITOR_COOKIE_NAME = "visitor_id"


def get_visitor_id(request: Request) -> Optional[str]:
    """Reads the visitor_id cookie without creating one - a visitor who
    has never tapped want-to-watch has no cookie and no marks."""
    return request.cookies.get(VISITOR_COOKIE_NAME)


def new_visitor_id() -> str:
    return uuid.uuid4().hex
```

- [ ] **Step 4: Add the toggle route**

In `flask_backend/routes/screening.py`, add to the imports:

```python
from flask_backend.env_config import SESSION_LIFETIME_DAYS
from flask_backend.repository.movies import get_by_id as get_movie_by_id
from flask_backend.repository.want_to_watch import toggle as toggle_want_to_watch
from flask_backend.utils.visitor import (
    VISITOR_COOKIE_NAME,
    get_visitor_id,
    new_visitor_id,
)
```

Add the route (after `describe_image`, at the end of the file):

```python
@bp.route("/movie/<int:movie_id>/want-to-watch", methods=("POST",))
def want_to_watch(movie_id):
    if request.method != "POST":
        abort(405)

    movie = get_movie_by_id(movie_id)
    if not movie:
        abort(404)

    visitor_id = get_visitor_id(request) or new_visitor_id()
    wanted = toggle_want_to_watch(movie_id, visitor_id)

    response = jsonify({"wanted": wanted})
    response.set_cookie(
        VISITOR_COOKIE_NAME,
        visitor_id,
        max_age=SESSION_LIFETIME_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
    )
    return response
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py::TestWantToWatchToggle -v`
Expected: PASS (3 tests)

Run: `pytest flask_backend/tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add flask_backend/utils/visitor.py flask_backend/routes/screening.py \
  flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: add anonymous visitor cookie and want-to-watch toggle route"
```

---

### Task 3: `build_reels_feed` wanted flag + wire into the homepage

**Files:**
- Modify: `flask_backend/service/screening.py` (`build_reels_feed` signature + card dict)
- Modify: `flask_backend/routes/screening.py` (`_mobile_index`)
- Modify: `flask_backend/templates/screening/index_mobile.html` (data attributes on the card section)
- Test: `flask_backend/tests/test_service/test_screening.py` (new tests in `TestBuildReelsFeed`)
- Test: `flask_backend/tests/test_routes/test_screening.py` (new test class)

**Interfaces:**
- Consumes: `want_to_watch.get_movie_ids_for_visitor(visitor_id) -> Set[int]` (Task 1), `utils.visitor.get_visitor_id(request)` (Task 2)
- Produces: `build_reels_feed(..., wanted_movie_ids: Optional[Set[int]] = None)` — each card gains `card["movie_id"]` (int) and `card["wanted"]` (bool), consumed by `build_favorites_feed` in Task 4 and the button markup in Task 6

- [ ] **Step 1: Write the failing service tests**

Add to `flask_backend/tests/test_service/test_screening.py`, inside `class TestBuildReelsFeed` (after the existing tests, before the class ends):

```python
    def test_marks_card_as_wanted_when_its_movie_id_is_in_the_set(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )

        cards = build_reels_feed(
            [screening],
            [],
            today,
            today + timedelta(days=6),
            False,
            wanted_movie_ids={1},
        )

        assert cards[0]["wanted"] is True
        assert cards[0]["movie_id"] == 1

    def test_card_not_wanted_when_its_movie_id_is_not_in_the_set(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )

        cards = build_reels_feed(
            [screening],
            [],
            today,
            today + timedelta(days=6),
            False,
            wanted_movie_ids={999},
        )

        assert cards[0]["wanted"] is False

    def test_defaults_to_not_wanted_when_no_set_given(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )

        cards = build_reels_feed([screening], [], today, today + timedelta(days=6), False)

        assert cards[0]["wanted"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_screening.py::TestBuildReelsFeed -v`
Expected: FAIL — `TypeError: build_reels_feed() got an unexpected keyword argument 'wanted_movie_ids'`

- [ ] **Step 3: Update `build_reels_feed`**

In `flask_backend/service/screening.py`, add `Set` to the `typing` import:

```python
from typing import Dict, List, Optional, Set, Tuple
```

Change the signature and body (replace the existing function):

```python
def build_reels_feed(
    screenings: List[Screening],
    movie_dates: List[ScreeningDate],
    today: date,
    window_end: date,
    user_logged_in: bool,
    earliest_datetime: Optional[datetime] = None,
    wanted_movie_ids: Optional[Set[int]] = None,
) -> List[dict]:
    """Builds the mobile reels feed: one card per non-draft screening (all
    screenings if user_logged_in), sorted by each screening's soonest
    future ScreeningDate within [today, window_end]. `movie_dates` is the
    flat, cross-cinema list of ScreeningDate rows for every movie present in
    `screenings` within the same window - grouped here per movie for each
    card's "next dates" list. `wanted_movie_ids` marks cards for the
    current anonymous visitor's want-to-watch picks (see
    docs/superpowers/specs/2026-07-26-want-to-watch-design.md)."""
    if earliest_datetime is None:
        earliest_datetime = datetime.combine(today, time.min)
    if wanted_movie_ids is None:
        wanted_movie_ids = set()

    dates_by_movie: Dict[int, List[ScreeningDate]] = defaultdict(list)
    for screening_date in movie_dates:
        if is_screening_date_upcoming(screening_date, earliest_datetime):
            dates_by_movie[screening_date.screening.movie_id].append(screening_date)

    cards = []
    for screening in screenings:
        if screening.draft and not user_logged_in:
            continue
        future_dates = [
            d
            for d in screening.dates
            if today <= d.date <= window_end
            and is_screening_date_upcoming(d, earliest_datetime)
        ]
        if not future_dates:
            continue
        soonest = min(future_dates, key=lambda d: (d.date, d.time or ""))
        next_dates = sorted(
            dates_by_movie.get(screening.movie_id, []),
            key=lambda d: (d.date, d.time or ""),
        )
        cards.append(
            {
                "screening_id": screening.id,
                "movie_id": screening.movie_id,
                "movie_title": screening.movie.title,
                "directors": [director.name for director in screening.movie.directors],
                "release_year": screening.movie.release_year,
                "description": screening.description,
                "image": screening.image,
                "image_alt": screening.image_alt,
                "cinema_name": screening.cinema.short_name,
                "cinema_color": screening.cinema.color,
                "soonest_date": soonest.date,
                "soonest_time": soonest.time,
                "next_dates": [
                    {
                        "date": screening_date.date,
                        "time": screening_date.time,
                        "cinema_name": screening_date.screening.cinema.short_name,
                    }
                    for screening_date in next_dates
                ],
                "draft": screening.draft,
                "screening_url": screening.url,
                "wanted": screening.movie_id in wanted_movie_ids,
            }
        )

    cards.sort(key=lambda card: (card["soonest_date"], card["soonest_time"] or ""))

    for card in cards:
        card["day_label"] = format_day_label(card["soonest_date"], today)

    return cards
```

- [ ] **Step 4: Run service tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening.py::TestBuildReelsFeed -v`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 5: Write the failing route test for homepage wiring**

Add to `flask_backend/tests/test_routes/test_screening.py` (append at end):

```python
class TestReelsWantToWatchState:
    def test_homepage_marks_card_as_wanted_for_matching_visitor(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Querido",
                screening_date=date.today() + timedelta(days=1),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)

        assert f'data-movie-id="{movie_id}"' in html
        assert 'data-wanted="true"' in html

    def test_homepage_card_not_wanted_without_a_visitor_cookie(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Qualquer",
                screening_date=date.today() + timedelta(days=1),
            )

        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)

        assert 'data-wanted="true"' not in html
```

- [ ] **Step 6: Run to verify it fails**

Run: `pytest flask_backend/tests/test_routes/test_screening.py::TestReelsWantToWatchState -v`
Expected: FAIL — `data-movie-id` not found in rendered HTML

- [ ] **Step 7: Wire the visitor cookie into `_mobile_index`**

In `flask_backend/routes/screening.py`, add to imports:

```python
from flask_backend.repository.want_to_watch import (
    get_movie_ids_for_visitor,
    toggle as toggle_want_to_watch,
)
```

(This replaces the single-name import added in Task 2 — merge both names into one `from flask_backend.repository.want_to_watch import (...)` block.)

Update `_mobile_index`:

```python
def _mobile_index():
    now = datetime.now()
    today = now.date()
    window_end = today + timedelta(days=6)
    user_logged_in = g.user is not None

    screenings = get_screenings_in_date_range(today, window_end)
    movie_ids = list({screening.movie_id for screening in screenings})
    movie_dates = get_screening_dates_for_movies(
        movie_ids, today, window_end, include_drafts=user_logged_in
    )
    visitor_id = get_visitor_id(request)
    wanted_movie_ids = get_movie_ids_for_visitor(visitor_id) if visitor_id else set()
    cards = build_reels_feed(
        screenings,
        movie_dates,
        today,
        window_end,
        user_logged_in,
        earliest_datetime=now,
        wanted_movie_ids=wanted_movie_ids,
    )

    return render_template("screening/index_mobile.html", cards=cards)
```

- [ ] **Step 8: Add the data attributes to the template**

In `flask_backend/templates/screening/index_mobile.html`, line 13, replace:

```html
                <section class="reels-card">
```

with:

```html
                <section class="reels-card"
                         data-movie-id="{{ card.movie_id }}"
                         data-wanted="{{ 'true' if card.wanted else 'false' }}">
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS

Run: `pytest flask_backend/tests`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add flask_backend/service/screening.py flask_backend/routes/screening.py \
  flask_backend/templates/screening/index_mobile.html \
  flask_backend/tests/test_service/test_screening.py \
  flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: mark reels cards as wanted for the current visitor"
```

---

### Task 4: Favorites feed — repository queries + service function

**Files:**
- Modify: `flask_backend/repository/screenings.py` (two new query functions)
- Modify: `flask_backend/service/screening.py` (`build_favorites_feed`)
- Test: `flask_backend/tests/test_repository/test_screenings.py` (appended)
- Test: `flask_backend/tests/test_service/test_screening.py` (appended)

**Interfaces:**
- Consumes: `build_reels_feed(...)` (Task 3), `get_screening_dates_for_movies(...)` (existing)
- Produces: `screenings.get_screenings_for_movies_with_dates_in_range(movie_ids, start_date, end_date) -> List[Screening]`
- Produces: `screenings.get_latest_screening_for_movie(movie_id) -> Optional[Screening]`
- Produces: `service.screening.build_favorites_feed(movie_ids: List[int], today: date, user_logged_in: bool, now: Optional[datetime] = None) -> List[dict]` — cards carry `wanted=True`, plus `no_sessions: bool` (True when built from the stale fallback, with `soonest_date`/`soonest_time`/`next_dates`/`day_label` all `None`/`[]`)

- [ ] **Step 1: Write the failing repository tests**

Add to `flask_backend/tests/test_repository/test_screenings.py`, add to the existing import from `flask_backend.repository.screenings`:

```python
from flask_backend.repository.screenings import (
    get_latest_screening_for_movie,
    get_screening_dates_for_movies,
    get_screenings_for_movies_with_dates_in_range,
    get_screenings_in_date_range,
    get_screenings_with_upcoming_dates,
)
```

Append at the end of the file:

```python
class TestGetScreeningsForMoviesWithDatesInRange:
    def test_includes_screening_for_requested_movie_within_range(
        self, app, setup_cinemas
    ):
        screening_id, movie_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_for_movies_with_dates_in_range(
                    [movie_id], date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_excludes_screening_for_a_different_movie(self, app, setup_cinemas):
        _, movie_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=1)]
        )
        other_screening_id, _ = _create_screening(
            app, "Outro Filme", "outro-filme", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_for_movies_with_dates_in_range(
                    [movie_id], date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert other_screening_id not in ids

    def test_returns_empty_list_for_no_movie_ids(self, app, setup_cinemas):
        with app.app_context():
            result = get_screenings_for_movies_with_dates_in_range(
                [], date.today(), date.today()
            )
            assert result == []


class TestGetLatestScreeningForMovie:
    def test_returns_the_most_recently_created_screening(self, app, setup_cinemas):
        with app.app_context():
            movie = Movie(title="Filme", slug="filme", created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            cinema = get_cinema_by_slug("capitolio")
            older = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="antiga",
                created_at=datetime.now() - timedelta(days=10),
            )
            newer = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="recente",
                created_at=datetime.now(),
            )
            db_session.add_all([older, newer])
            db_session.commit()

            latest = get_latest_screening_for_movie(movie.id)

            assert latest.id == newer.id

    def test_returns_none_for_movie_without_screenings(self, app, setup_cinemas):
        with app.app_context():
            movie = Movie(
                title="Sem Sessão", slug="sem-sessao", created_at=datetime.now()
            )
            db_session.add(movie)
            db_session.commit()

            assert get_latest_screening_for_movie(movie.id) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_screenings_for_movies_with_dates_in_range'`

- [ ] **Step 3: Add the repository functions**

In `flask_backend/repository/screenings.py`, add after `get_screenings_in_date_range`:

```python
def get_screenings_for_movies_with_dates_in_range(
    movie_ids: List[int], start_date: date, end_date: date
) -> List[Screening]:
    """Screenings (draft included) for the given movie IDs with at least
    one ScreeningDate between start_date and end_date, inclusive. Powers
    the /favoritos feed - the caller decides whether to keep drafts based
    on login state, same as get_screenings_in_date_range."""
    if not movie_ids:
        return []
    return (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(Screening.movie_id.in_(movie_ids))
        .filter(func.date(ScreeningDate.date).between(start_date, end_date))
        .distinct()
        .all()
    )
```

Add after `get_screenings_with_upcoming_dates`:

```python
def get_latest_screening_for_movie(movie_id: int) -> Optional[Screening]:
    """Most recently created Screening row for a movie, regardless of its
    dates. Used as a fallback source of poster/description/cinema data on
    /favoritos for a marked movie with no upcoming session."""
    return (
        db_session.query(Screening)
        .filter(Screening.movie_id == movie_id)
        .order_by(Screening.created_at.desc())
        .first()
    )
```

- [ ] **Step 4: Run repository tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing service tests**

Add to the top imports of `flask_backend/tests/test_service/test_screening.py`:

```python
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.service.screening import (
    build_favorites_feed,
    build_reels_feed,
    download_image_from_url,
    format_day_label,
    get_image_metadata,
    get_img_filename_from_url,
    get_img_path_from_filename,
    get_soonest_date_in_range,
    import_scrapped_results,
    save_image,
    validate_image,
)
```

Append at the end of the file:

```python
class TestBuildFavoritesFeed:
    def test_returns_empty_list_for_no_movie_ids(self, app):
        with app.app_context():
            assert build_favorites_feed([], date.today(), False) == []

    def test_includes_card_for_movie_with_upcoming_screening(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            movie = Movie(title="Filme Futuro", slug="filme-futuro")
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() + timedelta(days=2),
                    time="20:00",
                )
            )
            db_session.commit()

            cards = build_favorites_feed([movie.id], date.today(), False)

            assert len(cards) == 1
            assert cards[0]["movie_title"] == "Filme Futuro"
            assert cards[0]["no_sessions"] is False
            assert cards[0]["wanted"] is True

    def test_falls_back_to_latest_screening_when_no_upcoming_dates(
        self, app, setup_cinemas
    ):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            movie = Movie(title="Filme Antigo", slug="filme-antigo")
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                image="poster.jpg",
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() - timedelta(days=10),
                    time="20:00",
                )
            )
            db_session.commit()

            cards = build_favorites_feed([movie.id], date.today(), False)

            assert len(cards) == 1
            assert cards[0]["movie_title"] == "Filme Antigo"
            assert cards[0]["no_sessions"] is True
            assert cards[0]["soonest_date"] is None
            assert cards[0]["image"] == "poster.jpg"

    def test_excludes_draft_fallback_when_not_logged_in(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            movie = Movie(title="Filme Rascunho", slug="filme-rascunho")
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=True
            )
            db_session.add(screening)
            db_session.commit()
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id,
                    date=date.today() - timedelta(days=10),
                    time="20:00",
                )
            )
            db_session.commit()

            cards = build_favorites_feed([movie.id], date.today(), False)

            assert cards == []
```

- [ ] **Step 6: Run to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_screening.py::TestBuildFavoritesFeed -v`
Expected: FAIL — `ImportError: cannot import name 'build_favorites_feed'`

- [ ] **Step 7: Add `build_favorites_feed`**

In `flask_backend/service/screening.py`, add to the repository import from `flask_backend.repository.screenings`:

```python
from flask_backend.repository.screenings import (
    create as create_screening,
    get_by_movie_id_and_cinema_id as get_screening_by_movie_id_and_cinema_id,
    get_latest_screening_for_movie,
    get_screening_dates_for_movies,
    get_screenings_for_movies_with_dates_in_range,
    update_screening_dates,
    update_title_cleaning_info,
)
```

Add after `build_reels_feed`:

```python
_FAR_FUTURE_DATE = date(9999, 12, 31)


def build_favorites_feed(
    movie_ids: List[int],
    today: date,
    user_logged_in: bool,
    now: Optional[datetime] = None,
) -> List[dict]:
    """Builds the /favoritos feed: every marked movie, sorted the same way
    as the reels feed. A marked movie with an upcoming ScreeningDate gets a
    normal reels card (any future date, unlike the homepage's 7-day
    window - this is a personal list, not a "what's on this week" feed). A
    marked movie with none falls back to its most recent past Screening
    (there's always at least one, since a Movie row only exists because
    some Screening created it), with no_sessions=True and no dates. A
    fallback whose screening is a draft is skipped entirely when not
    logged in, same as everywhere else drafts are visitor-hidden."""
    if not movie_ids:
        return []
    if now is None:
        now = datetime.now()

    screenings = get_screenings_for_movies_with_dates_in_range(
        movie_ids, today, _FAR_FUTURE_DATE
    )
    movie_dates = get_screening_dates_for_movies(
        movie_ids, today, _FAR_FUTURE_DATE, include_drafts=user_logged_in
    )
    cards = build_reels_feed(
        screenings,
        movie_dates,
        today,
        _FAR_FUTURE_DATE,
        user_logged_in,
        earliest_datetime=now,
        wanted_movie_ids=set(movie_ids),
    )
    for card in cards:
        card["no_sessions"] = False

    covered_movie_ids = {card["movie_id"] for card in cards}
    for movie_id in movie_ids:
        if movie_id in covered_movie_ids:
            continue
        stale_screening = get_latest_screening_for_movie(movie_id)
        if stale_screening is None:
            continue
        if stale_screening.draft and not user_logged_in:
            continue
        cards.append(
            {
                "screening_id": stale_screening.id,
                "movie_id": stale_screening.movie_id,
                "movie_title": stale_screening.movie.title,
                "directors": [
                    director.name for director in stale_screening.movie.directors
                ],
                "release_year": stale_screening.movie.release_year,
                "description": stale_screening.description,
                "image": stale_screening.image,
                "image_alt": stale_screening.image_alt,
                "cinema_name": stale_screening.cinema.short_name,
                "cinema_color": stale_screening.cinema.color,
                "soonest_date": None,
                "soonest_time": None,
                "next_dates": [],
                "draft": stale_screening.draft,
                "screening_url": stale_screening.url,
                "day_label": None,
                "no_sessions": True,
                "wanted": True,
            }
        )

    return cards
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening.py -v`
Expected: PASS

Run: `pytest flask_backend/tests`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/service/screening.py \
  flask_backend/tests/test_repository/test_screenings.py \
  flask_backend/tests/test_service/test_screening.py
git commit -m "feat: build the /favoritos feed with a stale-pick fallback"
```

---

### Task 5: `/favoritos` route + shared reels card partial

**Files:**
- Create: `flask_backend/templates/screening/_reels_card.html`
- Modify: `flask_backend/templates/screening/index_mobile.html` (use the partial)
- Create: `flask_backend/templates/screening/favoritos.html`
- Modify: `flask_backend/routes/screening.py` (`GET /favoritos`)
- Test: `flask_backend/tests/test_routes/test_screening.py` (new test class)

**Interfaces:**
- Consumes: `build_favorites_feed(movie_ids, today, user_logged_in)` (Task 4), `get_movie_ids_for_visitor(visitor_id)` (Task 1), `get_visitor_id(request)` (Task 2)
- Produces route: `GET /favoritos` → `screening/favoritos.html`, named `screening.favoritos` (used by the nav link in Task 6)

- [ ] **Step 1: Extract the shared card partial**

Create `flask_backend/templates/screening/_reels_card.html` with the full `<section class="reels-card" ...> ... </section>` block currently inside the `{% for card in cards %}` loop in `flask_backend/templates/screening/index_mobile.html` (including the `data-movie-id`/`data-wanted` attributes added in Task 3, so the opening tag now spans 3 lines instead of 1 — everything from `<section class="reels-card"` down through its matching `</section>`):

```html
<section class="reels-card"
         data-movie-id="{{ card.movie_id }}"
         data-wanted="{{ 'true' if card.wanted else 'false' }}">
    <p class="reels-day-label">{{ card.day_label }}</p>
    <div class="reels-card-panels">
        <div class="reels-panel reels-panel-poster">
            {% if card.image %}
                {# djlint:off H006 #}
                {% if loop.index0 < 2 %}
                    <img class="reels-poster-img"
                         src="{{ card.image }}"
                         alt="{{ card.image_alt or card.movie_title }}" />
                {% else %}
                    <img class="reels-poster-img"
                         data-src="{{ card.image }}"
                         alt="{{ card.image_alt or card.movie_title }}" />
                {% endif %}
                {# djlint:on #}
            {% else %}
                <div class="reels-poster-placeholder"
                     style="background-color: {{ card.cinema_color }}">
                    <span>{{ card.movie_title }}</span>
                </div>
            {% endif %}
            <div class="reels-overlay">
                <span class="badge rounded-pill"
                      style="background-color: {{ card.cinema_color }}">{{ card.cinema_name }}</span>
                <h2>{{ card.movie_title }}</h2>
                <p>
                    {% if card.soonest_time %}{{ card.soonest_time }}{% endif %}
                    {% if card.directors %}· {{ card.directors|join(", ") }}{% endif %}
                    {% if card.release_year %}· {{ card.release_year }}{% endif %}
                </p>
                {% if card.draft %}<span class="badge text-bg-warning">Rascunho</span>{% endif %}
            </div>
            <span class="reels-swipe-hint" aria-hidden="true">›</span>
        </div>
        <div class="reels-panel reels-panel-info">
            <div class="reels-info-header">
                <h2 class="reels-info-title">{{ card.movie_title }}</h2>
                <p class="reels-info-meta">
                    {% if card.directors %}{{ card.directors|join(", ") }}{% endif %}
                    {% if card.release_year %}
                        {% if card.directors %}·{% endif %}
                        {{ card.release_year }}
                    {% endif %}
                    {% if card.cinema_name %}· {{ card.cinema_name }}{% endif %}
                </p>
            </div>
            <p class="reels-description">{{ card.description }}</p>
            {% if card.next_dates %}
                <h3 class="h6">Próximas sessões</h3>
                <ul class="list-unstyled">
                    {% for next_date in card.next_dates %}
                        <li>
                            <span class="reels-session-dot"
                                  style="background-color: {{ card.cinema_color }}"></span>
                            {{ next_date.date.strftime("%d/%m") }} · {{ next_date.cinema_name }}
                            {% if next_date.time %}· {{ next_date.time }}{% endif %}
                        </li>
                    {% endfor %}
                </ul>
            {% elif card.no_sessions %}
                <p class="reels-no-sessions">Não há sessões previstas no momento.</p>
            {% endif %}
            {% if card.screening_url %}
                <p class="reels-utility-links">
                    <a href="{{ card.screening_url }}">Veja a postagem original</a>
                </p>
            {% endif %}
            <p class="reels-utility-links">
                {% if g.user %}
                    <a href="{{ url_for('screening.update', id=card.screening_id) }}">Edite!</a>
                {% else %}
                    <a href="{{ url_for('screening.update', id=card.screening_id) }}">Achou um erro? Ajude a corrigir!</a>
                {% endif %}
            </p>
            {% if card.draft %}
                <p>
                    <button class="badge text-bg-warning"
                            data-function="publish"
                            data-screening-id="{{ card.screening_id }}">Publicar</button>
                    <button class="badge text-bg-danger"
                            data-function="delete"
                            data-screening-id="{{ card.screening_id }}">Descartar</button>
                </p>
            {% endif %}
        </div>
    </div>
</section>
```

(The only content change versus the original block is the added `{% elif card.no_sessions %}` branch for the stale-pick message — everything else is a verbatim move.)

- [ ] **Step 2: Use the partial from `index_mobile.html`**

In `flask_backend/templates/screening/index_mobile.html`, replace the entire `<section class="reels-card" ...>...</section>` block moved in Step 1 (from its opening `<section class="reels-card"` tag through the matching `</section>`) with:

```html
                {% include "screening/_reels_card.html" %}
```

The surrounding `{% for card in cards %}` / `{% endfor %}` loop and the `{% else %}` empty-state branch stay in `index_mobile.html` unchanged.

- [ ] **Step 3: Write the failing route test**

Add to `flask_backend/tests/test_routes/test_screening.py` (append at end):

```python
class TestFavoritos:
    def test_returns_200(self, client, setup_cinemas):
        response = client.get("/favoritos")

        assert response.status_code == 200

    def test_shows_empty_state_without_a_visitor_cookie(self, client, setup_cinemas):
        response = client.get("/favoritos")

        assert "ainda não marcou" in response.get_data(as_text=True)

    def test_shows_marked_movie_with_upcoming_screening(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Futuro",
                screening_date=date.today() + timedelta(days=2),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")

        assert b"Filme Futuro" in response.data

    def test_shows_marked_movie_with_no_upcoming_screening_as_stale(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Antigo",
                screening_date=date.today() - timedelta(days=30),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert "Filme Antigo" in html
        assert "Não há sessões previstas no momento" in html
```

- [ ] **Step 4: Run to verify it fails**

Run: `pytest flask_backend/tests/test_routes/test_screening.py::TestFavoritos -v`
Expected: FAIL — 404 Not Found (route doesn't exist yet)

- [ ] **Step 5: Add the `/favoritos` route and template**

In `flask_backend/routes/screening.py`, add to the `flask_backend.service.screening` import:

```python
from flask_backend.service.screening import (
    build_dates,
    build_favorites_feed,
    build_reels_feed,
    save_image,
    validate_image,
)
```

Add the route (after `want_to_watch`, at the end of the file):

```python
@bp.route("/favoritos")
def favoritos():
    visitor_id = get_visitor_id(request)
    movie_ids = list(get_movie_ids_for_visitor(visitor_id)) if visitor_id else []
    user_logged_in = g.user is not None
    cards = build_favorites_feed(movie_ids, date.today(), user_logged_in)
    return render_template("screening/favoritos.html", cards=cards)
```

Create `flask_backend/templates/screening/favoritos.html`:

```html
{% extends "base_reels.html" %}
{% block title %}
    Meus Filmes
{% endblock title %}
{% block meta_tags %}
    <meta name="description"
          content="Filmes que você marcou como &quot;quero assistir&quot; no cinemaempoa.">
{% endblock meta_tags %}
{% block content %}
    <div class="reels-feed">
        {% if cards %}
            {% for card in cards %}
                {% include "screening/_reels_card.html" %}
            {% endfor %}
        {% else %}
            <section class="reels-card reels-empty">
                <strong>Você ainda não marcou nenhum filme. Toque na estrela em um filme para adicioná-lo aqui.</strong>
            </section>
        {% endif %}
    </div>
{% endblock content %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS

Run: `pytest flask_backend/tests`
Expected: PASS

Run: `uv run djlint flask_backend/templates --lint --profile=jinja`
Expected: no new errors on the three touched/created template files

- [ ] **Step 7: Commit**

```bash
git add flask_backend/templates/screening/_reels_card.html \
  flask_backend/templates/screening/index_mobile.html \
  flask_backend/templates/screening/favoritos.html \
  flask_backend/routes/screening.py \
  flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: add /favoritos page and extract shared reels card partial"
```

---

### Task 6: Want-to-watch star button (CSS + JS + markup) and nav link

**Files:**
- Modify: `flask_backend/templates/screening/_reels_card.html` (button markup)
- Modify: `flask_backend/static/css/reels.css` (button + animation styles)
- Create: `flask_backend/static/reels-want-to-watch.js`
- Modify: `flask_backend/templates/base_reels.html` (load the script, add nav link)

**Interfaces:**
- Consumes: `POST /movie/<id>/want-to-watch` (Task 2), `card.movie_id` / `card.wanted` (Task 3/4), route name `screening.favoritos` (Task 5)
- No new Python interfaces — this task is markup/CSS/JS only, verified manually per project convention (`CLAUDE.md`: "For UI or frontend changes... test in browser before reporting complete").

- [ ] **Step 1: Add the button markup**

In `flask_backend/templates/screening/_reels_card.html`, inside `<div class="reels-panel reels-panel-poster">`, immediately before the `<div class="reels-overlay">` line, add:

```html
            <button type="button"
                    class="reels-want-to-watch"
                    data-function="want-to-watch"
                    data-movie-id="{{ card.movie_id }}"
                    data-wanted="{{ 'true' if card.wanted else 'false' }}"
                    aria-pressed="{{ 'true' if card.wanted else 'false' }}"
                    aria-label="{{ 'Remover dos meus filmes' if card.wanted else 'Adicionar aos meus filmes' }}">
                <span aria-hidden="true">{{ '★' if card.wanted else '☆' }}</span>
            </button>
```

- [ ] **Step 2: Add the CSS**

Append to `flask_backend/static/css/reels.css`:

```css
.reels-want-to-watch {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    z-index: 2;
    width: 2.5rem;
    height: 2.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, 0.25);
    background: rgba(0, 0, 0, 0.35);
    backdrop-filter: blur(2px);
    color: #fff;
    font-size: 1.4rem;
    line-height: 1;
    padding: 0;
    cursor: pointer;
    transition: transform 0.15s ease;
}

.reels-want-to-watch:active {
    transform: scale(0.9);
}

.reels-want-to-watch[data-wanted="true"] {
    color: var(--reels-accent);
}

@media (prefers-reduced-motion: no-preference) {
    .reels-want-to-watch-pop {
        animation: reels-want-to-watch-pop 0.3s ease;
    }
}

@keyframes reels-want-to-watch-pop {
    0% {
        transform: scale(1);
    }

    40% {
        transform: scale(1.3);
    }

    100% {
        transform: scale(1);
    }
}
```

- [ ] **Step 3: Add the toggle script**

Create `flask_backend/static/reels-want-to-watch.js`:

```javascript
function setWantToWatchState(button, wanted) {
    button.dataset.wanted = wanted ? "true" : "false";
    button.setAttribute("aria-pressed", wanted ? "true" : "false");
    button.setAttribute(
        "aria-label",
        wanted ? "Remover dos meus filmes" : "Adicionar aos meus filmes"
    );
    button.querySelector("span").textContent = wanted ? "★" : "☆";
}

document.addEventListener("click", (event) => {
    const button = event.target.closest('[data-function="want-to-watch"]');
    if (!button || button.disabled) return;

    const wasWanted = button.dataset.wanted === "true";
    setWantToWatchState(button, !wasWanted);
    button.classList.add("reels-want-to-watch-pop");
    button.disabled = true;

    fetch(`/movie/${button.dataset.movieId}/want-to-watch`, { method: "POST" })
        .then((response) => {
            if (!response.ok) throw new Error("want-to-watch request failed");
            return response.json();
        })
        .then((data) => {
            setWantToWatchState(button, data.wanted);
        })
        .catch((error) => {
            console.error("Error:", error);
            setWantToWatchState(button, wasWanted);
        })
        .finally(() => {
            button.disabled = false;
            setTimeout(() => button.classList.remove("reels-want-to-watch-pop"), 300);
        });
});
```

- [ ] **Step 4: Load the script and add the nav link**

In `flask_backend/templates/base_reels.html`, add the "Meus Filmes" nav item after the "Programação" item:

```html
                <li class="nav-item">
                    <a class="nav-link" href="{{ url_for("screening.programacao") }}">Programação</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="{{ url_for("screening.favoritos") }}">Meus Filmes</a>
                </li>
```

Add the script tag after `halfmoon/bootstrap.bundle.js`, before the goatcounter script:

```html
    <script src="{{ url_for('static', filename='halfmoon/bootstrap.bundle.js') }}"></script>
    <script src="{{ url_for('static', filename='reels-want-to-watch.js') }}"></script>
```

- [ ] **Step 5: Run the full test suite**

Run: `pytest flask_backend/tests`
Expected: PASS (nothing in this task touches Python, but confirms the template changes didn't break rendering)

- [ ] **Step 6: Manually verify in the browser**

Run: `flask --app flask_backend run --debug`

Using a mobile viewport (or actual phone), visit `/`:
- The star appears in the top-right corner of each poster panel.
- Tapping it fills the star immediately (pop animation) and, after a moment, stays filled (server confirmed).
- Reloading the page keeps the star filled for that movie.
- Tapping again empties the star and the mark is removed on reload.
- Open the hamburger menu, confirm "Meus Filmes" links to `/favoritos` and shows the marked movie.
- On `/favoritos`, tap the star again to unmark; reloading `/favoritos` shows the empty state.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/templates/screening/_reels_card.html \
  flask_backend/static/css/reels.css \
  flask_backend/static/reels-want-to-watch.js \
  flask_backend/templates/base_reels.html
git commit -m "feat: add want-to-watch star button UI"
```

---

### Task 7: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full lint/format suite**

```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```

Expected: no errors; if `ruff format` or `djlint --reformat` change files, review the diff for correctness, then re-run the affected tests.

- [ ] **Step 2: Run the full test suite with coverage**

```bash
coverage run -m pytest && coverage report -m
```

Expected: all tests pass; spot-check that `flask_backend/repository/want_to_watch.py`, the new `screening.py` routes, and `build_favorites_feed` show reasonable coverage (no large uncovered blocks).

- [ ] **Step 3: Re-run the manual browser check from Task 6, Step 6**

Confirm nothing regressed after the lint/format pass (in particular, `djlint --reformat` touches template whitespace — verify the reels card layout still renders correctly).

- [ ] **Step 4: Commit any lint/format fixups**

If Step 1 modified any files:

```bash
git add -u
git commit -m "chore: apply lint/format fixes"
```
