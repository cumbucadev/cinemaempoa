# Mobile Reels-Style Homepage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mobile homepage with an Instagram-reels-style feed — one screening fills the screen at a time, vertical scroll snaps between screenings, horizontal swipe reveals a "more info" panel — while leaving the desktop homepage completely untouched.

**Architecture:** `screening.index` (`/`) branches on `User-Agent`. Mobile requests get a new 7-day, cross-cinema query and render a new full-bleed template (`screening/index_mobile.html` extending a minimal `base_reels.html`, no navbar/footer). Everything else falls through to the existing code path unchanged. Vertical/horizontal snapping is pure CSS (`scroll-snap-type`); an `IntersectionObserver` preloads upcoming poster images.

**Tech Stack:** Flask + Jinja2 (server-rendered), SQLAlchemy, vanilla JS, Halfmoon/Bootstrap (already vendored, no new dependencies), pytest.

## Global Constraints

- No new dependencies (no npm/build pipeline exists in this repo — vanilla JS and CSS only).
- Desktop/tablet rendering path (`get_days_screenings_by_cinema_id` and the existing `screening/index.html`) must not change.
- Mobile detection is a `User-Agent` heuristic, not a real viewport check (documented trade-off — see `docs/superpowers/specs/2026-07-25-mobile-reels-homepage-design.md`).
- Feed window is a rolling 7 days (today through today+6 inclusive).
- One card per `Screening` (per cinema run), ordered by that screening's own soonest date/time within the window.
- "Next dates" in the info panel aggregate `ScreeningDate` rows for the same `movie_id` across **all** cinemas, within the same 7-day window — and must never leak a draft screening's dates to a non-logged-in viewer.
- UI copy is in Portuguese (Brazil), matching the rest of the site.
- Run `uv run ruff check --fix`, `uv run ruff format`, `uv run djlint flask_backend/templates --lint --profile=jinja` before considering the branch done (per `CLAUDE.md`).
- Never add an AI/agent co-author trailer to commits.

---

### Task 1: Mobile User-Agent detection helper

**Files:**
- Create: `flask_backend/utils/mobile.py`
- Test: `flask_backend/tests/test_utils/__init__.py` (new, empty — matches the `__init__.py` convention used by `test_service/`, `test_repository/`, `test_routes/`)
- Test: `flask_backend/tests/test_utils/test_mobile.py`

**Interfaces:**
- Produces: `is_mobile_user_agent(user_agent: str) -> bool`, used by Task 7's route wiring.

- [ ] **Step 1: Write the failing test**

```python
# flask_backend/tests/test_utils/test_mobile.py
from flask_backend.utils.mobile import is_mobile_user_agent

IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)
ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Mobile Safari/537.36"
)
DESKTOP_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DESKTOP_SAFARI_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)


class TestIsMobileUserAgent:
    def test_detects_iphone(self):
        assert is_mobile_user_agent(IPHONE_UA) is True

    def test_detects_android(self):
        assert is_mobile_user_agent(ANDROID_UA) is True

    def test_rejects_desktop_chrome(self):
        assert is_mobile_user_agent(DESKTOP_CHROME_UA) is False

    def test_rejects_desktop_safari(self):
        assert is_mobile_user_agent(DESKTOP_SAFARI_UA) is False

    def test_rejects_empty_string(self):
        assert is_mobile_user_agent("") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_utils/test_mobile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'flask_backend.utils.mobile'`

- [ ] **Step 3: Write minimal implementation**

```python
# flask_backend/utils/mobile.py
import re

# Heuristic only - see docs/superpowers/specs/2026-07-25-mobile-reels-homepage-design.md
# for why a User-Agent check was chosen over a real viewport check.
_MOBILE_USER_AGENT_PATTERN = re.compile(
    r"Mobi|Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini",
    re.IGNORECASE,
)


def is_mobile_user_agent(user_agent: str) -> bool:
    return bool(_MOBILE_USER_AGENT_PATTERN.search(user_agent))
```

Also create the empty `flask_backend/tests/test_utils/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest flask_backend/tests/test_utils/test_mobile.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/utils/mobile.py flask_backend/tests/test_utils/
git commit -m "feat: add mobile user-agent detection helper"
```

---

### Task 2: Repository — `get_screenings_in_date_range`

**Files:**
- Modify: `flask_backend/repository/screenings.py`
- Test: `flask_backend/tests/test_repository/test_screenings.py`

**Interfaces:**
- Consumes: `Screening`, `ScreeningDate` models (existing).
- Produces: `get_screenings_in_date_range(start_date: date, end_date: date) -> List[Screening]`, used by Task 7's route wiring.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_repository/test_screenings.py` (reuses the file's existing `_create_screening` helper and `date`/`timedelta` imports already at the top of the file):

```python
from flask_backend.repository.screenings import (
    get_screenings_in_date_range,
    get_screenings_with_upcoming_dates,
)


class TestGetScreeningsInDateRange:
    def test_includes_screening_with_a_date_inside_the_range(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=3)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_excludes_screening_with_a_date_before_the_range(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Filme Passado", "filme-passado", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id not in ids

    def test_excludes_screening_with_a_date_after_the_range(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Filme Futuro", "filme-futuro", [date.today() + timedelta(days=7)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id not in ids

    def test_includes_screening_with_a_date_on_the_last_day_of_the_range(
        self, app, setup_cinemas
    ):
        screening_id = _create_screening(
            app, "Filme Limite", "filme-limite", [date.today() + timedelta(days=6)]
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_includes_draft_screenings(self, app, setup_cinemas):
        screening_id = _create_screening(
            app, "Rascunho", "rascunho", [date.today()], draft=True
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert screening_id in ids

    def test_does_not_duplicate_screenings_with_multiple_dates_in_range(
        self, app, setup_cinemas
    ):
        screening_id = _create_screening(
            app,
            "Recorrente",
            "recorrente",
            [date.today(), date.today() + timedelta(days=1)],
        )

        with app.app_context():
            ids = [
                s.id
                for s in get_screenings_in_date_range(
                    date.today(), date.today() + timedelta(days=6)
                )
            ]
            assert ids.count(screening_id) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v -k GetScreeningsInDateRange`
Expected: FAIL with `ImportError: cannot import name 'get_screenings_in_date_range'`

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/repository/screenings.py`, near `get_month_screening_dates`:

```python
def get_screenings_in_date_range(start_date: date, end_date: date) -> List[Screening]:
    """Screenings (draft included) with at least one ScreeningDate between
    start_date and end_date, inclusive. Powers the mobile reels feed - the
    caller decides whether to keep drafts based on login state."""
    return (
        db_session.query(Screening)
        .join(ScreeningDate)
        .filter(func.date(ScreeningDate.date).between(start_date, end_date))
        .distinct()
        .all()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v -k GetScreeningsInDateRange`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/tests/test_repository/test_screenings.py
git commit -m "feat: add get_screenings_in_date_range repository query"
```

---

### Task 3: Repository — `get_screening_dates_for_movies`

**Files:**
- Modify: `flask_backend/repository/screenings.py`
- Modify: `flask_backend/tests/test_repository/test_screenings.py` (extend the shared `_create_screening` helper)

**Interfaces:**
- Produces: `get_screening_dates_for_movies(movie_ids: List[int], start_date: date, end_date: date, include_drafts: bool = False) -> List[ScreeningDate]`, used by Task 6's `build_reels_feed`.

- [ ] **Step 1: Extend the shared test helper and write the failing tests**

The existing `_create_screening` helper (top of `flask_backend/tests/test_repository/test_screenings.py`) always creates a brand-new movie at "capitolio". To test cross-cinema aggregation we need to reuse a movie across two cinemas. Replace the helper with:

```python
def _create_screening(app, title, slug, dates, draft=False, cinema_slug="capitolio", movie_id=None):
    with app.app_context():
        if movie_id is None:
            movie = Movie(title=title, slug=slug, created_at=datetime.now())
            db_session.add(movie)
            db_session.commit()
            movie_id = movie.id
        cinema = get_cinema_by_slug(cinema_slug)
        screening = Screening(
            movie_id=movie_id,
            cinema_id=cinema.id,
            description="desc",
            draft=draft,
        )
        db_session.add(screening)
        db_session.commit()
        for screening_date in dates:
            db_session.add(
                ScreeningDate(
                    screening_id=screening.id, date=screening_date, time="20:00"
                )
            )
        db_session.commit()
        return screening.id, movie_id
```

This changes the return type from `screening_id` to `(screening_id, movie_id)`. Update the existing call sites in `TestGetScreeningsWithUpcomingDates` and `TestGetScreeningsInDateRange` to unpack it:

```python
screening_id, _ = _create_screening(...)
```

(Six call sites from Task 2 plus four from the pre-existing `TestGetScreeningsWithUpcomingDates` class — mechanical find/replace of `screening_id = _create_screening(` to `screening_id, _ = _create_screening(`.)

Then add:

```python
from flask_backend.repository.screenings import (
    get_screening_dates_for_movies,
    get_screenings_in_date_range,
    get_screenings_with_upcoming_dates,
)


class TestGetScreeningDatesForMovies:
    def test_includes_dates_for_the_requested_movie(self, app, setup_cinemas):
        screening_id, movie_id = _create_screening(
            app, "Filme", "filme", [date.today() + timedelta(days=2)]
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 1
            assert dates[0].screening_id == screening_id

    def test_aggregates_dates_across_cinemas_for_the_same_movie(
        self, app, setup_cinemas
    ):
        _screening_id_a, movie_id = _create_screening(
            app, "Filme", "filme", [date.today()], cinema_slug="capitolio"
        )
        _create_screening(
            app,
            "Filme",
            "filme",
            [date.today() + timedelta(days=1)],
            cinema_slug="sala-redencao",
            movie_id=movie_id,
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 2

    def test_excludes_dates_for_other_movies(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app, "Filme A", "filme-a", [date.today()]
        )
        _create_screening(app, "Filme B", "filme-b", [date.today()])

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 1

    def test_excludes_dates_outside_the_range(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app,
            "Filme",
            "filme",
            [date.today(), date.today() + timedelta(days=10)],
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert len(dates) == 1

    def test_excludes_draft_screening_dates_by_default(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app, "Rascunho", "rascunho", [date.today()], draft=True
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id], date.today(), date.today() + timedelta(days=6)
            )
            assert dates == []

    def test_includes_draft_screening_dates_when_include_drafts_is_true(
        self, app, setup_cinemas
    ):
        _screening_id, movie_id = _create_screening(
            app, "Rascunho", "rascunho", [date.today()], draft=True
        )

        with app.app_context():
            dates = get_screening_dates_for_movies(
                [movie_id],
                date.today(),
                date.today() + timedelta(days=6),
                include_drafts=True,
            )
            assert len(dates) == 1

    def test_returns_empty_list_for_empty_movie_ids(self, app, setup_cinemas):
        with app.app_context():
            assert get_screening_dates_for_movies([], date.today(), date.today()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v`
Expected: FAIL — `ImportError` for `get_screening_dates_for_movies`, plus the unpacking changes will fail until Step 3/the helper rewrite lands (this is expected since Step 1 changes both the helper and its call sites together).

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/repository/screenings.py`:

```python
def get_screening_dates_for_movies(
    movie_ids: List[int],
    start_date: date,
    end_date: date,
    include_drafts: bool = False,
) -> List[ScreeningDate]:
    """Every ScreeningDate between start_date and end_date (inclusive) for
    the given movie IDs, across all cinemas. Drafts are excluded unless
    include_drafts is True - callers must pass True only for logged-in
    requests, otherwise a movie with an unpublished screening at one cinema
    would leak that draft's dates via another cinema's published card."""
    if not movie_ids:
        return []
    query = (
        db_session.query(ScreeningDate)
        .join(Screening)
        .filter(Screening.movie_id.in_(movie_ids))
        .filter(func.date(ScreeningDate.date).between(start_date, end_date))
    )
    if not include_drafts:
        query = query.filter(Screening.draft == False)  # noqa: E712
    return query.all()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v`
Expected: PASS (all tests in the file, including the pre-existing `TestGetScreeningsWithUpcomingDates` class with its call sites updated)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/tests/test_repository/test_screenings.py
git commit -m "feat: add get_screening_dates_for_movies repository query"
```

---

### Task 4: Service — `get_soonest_date_in_range`

**Files:**
- Modify: `flask_backend/service/screening.py`
- Test: `flask_backend/tests/test_service/test_screening.py`

**Interfaces:**
- Produces: `get_soonest_date_in_range(screening_dates: List[ScreeningDate], start_date: date, end_date: date) -> ScreeningDate`. Precondition: at least one date in `screening_dates` falls within range (guaranteed by `get_screenings_in_date_range`'s join filter — callers using unfiltered data must not call this). Used by Task 6.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_screening.py`:

```python
from datetime import date, timedelta

from flask_backend.models import ScreeningDate
from flask_backend.service.screening import get_soonest_date_in_range


class TestGetSoonestDateInRange:
    def test_returns_the_earliest_date_in_range(self):
        today = date.today()
        later = ScreeningDate(date=today + timedelta(days=3), time="20:00")
        sooner = ScreeningDate(date=today + timedelta(days=1), time="18:00")

        result = get_soonest_date_in_range(
            [later, sooner], today, today + timedelta(days=6)
        )

        assert result is sooner

    def test_ignores_dates_outside_the_range(self):
        today = date.today()
        in_range = ScreeningDate(date=today + timedelta(days=1), time="18:00")
        out_of_range = ScreeningDate(date=today - timedelta(days=1), time="10:00")

        result = get_soonest_date_in_range(
            [out_of_range, in_range], today, today + timedelta(days=6)
        )

        assert result is in_range

    def test_breaks_ties_on_the_same_date_by_time(self):
        today = date.today()
        earlier_time = ScreeningDate(date=today, time="14:00")
        later_time = ScreeningDate(date=today, time="20:00")

        result = get_soonest_date_in_range(
            [later_time, earlier_time], today, today + timedelta(days=6)
        )

        assert result is earlier_time
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_screening.py -v -k GetSoonestDateInRange`
Expected: FAIL with `ImportError: cannot import name 'get_soonest_date_in_range'`

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/screening.py`, near `group_screening_dates_by_day`:

```python
def get_soonest_date_in_range(
    screening_dates: List[ScreeningDate], start_date: date, end_date: date
) -> ScreeningDate:
    """Earliest ScreeningDate within [start_date, end_date]. Assumes at
    least one date in screening_dates falls in that range."""
    in_range = [d for d in screening_dates if start_date <= d.date <= end_date]
    return min(in_range, key=lambda d: (d.date, d.time or ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest flask_backend/tests/test_service/test_screening.py -v -k GetSoonestDateInRange`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py
git commit -m "feat: add get_soonest_date_in_range service helper"
```

---

### Task 5: Service — `format_day_label`

**Files:**
- Modify: `flask_backend/service/screening.py`
- Test: `flask_backend/tests/test_service/test_screening.py`

**Interfaces:**
- Produces: `format_day_label(day: date, today: date) -> str`. Used by Task 6.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_screening.py`:

```python
from flask_backend.service.screening import format_day_label


class TestFormatDayLabel:
    def test_labels_today(self):
        today = date(2026, 7, 25)
        assert format_day_label(today, today) == "Hoje, 25/07"

    def test_labels_tomorrow(self):
        today = date(2026, 7, 25)
        assert format_day_label(today + timedelta(days=1), today) == "Amanhã, 26/07"

    def test_labels_later_days_with_weekday_name(self):
        today = date(2026, 7, 25)  # a Saturday
        # today + 4 days = 2026-07-29, a Wednesday
        assert (
            format_day_label(today + timedelta(days=4), today)
            == "Quarta-feira, 29/07"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_screening.py -v -k FormatDayLabel`
Expected: FAIL with `ImportError: cannot import name 'format_day_label'`

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/screening.py`:

```python
_WEEKDAY_NAMES_PT = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]


def format_day_label(day: date, today: date) -> str:
    """Portuguese label for a reels-feed day-boundary card: "Hoje, DD/MM",
    "Amanhã, DD/MM", or "<Weekday>, DD/MM" for later days."""
    formatted_date = day.strftime("%d/%m")
    if day == today:
        return f"Hoje, {formatted_date}"
    if day == today + timedelta(days=1):
        return f"Amanhã, {formatted_date}"
    return f"{_WEEKDAY_NAMES_PT[day.weekday()]}, {formatted_date}"
```

`timedelta` is not yet imported in `flask_backend/service/screening.py` — change the existing `from datetime import date, datetime` line to `from datetime import date, datetime, timedelta`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest flask_backend/tests/test_service/test_screening.py -v -k FormatDayLabel`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py
git commit -m "feat: add format_day_label service helper"
```

---

### Task 6: Service — `build_reels_feed`

**Files:**
- Modify: `flask_backend/service/screening.py`
- Test: `flask_backend/tests/test_service/test_screening.py`

**Interfaces:**
- Consumes: `get_soonest_date_in_range` (Task 4), `format_day_label` (Task 5); `Screening`, `ScreeningDate` models.
- Produces: `build_reels_feed(screenings: List[Screening], movie_dates: List[ScreeningDate], today: date, window_end: date, user_logged_in: bool) -> List[dict]`. Each dict has keys: `screening_id`, `movie_title`, `directors` (`List[str]`), `release_year`, `description`, `image`, `image_alt`, `cinema_name`, `cinema_color`, `soonest_time`, `day_label` (`Optional[str]`), `next_dates` (`List[dict]` with `date`, `time`, `cinema_name` keys), `draft` (`bool`), `screening_url`. Used by Task 7's route wiring and template.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_service/test_screening.py`:

```python
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate
from flask_backend.service.screening import build_reels_feed


def _movie(title="Filme", release_year=2024):
    return Movie(title=title, release_year=release_year, directors=[])


def _cinema(slug="capitolio"):
    # short_name and color are computed properties looked up by slug from
    # CINEMA_SHORT_NAMES/CINEMA_COLORS (flask_backend/constants.py) - the
    # slug is what actually drives them, `name` here is just the fallback.
    return Cinema(slug=slug, name=slug, url="https://example.com")


def _screening(movie, cinema, dates, draft=False, screening_id=1, image=None):
    screening = Screening(
        id=screening_id,
        movie=movie,
        movie_id=1,
        cinema=cinema,
        description="Uma descrição",
        draft=draft,
        image=image,
        dates=dates,
    )
    return screening


class TestBuildReelsFeed:
    def test_orders_cards_by_each_screenings_soonest_date(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        later = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today + timedelta(days=2), time="20:00")],
            screening_id=1,
        )
        sooner = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="18:00")],
            screening_id=2,
        )

        cards = build_reels_feed(
            [later, sooner], [], today, today + timedelta(days=6), False
        )

        assert [card["screening_id"] for card in cards] == [2, 1]

    def test_excludes_draft_screenings_when_not_logged_in(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        draft = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="20:00")],
            draft=True,
            screening_id=1,
        )

        cards = build_reels_feed(
            [draft], [], today, today + timedelta(days=6), False
        )

        assert cards == []

    def test_includes_draft_screenings_when_logged_in(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        draft = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today, time="20:00")],
            draft=True,
            screening_id=1,
        )

        cards = build_reels_feed(
            [draft], [], today, today + timedelta(days=6), True
        )

        assert len(cards) == 1
        assert cards[0]["draft"] is True

    def test_attaches_next_dates_for_the_cards_movie(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        screening = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=1
        )
        other_cinema_date = ScreeningDate(
            date=today + timedelta(days=1), time="19:00"
        )
        other_cinema_date.screening = _screening(
            movie, _cinema(slug="sala-redencao"), [], screening_id=2
        )

        cards = build_reels_feed(
            [screening],
            [other_cinema_date],
            today,
            today + timedelta(days=6),
            False,
        )

        assert len(cards[0]["next_dates"]) == 1
        assert cards[0]["next_dates"][0]["cinema_name"] == "Sala Redenção"

    def test_marks_day_label_only_on_the_first_card_of_each_day(self):
        today = date.today()
        movie = _movie()
        cinema = _cinema()
        first = _screening(
            movie, cinema, [ScreeningDate(date=today, time="18:00")], screening_id=1
        )
        second_same_day = _screening(
            movie, cinema, [ScreeningDate(date=today, time="20:00")], screening_id=2
        )
        next_day = _screening(
            movie,
            cinema,
            [ScreeningDate(date=today + timedelta(days=1), time="18:00")],
            screening_id=3,
        )

        cards = build_reels_feed(
            [second_same_day, next_day, first],
            [],
            today,
            today + timedelta(days=6),
            False,
        )

        assert cards[0]["day_label"] is not None
        assert cards[1]["day_label"] is None
        assert cards[2]["day_label"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_screening.py -v -k BuildReelsFeed`
Expected: FAIL with `ImportError: cannot import name 'build_reels_feed'`

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/screening.py`. Change the `from typing import List, Optional, Tuple` line to `from typing import Dict, List, Optional, Tuple`, and change `from flask_backend.models import ScreeningDate` to `from flask_backend.models import Screening, ScreeningDate`. Add `from collections import OrderedDict, defaultdict` (there is already `from collections import OrderedDict` — change it to also import `defaultdict`).

```python
def build_reels_feed(
    screenings: List[Screening],
    movie_dates: List[ScreeningDate],
    today: date,
    window_end: date,
    user_logged_in: bool,
) -> List[dict]:
    """Builds the mobile reels feed: one card per non-draft screening (all
    screenings if user_logged_in), sorted by each screening's soonest
    ScreeningDate within [today, window_end]. `movie_dates` is the flat,
    cross-cinema list of ScreeningDate rows for every movie present in
    `screenings` within the same window - grouped here per movie for each
    card's "next dates" list."""
    dates_by_movie: Dict[int, List[ScreeningDate]] = defaultdict(list)
    for screening_date in movie_dates:
        dates_by_movie[screening_date.screening.movie_id].append(screening_date)

    cards = []
    for screening in screenings:
        if screening.draft and not user_logged_in:
            continue
        soonest = get_soonest_date_in_range(screening.dates, today, window_end)
        next_dates = sorted(
            dates_by_movie.get(screening.movie_id, []),
            key=lambda d: (d.date, d.time or ""),
        )
        cards.append(
            {
                "screening_id": screening.id,
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
            }
        )

    cards.sort(key=lambda card: (card["soonest_date"], card["soonest_time"] or ""))

    seen_dates = set()
    for card in cards:
        if card["soonest_date"] not in seen_dates:
            card["day_label"] = format_day_label(card["soonest_date"], today)
            seen_dates.add(card["soonest_date"])
        else:
            card["day_label"] = None

    return cards
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_screening.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/screening.py flask_backend/tests/test_service/test_screening.py
git commit -m "feat: add build_reels_feed service function"
```

---

### Task 7: Route wiring and minimal templates

**Files:**
- Modify: `flask_backend/routes/screening.py`
- Create: `flask_backend/templates/base_reels.html`
- Create: `flask_backend/templates/screening/index_mobile.html`
- Test: `flask_backend/tests/test_routes/test_screening.py`

**Interfaces:**
- Consumes: `is_mobile_user_agent` (Task 1), `get_screenings_in_date_range` / `get_screening_dates_for_movies` (Tasks 2-3), `build_reels_feed` (Task 6).
- Produces: mobile-branch behavior on `GET /`, and the `cards` template variable consumed by later tasks (8, 9, 10) which only add CSS/JS/markup on top of this skeleton.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_routes/test_screening.py` (reuses the file's existing `_create_screening` helper):

```python
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)


class TestScreeningIndexMobile:
    def test_returns_200_for_mobile_user_agent(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        assert response.status_code == 200

    def test_renders_reels_feed_for_mobile_user_agent(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(movie_title="Filme Mobile")
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert "Filme Mobile" in html
        assert 'class="reels-feed"' in html

    def test_desktop_user_agent_still_gets_the_existing_layout(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(movie_title="Filme Desktop")
        response = client.get("/")
        html = response.get_data(as_text=True)
        assert "Filme Desktop" in html
        assert 'class="reels-feed"' not in html

    def test_hides_draft_screening_on_mobile_when_not_logged_in(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(movie_title="Filme Rascunho Mobile", draft=True)
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        assert b"Filme Rascunho Mobile" not in response.data

    def test_shows_draft_screening_on_mobile_when_logged_in(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            _create_screening(movie_title="Filme Rascunho Mobile Logado", draft=True)
        response = auth_headers.get("/", headers={"User-Agent": MOBILE_UA})
        assert b"Filme Rascunho Mobile Logado" in response.data

    def test_shows_placeholder_for_screening_without_poster(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(movie_title="Filme Sem Poster", image=None)
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'class="reels-poster-placeholder"' in html

    def test_shows_empty_state_when_no_screenings_in_range(
        self, client, setup_cinemas
    ):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert "Não há sessões" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k Mobile`
Expected: FAIL — desktop still serves the reels feed too (no branching yet) / `TemplateNotFound`, depending on where you run this from a clean checkout.

- [ ] **Step 3: Write minimal implementation**

Modify `flask_backend/routes/screening.py`. Change the top `from datetime import date, datetime` import to `from datetime import date, datetime, timedelta`. Add new imports near the existing repository/service imports:

```python
from flask_backend.repository.screenings import (
    ...  # existing imports stay
    get_screening_dates_for_movies,
    get_screenings_in_date_range,
)
from flask_backend.service.screening import (
    build_dates,
    build_reels_feed,
    save_image,
    validate_image,
)
from flask_backend.utils.mobile import is_mobile_user_agent
```

Change the `index()` function to branch at the top:

```python
@bp.route("/")
def index():
    if is_mobile_user_agent(request.headers.get("User-Agent", "")):
        return _mobile_index()

    cinemas = get_all_cinemas()
    # ... rest of the existing function body is unchanged ...
```

Add a new private function right above `index()`:

```python
def _mobile_index():
    today = date.today()
    window_end = today + timedelta(days=6)
    user_logged_in = g.user is not None

    screenings = get_screenings_in_date_range(today, window_end)
    movie_ids = list({screening.movie_id for screening in screenings})
    movie_dates = get_screening_dates_for_movies(
        movie_ids, today, window_end, include_drafts=user_logged_in
    )
    cards = build_reels_feed(
        screenings, movie_dates, today, window_end, user_logged_in
    )

    return render_template("screening/index_mobile.html", cards=cards)
```

Create `flask_backend/templates/base_reels.html`:

```jinja
<!DOCTYPE html>
<html lang="pt-br" data-bs-core="default">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>
        {% block title %}
        {% endblock title %}
    - Cinema em POA</title>
    {% block meta_tags %}
    {% endblock meta_tags %}
    <link rel="apple-touch-icon"
          sizes="180x180"
          href="{{ url_for('static', filename='apple-touch-icon.png') }}">
    <link rel="icon"
          type="image/png"
          sizes="32x32"
          href="{{ url_for('static', filename='favicon-32x32.png') }}">
    <link rel="icon"
          type="image/png"
          sizes="16x16"
          href="{{ url_for('static', filename='favicon-16x16.png') }}">
    <link rel="manifest"
          href="{{ url_for('static', filename='site.webmanifest') }}">
    <link rel="stylesheet"
          href="{{ url_for('static', filename='halfmoon/halfmoon.min.css') }}" />
    {% block extra_head %}
    {% endblock extra_head %}
</head>
<body>
    {% block content %}
    {% endblock content %}
    <script>
        if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
            document.querySelector("html").setAttribute("data-bs-theme", "dark");
        } else {
            document.querySelector("html").setAttribute("data-bs-theme", "light");
        }
    </script>
    <script src="{{ url_for('static', filename='halfmoon/bootstrap.bundle.js') }}"></script>
</body>
</html>
```

Create `flask_backend/templates/screening/index_mobile.html`:

```jinja
{% extends "base_reels.html" %}
{% block title %}Programação do dia{% endblock title %}
{% block meta_tags %}
    <meta name="description"
          content="Filmes em cartaz nos próximos dias nas salas de cinema alternativo em Porto Alegre.">
{% endblock meta_tags %}
{% block content %}
    <div class="reels-feed">
        {% if cards %}
            {% for card in cards %}
                <section class="reels-card">
                    {% if card.day_label %}<p class="reels-day-label">{{ card.day_label }}</p>{% endif %}
                    <div class="reels-card-panels">
                        <div class="reels-panel reels-panel-poster">
                            {% if card.image %}
                                <img class="reels-poster-img"
                                     src="{{ card.image }}"
                                     alt="{{ card.image_alt or card.movie_title }}" />
                            {% else %}
                                <div class="reels-poster-placeholder"
                                     style="background-color: {{ card.cinema_color }}">
                                    <span>{{ card.movie_title }}</span>
                                </div>
                            {% endif %}
                            <div class="reels-overlay">
                                <span class="badge rounded-pill" style="background-color: {{ card.cinema_color }}">{{ card.cinema_name }}</span>
                                <h2>{{ card.movie_title }}</h2>
                                <p>
                                    {% if card.soonest_time %}{{ card.soonest_time }}{% endif %}
                                    {% if card.directors %} · {{ card.directors|join(', ') }}{% endif %}
                                    {% if card.release_year %} · {{ card.release_year }}{% endif %}
                                </p>
                                {% if card.draft %}<span class="badge text-bg-warning">Rascunho</span>{% endif %}
                            </div>
                        </div>
                        <div class="reels-panel reels-panel-info">
                            <p>{{ card.description }}</p>
                            {% if card.next_dates %}
                                <ul class="list-unstyled">
                                    {% for next_date in card.next_dates %}
                                        <li>{{ next_date.date.strftime("%d/%m") }} · {{ next_date.cinema_name }}{% if next_date.time %} · {{ next_date.time }}{% endif %}</li>
                                    {% endfor %}
                                </ul>
                            {% endif %}
                            {% if card.screening_url %}<p><a href="{{ card.screening_url }}">Veja a postagem original</a></p>{% endif %}
                            <p>
                                {% if g.user %}
                                    <a href="{{ url_for('screening.update', id=card.screening_id) }}">Edite!</a>
                                {% else %}
                                    <a href="{{ url_for('screening.update', id=card.screening_id) }}">Achou um erro? Ajude a corrigir!</a>
                                {% endif %}
                            </p>
                        </div>
                    </div>
                </section>
            {% endfor %}
        {% else %}
            <section class="reels-card reels-empty">
                <strong>Não há sessões nos próximos dias.</strong>
            </section>
        {% endif %}
    </div>
{% endblock content %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k Mobile`
Expected: PASS (7 passed)

Then run the full route test file to confirm the desktop tests still pass unchanged:

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/routes/screening.py flask_backend/templates/base_reels.html flask_backend/templates/screening/index_mobile.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: wire mobile reels feed into the homepage route"
```

---

### Task 8: Scroll-snap CSS and placeholder styling

**Files:**
- Modify: `flask_backend/templates/screening/index_mobile.html`

**Interfaces:**
- Consumes: the `reels-feed` / `reels-card` / `reels-card-panels` / `reels-panel` / `reels-poster-placeholder` class hooks from Task 7.
- Produces: no new server-side interface — purely visual. Verified via the same route tests from Task 7 (they already assert on the class names this task styles) plus a manual check in Task 11.

- [ ] **Step 1: Write the failing test**

The relevant behavioral assertions already exist in Task 7 (`class="reels-feed"`, `class="reels-poster-placeholder"`). Add one more, checking the swipe-hint chevron is present, to `flask_backend/tests/test_routes/test_screening.py`:

```python
    def test_poster_panel_has_a_swipe_hint(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(movie_title="Filme Com Dica")
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'class="reels-swipe-hint"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k swipe_hint`
Expected: FAIL — no element with that class exists yet

- [ ] **Step 3: Add the CSS and the swipe-hint markup**

In `flask_backend/templates/screening/index_mobile.html`, add a `<style>` block inside `{% block extra_head %}` (this block was added to `base_reels.html` in Task 7):

```jinja
{% block extra_head %}
    <style>
        html, body {
            height: 100%;
            margin: 0;
            background: #000;
        }

        .reels-feed {
            height: 100vh;
            height: 100dvh;
            overflow-y: scroll;
            scroll-snap-type: y mandatory;
            scroll-behavior: smooth;
        }

        .reels-card {
            height: 100vh;
            height: 100dvh;
            scroll-snap-align: start;
            scroll-snap-stop: always;
            position: relative;
        }

        .reels-day-label {
            position: absolute;
            top: 0.75rem;
            left: 50%;
            transform: translateX(-50%);
            z-index: 2;
            margin: 0;
            padding: 0.25rem 0.75rem;
            background: rgba(0, 0, 0, 0.6);
            color: #fff;
            border-radius: 999px;
            font-size: 0.8rem;
        }

        .reels-card-panels {
            display: flex;
            height: 100%;
            overflow-x: scroll;
            scroll-snap-type: x mandatory;
        }

        .reels-panel {
            flex: 0 0 100%;
            width: 100%;
            height: 100%;
            scroll-snap-align: start;
            scroll-snap-stop: always;
            box-sizing: border-box;
        }

        .reels-panel-poster {
            position: relative;
            overflow: hidden;
        }

        .reels-poster-img,
        .reels-poster-placeholder {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .reels-poster-placeholder {
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 2rem;
            color: #fff;
            font-size: 1.5rem;
            font-weight: 700;
        }

        .reels-overlay {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 1rem;
            background: linear-gradient(to top, rgba(0, 0, 0, 0.85), rgba(0, 0, 0, 0));
            color: #fff;
        }

        .reels-swipe-hint {
            position: absolute;
            top: 50%;
            right: 0.5rem;
            transform: translateY(-50%);
            color: rgba(255, 255, 255, 0.7);
            font-size: 1.5rem;
            pointer-events: none;
        }

        .reels-panel-info {
            overflow-y: auto;
            padding: 1.5rem;
            background: var(--bs-content-bg, #fff);
        }

        .reels-empty {
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            text-align: center;
            padding: 2rem;
        }
    </style>
{% endblock extra_head %}
```

Add the swipe hint inside `.reels-panel-poster`, right after the `.reels-overlay` closing `</div>` from Task 7:

```jinja
                            <span class="reels-swipe-hint" aria-hidden="true">&rsaquo;</span>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS (all tests, including the new swipe-hint test)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/templates/screening/index_mobile.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: add scroll-snap CSS and swipe hint to the mobile reels feed"
```

---

### Task 9: Poster image preloading

**Files:**
- Modify: `flask_backend/templates/screening/index_mobile.html`

**Interfaces:**
- Consumes: `.reels-poster-img` elements from Task 7/8.
- Produces: no new server-side interface — verified via HTML attribute assertions plus manual check in Task 11.

- [ ] **Step 1: Write the failing test**

Add to `flask_backend/tests/test_routes/test_screening.py`:

```python
    def test_first_poster_loads_eagerly_and_later_posters_are_deferred(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            for i in range(3):
                _create_screening(
                    movie_title=f"Filme {i}",
                    image=f"poster{i}.jpg",
                    image_width=100,
                    image_height=200,
                    screening_date=date.today() + timedelta(days=i),
                )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'src="poster0.jpg"' in html
        assert 'data-src="poster2.jpg"' in html
```

`date` and `timedelta` are already imported at the top of `flask_backend/tests/test_routes/test_screening.py` (`from datetime import date, datetime`) — add `timedelta` to that import if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k eagerly`
Expected: FAIL — every poster currently renders with `src`, none with `data-src`

- [ ] **Step 3: Defer later posters and add the preloading script**

In `flask_backend/templates/screening/index_mobile.html`, change the poster `<img>` tag from Task 7:

```jinja
                            {% if card.image %}
                                {% if loop.index0 < 2 %}
                                    <img class="reels-poster-img"
                                         src="{{ card.image }}"
                                         alt="{{ card.image_alt or card.movie_title }}" />
                                {% else %}
                                    <img class="reels-poster-img"
                                         data-src="{{ card.image }}"
                                         alt="{{ card.image_alt or card.movie_title }}" />
                                {% endif %}
                            {% else %}
```

Add a script at the end of `{% block content %}`, after the closing `</div>` of `.reels-feed`:

```jinja
    <script>
        const lazyPosters = document.querySelectorAll(".reels-poster-img[data-src]");
        const posterObserver = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.removeAttribute("data-src");
                        posterObserver.unobserve(img);
                    }
                });
            },
            { rootMargin: "200% 0px 200% 0px" }
        );
        lazyPosters.forEach((img) => posterObserver.observe(img));
    </script>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/templates/screening/index_mobile.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: preload upcoming poster images in the mobile reels feed"
```

---

### Task 10: Draft admin actions and way-back navigation

**Files:**
- Modify: `flask_backend/templates/screening/index_mobile.html`
- Modify: `flask_backend/templates/base_reels.html`

**Interfaces:**
- Consumes: `card.draft`, `card.screening_id`, `g.user` (already available); `url_for("screening.publish"/"screening.delete", id=...)` (existing routes, unchanged).
- Produces: no new server-side interface.

- [ ] **Step 1: Write the failing tests**

Add to `flask_backend/tests/test_routes/test_screening.py`:

```python
    def test_draft_admin_actions_appear_in_the_info_panel_when_logged_in(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            _create_screening(movie_title="Filme Rascunho Ações", draft=True)
        response = auth_headers.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'data-function="publish"' in html
        assert 'data-function="delete"' in html

    def test_menu_button_is_present(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'id="reels-menu-toggle"' in html
        with client.application.test_request_context():
            about_url = url_for("page.about")
        assert about_url in html
```

`url_for` is not yet imported in `flask_backend/tests/test_routes/test_screening.py` — add `from flask import url_for` to the top of the file, alongside the existing imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k "draft_admin_actions or menu_button"`
Expected: FAIL — neither the admin action buttons nor the menu button exist yet

- [ ] **Step 3: Add the admin actions and the menu**

In `flask_backend/templates/screening/index_mobile.html`, inside `.reels-panel-info`, replace the `{% if card.draft %}` badge block from Task 7's poster overlay with just the badge (already there), and add the actions in the info panel, right after the "Achou um erro?" paragraph:

```jinja
                            {% if card.draft %}
                                <p>
                                    <button class="badge text-bg-warning"
                                            data-function="publish"
                                            data-screening-id="{{ card.screening_id }}">
                                        Publicar
                                    </button>
                                    <button class="badge text-bg-danger"
                                            data-function="delete"
                                            data-screening-id="{{ card.screening_id }}">
                                        Descartar
                                    </button>
                                </p>
                            {% endif %}
```

Add the publish/delete JS at the end of `{% block content %}`, reusing the same fetch logic already used in `screening/index.html`:

```jinja
    <script>
        document.querySelectorAll('[data-function="publish"]').forEach((btn) => {
            btn.addEventListener("click", () => {
                fetch(`/screening/${btn.dataset.screeningId}/publish`, { method: "POST" })
                    .then((response) => { if (response.ok) window.location.reload(); });
            });
        });
        document.querySelectorAll('[data-function="delete"]').forEach((btn) => {
            btn.addEventListener("click", () => {
                fetch(`/screening/${btn.dataset.screeningId}/delete`, { method: "POST" })
                    .then((response) => { if (response.ok) window.location.reload(); });
            });
        });
    </script>
```

For the way-back menu, add a floating button plus a Bootstrap offcanvas panel to `flask_backend/templates/base_reels.html`, right after `{% block content %}`:

```jinja
    <button id="reels-menu-toggle"
            type="button"
            class="btn btn-dark"
            style="position: fixed; top: 0.75rem; left: 0.75rem; z-index: 10; border-radius: 999px;"
            data-bs-toggle="offcanvas"
            data-bs-target="#reels-menu"
            aria-controls="reels-menu">
        ☰
    </button>
    <div class="offcanvas offcanvas-start" tabindex="-1" id="reels-menu">
        <div class="offcanvas-header">
            <h5 class="offcanvas-title">Cinema em POA</h5>
            <button type="button" class="btn-close" data-bs-dismiss="offcanvas"></button>
        </div>
        <div class="offcanvas-body">
            <ul class="nav flex-column">
                <li class="nav-item"><a class="nav-link" href="{{ url_for('page.about') }}">Sobre o projeto</a></li>
                <li class="nav-item"><a class="nav-link" href="{{ url_for('screening.programacao') }}">Programação</a></li>
                <li class="nav-item"><a class="nav-link" href="{{ url_for('movie.index') }}">Filmes</a></li>
                <li class="nav-item"><a class="nav-link" href="{{ url_for('blog.index') }}">Blog</a></li>
                {% if g.user %}
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('auth.logout') }}">Sair</a></li>
                {% else %}
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('auth.login') }}">Acessar</a></li>
                {% endif %}
            </ul>
        </div>
    </div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/templates/screening/index_mobile.html flask_backend/templates/base_reels.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: add draft admin actions and way-back menu to the mobile reels feed"
```

---

### Task 11: Manual browser verification

**Files:** none (verification only)

- [ ] **Step 1: Start the dev server**

Run: `flask --app flask_backend run --debug`

- [ ] **Step 2: Seed a few screenings across today and the next few days**

Use the admin "Nova sessão" form (`/screening/new`, requires login) or `flask --app flask_backend seed-db` if it produces screenings in range — create at least: one screening with a poster, one without a poster (placeholder check), one draft (while logged out, then logged in), and two screenings for the same movie at two different cinemas on different days (next-dates aggregation check).

- [ ] **Step 3: Emulate a mobile device and walk through the feed**

In Chrome DevTools, toggle device toolbar to an iPhone/Android preset (this sets both viewport *and* `User-Agent`, since our detection is UA-based). Load `/` and confirm:
- The feed is full-bleed, no navbar/footer visible, menu button opens the offcanvas nav with working links
- Scrolling vertically snaps one screening at a time
- Swiping/scrolling horizontally on a card reveals the info panel (description + next dates), and swiping back returns to the poster
- The chevron swipe hint is visible on the poster
- The posterless screening shows the cinema-colored placeholder with the title
- The draft screening is hidden while logged out and visible (with Publicar/Descartar buttons that work) while logged in
- Scrolling from today's last card into tomorrow's first card shows the day label
- Resize the DevTools window to a desktop width with a desktop UA (toggle device toolbar off) and confirm `/` renders the original, unchanged cinema-grouped list

- [ ] **Step 4: Report findings**

Note any visual issues found (they are not expected, given the CSS was written directly against the class hooks asserted by tests, but this step exists per `CLAUDE.md`'s requirement to verify UI changes in a browser before considering them done). Fix inline if anything is broken, re-running the relevant pytest file after any fix.

---

### Task 12: Lint, format, and final full test run

**Files:** none (verification only, may touch any file the linters reformat)

- [ ] **Step 1: Run the full test suite**

Run: `pytest`
Expected: all tests pass

- [ ] **Step 2: Run lint and formatting**

```bash
uv run ruff check --fix
uv run ruff format
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```

Review any files the formatters touched with `git diff`.

- [ ] **Step 3: Run the full test suite again**

Run: `pytest`
Expected: all tests still pass after formatting

- [ ] **Step 4: Commit any formatting changes**

```bash
git add -u
git commit -m "chore: lint and format mobile reels feed"
```

(Skip this step if `git diff --cached` is empty after `git add -u` — nothing to commit.)
