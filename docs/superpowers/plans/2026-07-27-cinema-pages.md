# Cinema Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public "Cinemas" section (list + per-cinema detail page showing venue info, upcoming screenings, and past movies) and an admin UI for editing each cinema's profile info.

**Architecture:** Two nullable-column additions to the existing `Cinema` model, one new repository query for past/exclusive movies, a public `cinema` blueprint (`/cinemas`, `/cinemas/<slug>`), and an admin `admin_cinemas` blueprint (`/admin/cinemas`, `/admin/cinemas/<id>/update`) — mirroring the split already used by `admin_alerts`/`admin_pipelines`.

**Tech Stack:** Flask, SQLAlchemy, Alembic, Jinja2 + Bootstrap 5 (halfmoon theme), pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-27-cinema-pages-design.md` — read it before starting; every task below implements one section of it.
- No payment methods, no `about.html` changes, no admin "create cinema" route — all explicitly out of scope per the spec.
- All new `Cinema` columns are nullable; no data backfill — existing rows stay `NULL` until edited via the new admin UI.
- Run `pytest flask_backend/tests` after every task; all tests must pass before committing.
- Before opening a PR, run: `uv run ruff check --fix`, `uv run ruff format`, `uv run djlint flask_backend/templates --lint --profile=jinja`, `uv run djlint --reformat flask_backend/templates --format-css --format-js` (per `AGENTS.md`).
- Never add an AI/agent co-author trailer to commits.

---

### Task 1: Cinema profile fields — model, migration, repository `update`

**Files:**
- Modify: `flask_backend/models.py:138-152` (`Cinema` class)
- Create: `migrations/versions/20260727_000001_add_cinema_profile_fields.py` (via `flask --app flask_backend db-revision --autogenerate`)
- Modify: `flask_backend/repository/cinemas.py`
- Test: `flask_backend/tests/test_repository/test_cinemas.py` (new file)

**Interfaces:**
- Consumes: `flask_backend.db.db_session`, existing `Cinema` model (`id`, `slug`, `name`, `url`).
- Produces: `Cinema.address: Optional[str]`, `Cinema.opening_hours: Optional[str]`, `Cinema.instagram_url: Optional[str]`, `Cinema.map_embed_url: Optional[str]`, `Cinema.photo: Optional[str]`, `Cinema.photo_width: Optional[int]`, `Cinema.photo_height: Optional[int]`. `repository.cinemas.update(cinema: Cinema, name: str, url: str, address: Optional[str] = None, opening_hours: Optional[str] = None, instagram_url: Optional[str] = None, map_embed_url: Optional[str] = None, photo: Optional[str] = None, photo_width: Optional[int] = None, photo_height: Optional[int] = None) -> Cinema` — used by Task 4's admin route.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_repository/test_cinemas.py`:

```python
"""
Tests flask_backend/repository/cinemas.py.
"""

from flask_backend.repository.cinemas import get_by_slug, update


class TestUpdateCinema:
    def test_updates_profile_fields(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_by_slug("capitolio")
            updated = update(
                cinema,
                name=cinema.name,
                url=cinema.url,
                address="Rua dos Andradas, 736",
                opening_hours="Ter-Dom, 14h-22h",
                instagram_url="https://instagram.com/cinemateca.capitolio",
                map_embed_url="https://www.google.com/maps/embed?pb=example",
            )

            assert updated.address == "Rua dos Andradas, 736"
            assert updated.opening_hours == "Ter-Dom, 14h-22h"
            assert updated.instagram_url == "https://instagram.com/cinemateca.capitolio"
            assert updated.map_embed_url == "https://www.google.com/maps/embed?pb=example"

    def test_keeps_existing_photo_when_none_provided(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_by_slug("capitolio")
            update(
                cinema,
                name=cinema.name,
                url=cinema.url,
                photo="old.png",
                photo_width=100,
                photo_height=200,
            )

            reloaded = get_by_slug("capitolio")
            updated = update(reloaded, name=reloaded.name, url=reloaded.url)

            assert updated.photo == "old.png"
            assert updated.photo_width == 100
            assert updated.photo_height == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_cinemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'update' from 'flask_backend.repository.cinemas'`

- [ ] **Step 3: Add the new columns to the `Cinema` model**

In `flask_backend/models.py`, replace the `Cinema` class body:

```python
class Cinema(Base):
    __tablename__ = "cinemas"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    address = Column(String, nullable=True)
    opening_hours = Column(Text, nullable=True)
    instagram_url = Column(String, nullable=True)
    map_embed_url = Column(String, nullable=True)
    photo = Column(String, nullable=True)
    photo_width = Column(Integer, nullable=True)
    photo_height = Column(Integer, nullable=True)

    @property
    def short_name(self) -> str:
        return CINEMA_SHORT_NAMES.get(self.slug, self.name)

    @property
    def color(self) -> str:
        return CINEMA_COLORS.get(self.slug, DEFAULT_CINEMA_COLOR)
```

`Text` is already imported at the top of `flask_backend/models.py` — no import changes needed.

- [ ] **Step 4: Generate the migration**

Run: `flask --app flask_backend db-revision --autogenerate -m "add cinema profile fields"`

This creates a new file under `migrations/versions/` named `<revision>_add_cinema_profile_fields.py`. Open it and:

1. Rename it to `migrations/versions/20260727_000001_add_cinema_profile_fields.py`.
2. Edit its `revision`/`down_revision` so it chains onto the current head — check the current head first with `flask --app flask_backend db-history` (expected head going in: `20260727_000000`, the `add_movies_pipeline_run_id` migration). Set `revision = "20260727_000001"`, `down_revision = "20260727_000000"`.
3. Replace the autogenerated docstring with one matching the existing convention (see `migrations/versions/20260727_000000_add_movies_pipeline_run_id.py`):

```python
"""Adds cinema profile fields (address, opening hours, Instagram, map
embed, photo) so /cinemas/<slug> can show venue info - see
docs/superpowers/specs/2026-07-27-cinema-pages-design.md.

Revision ID: 20260727_000001
Revises: 20260727_000000
Create Date: 2026-07-27 00:00:01.000000

"""
```

4. Verify `upgrade()`/`downgrade()` add/drop exactly these seven nullable columns on `cinemas`: `address` (String), `opening_hours` (Text), `instagram_url` (String), `map_embed_url` (String), `photo` (String), `photo_width` (Integer), `photo_height` (Integer). It should look like:

```python
def upgrade() -> None:
    op.add_column("cinemas", sa.Column("address", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("opening_hours", sa.Text(), nullable=True))
    op.add_column("cinemas", sa.Column("instagram_url", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("map_embed_url", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("photo", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("photo_width", sa.Integer(), nullable=True))
    op.add_column("cinemas", sa.Column("photo_height", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("cinemas", "photo_height")
    op.drop_column("cinemas", "photo_width")
    op.drop_column("cinemas", "photo")
    op.drop_column("cinemas", "map_embed_url")
    op.drop_column("cinemas", "instagram_url")
    op.drop_column("cinemas", "opening_hours")
    op.drop_column("cinemas", "address")
```

If autogenerate emitted anything else (e.g. batch mode wrapping, different column ordering), leave its mechanics intact but confirm the columns/types/nullability match the above exactly.

- [ ] **Step 5: Add `update()` to the cinemas repository**

In `flask_backend/repository/cinemas.py`, add below the existing functions:

```python
def update(
    cinema: Cinema,
    name: str,
    url: str,
    address: Optional[str] = None,
    opening_hours: Optional[str] = None,
    instagram_url: Optional[str] = None,
    map_embed_url: Optional[str] = None,
    photo: Optional[str] = None,
    photo_width: Optional[int] = None,
    photo_height: Optional[int] = None,
) -> Cinema:
    cinema.name = name
    cinema.url = url
    cinema.address = address
    cinema.opening_hours = opening_hours
    cinema.instagram_url = instagram_url
    cinema.map_embed_url = map_embed_url
    if photo:
        cinema.photo = photo
        cinema.photo_width = photo_width
        cinema.photo_height = photo_height
    db_session.add(cinema)
    db_session.commit()
    db_session.refresh(cinema)
    return cinema
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_cinemas.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Run the full test suite**

Run: `pytest flask_backend/tests`
Expected: PASS — confirms the migration doesn't break `init_db()` for any other test relying on the `cinemas` table.

- [ ] **Step 8: Commit**

```bash
git add flask_backend/models.py flask_backend/repository/cinemas.py \
        migrations/versions/20260727_000001_add_cinema_profile_fields.py \
        flask_backend/tests/test_repository/test_cinemas.py
git commit -m "feat: add cinema profile fields (address, hours, instagram, map, photo)"
```

---

### Task 2: Repository — past movies with exclusivity flag

**Files:**
- Modify: `flask_backend/repository/screenings.py`
- Test: Modify `flask_backend/tests/test_repository/test_screenings.py`

**Interfaces:**
- Consumes: `Movie`, `Screening`, `ScreeningDate` models; the existing `_create_screening(app, title, slug, dates, draft=False, cinema_slug="capitolio", movie_id=None)` test helper already defined at the top of `test_screenings.py`.
- Produces: `get_past_movies_for_cinema(cinema_id: int) -> List[Tuple[Movie, bool]]` — a list of `(movie, is_exclusive)` pairs, used by Task 3's `cinema.show` route. `is_exclusive` is `True` when the movie has never screened at any other cinema.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_repository/test_screenings.py`:

```python
from flask_backend.repository.screenings import (  # noqa: keep existing imports, add this name
    get_past_movies_for_cinema,
)


class TestGetPastMoviesForCinema:
    def test_includes_movie_with_only_a_past_date(self, app, setup_cinemas):
        screening_id, movie_id = _create_screening(
            app, "Filme Antigo", "filme-antigo", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            result = get_past_movies_for_cinema(
                get_cinema_by_slug("capitolio").id
            )
            movie_ids = [movie.id for movie, _exclusive in result]
            assert movie_id in movie_ids

    def test_excludes_movie_with_an_upcoming_date_at_this_cinema(
        self, app, setup_cinemas
    ):
        screening_id, movie_id = _create_screening(
            app, "Filme Futuro", "filme-futuro", [date.today() + timedelta(days=1)]
        )

        with app.app_context():
            result = get_past_movies_for_cinema(
                get_cinema_by_slug("capitolio").id
            )
            movie_ids = [movie.id for movie, _exclusive in result]
            assert movie_id not in movie_ids

    def test_marks_movie_screened_only_here_as_exclusive(self, app, setup_cinemas):
        _screening_id, movie_id = _create_screening(
            app, "Exclusivo", "exclusivo", [date.today() - timedelta(days=1)]
        )

        with app.app_context():
            result = get_past_movies_for_cinema(
                get_cinema_by_slug("capitolio").id
            )
            exclusivity_by_id = {movie.id: exclusive for movie, exclusive in result}
            assert exclusivity_by_id[movie_id] is True

    def test_marks_movie_screened_elsewhere_as_not_exclusive(
        self, app, setup_cinemas
    ):
        _screening_id, movie_id = _create_screening(
            app, "Compartilhado", "compartilhado", [date.today() - timedelta(days=2)]
        )
        _create_screening(
            app,
            "Compartilhado",
            "compartilhado",
            [date.today() - timedelta(days=1)],
            cinema_slug="sala-redencao",
            movie_id=movie_id,
        )

        with app.app_context():
            result = get_past_movies_for_cinema(
                get_cinema_by_slug("capitolio").id
            )
            exclusivity_by_id = {movie.id: exclusive for movie, exclusive in result}
            assert exclusivity_by_id[movie_id] is False
```

This new class needs `get_cinema_by_slug` in scope — the file already imports it as `from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug` (see line 5 of the existing file). Add the `get_past_movies_for_cinema` import to that same top-of-file import block instead of a separate inline import — i.e. edit the existing:

```python
from flask_backend.repository.screenings import (
    get_latest_screening_for_movie,
    get_screening_dates_for_movies,
    get_screenings_for_movies_with_dates_in_range,
    get_screenings_in_date_range,
    get_screenings_with_upcoming_dates,
)
```

to also include `get_past_movies_for_cinema` in that alphabetized list.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v -k PastMoviesForCinema`
Expected: FAIL — `ImportError: cannot import name 'get_past_movies_for_cinema'`

- [ ] **Step 3: Implement `get_past_movies_for_cinema`**

In `flask_backend/repository/screenings.py`, add `Movie` to the model import (`from flask_backend.models import Cinema, Movie, Screening, ScreeningDate`), then add:

```python
def get_past_movies_for_cinema(cinema_id: int) -> List[Tuple[Movie, bool]]:
    """Distinct movies with a Screening at this cinema and no upcoming
    ScreeningDate here, paired with whether the movie has ever screened
    at another cinema too (False) or only ever at this one (True)."""
    today = date.today()

    upcoming_movie_ids = {
        movie_id
        for (movie_id,) in (
            db_session.query(Screening.movie_id)
            .join(ScreeningDate)
            .filter(Screening.cinema_id == cinema_id)
            .filter(func.date(ScreeningDate.date) >= today)
            .distinct()
        )
    }

    past_movie_rows = (
        db_session.query(Movie, func.max(ScreeningDate.date).label("last_shown"))
        .join(Screening, Screening.movie_id == Movie.id)
        .join(ScreeningDate, ScreeningDate.screening_id == Screening.id)
        .filter(Screening.cinema_id == cinema_id)
        .group_by(Movie.id)
        .order_by(func.max(ScreeningDate.date).desc())
        .all()
    )

    exclusive_movie_ids = {
        movie_id
        for (movie_id,) in (
            db_session.query(Screening.movie_id)
            .group_by(Screening.movie_id)
            .having(func.count(func.distinct(Screening.cinema_id)) == 1)
        )
    }

    return [
        (movie, movie.id in exclusive_movie_ids)
        for movie, _last_shown in past_movie_rows
        if movie.id not in upcoming_movie_ids
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py -v -k PastMoviesForCinema`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest flask_backend/tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/tests/test_repository/test_screenings.py
git commit -m "feat: add get_past_movies_for_cinema repository query"
```

---

### Task 3: Public cinema pages

**Files:**
- Create: `flask_backend/routes/cinema.py`
- Modify: `flask_backend/__init__.py:56-60` (register the new blueprint)
- Create: `flask_backend/templates/cinema/index.html`
- Create: `flask_backend/templates/cinema/show.html`
- Modify: `flask_backend/templates/base.html` (nav — both the mobile block around lines 116-146 and the desktop block around lines 184-217)
- Test: `flask_backend/tests/test_routes/test_cinema.py` (new file)

**Interfaces:**
- Consumes: `repository.cinemas.get_all()`, `repository.cinemas.get_by_slug(slug)` (existing), `repository.screenings.get_screenings_with_upcoming_dates(cinema_id=...)` (existing), `repository.screenings.get_past_movies_for_cinema(cinema_id)` (Task 2).
- Produces: routes `cinema.index` (`GET /cinemas`) and `cinema.show` (`GET /cinemas/<slug>`, 404 on unknown slug) — Task 4's admin templates link back to `cinema.show` for a "view live page" link, matching the `blog.show` pattern in `templates/blog/admin/edit.html:128-130`.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_routes/test_cinema.py`:

```python
"""
Tests the basic functionality of /cinemas and /cinemas/<slug> endpoints.
"""

from datetime import date, datetime, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


def _create_screening(app, title, slug, screening_date, cinema_slug="capitolio"):
    with app.app_context():
        movie = Movie(title=title, slug=slug, created_at=datetime.now())
        db_session.add(movie)
        db_session.commit()
        cinema = get_cinema_by_slug(cinema_slug)
        screening = Screening(
            movie_id=movie.id, cinema_id=cinema.id, description="desc", draft=False
        )
        db_session.add(screening)
        db_session.commit()
        db_session.add(
            ScreeningDate(screening_id=screening.id, date=screening_date, time="20:00")
        )
        db_session.commit()


class TestCinemaIndex:
    def test_returns_200_and_lists_cinemas(self, client, setup_cinemas):
        response = client.get("/cinemas")
        assert response.status_code == 200
        assert "Cinemateca Capitólio" in response.get_data(as_text=True)


class TestCinemaShow:
    def test_returns_200_for_known_slug(self, client, setup_cinemas):
        response = client.get("/cinemas/capitolio")
        assert response.status_code == 200

    def test_returns_404_for_unknown_slug(self, client, setup_cinemas):
        response = client.get("/cinemas/does-not-exist")
        assert response.status_code == 404

    def test_shows_upcoming_and_past_movies(self, app, client, setup_cinemas):
        _create_screening(
            app, "Filme Futuro", "filme-futuro", date.today() + timedelta(days=1)
        )
        _create_screening(
            app, "Filme Antigo", "filme-antigo", date.today() - timedelta(days=1)
        )

        response = client.get("/cinemas/capitolio")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Filme Futuro" in body
        assert "Filme Antigo" in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_cinema.py -v`
Expected: FAIL — 404s / connection errors, since no `cinema` blueprint or routes exist yet (`/cinemas` isn't registered).

- [ ] **Step 3: Create the `cinema` blueprint**

Create `flask_backend/routes/cinema.py`:

```python
from flask import Blueprint, abort, render_template

from flask_backend.repository.cinemas import get_all, get_by_slug
from flask_backend.repository.screenings import (
    get_past_movies_for_cinema,
    get_screenings_with_upcoming_dates,
)

bp = Blueprint("cinema", __name__)


@bp.route("/cinemas")
def index():
    cinemas = get_all()
    return render_template("cinema/index.html", cinemas=cinemas)


@bp.route("/cinemas/<slug>")
def show(slug):
    cinema = get_by_slug(slug)
    if cinema is None:
        abort(404)

    upcoming_screenings = get_screenings_with_upcoming_dates(cinema_id=cinema.id)
    past_movies = get_past_movies_for_cinema(cinema.id)

    return render_template(
        "cinema/show.html",
        cinema=cinema,
        upcoming_screenings=upcoming_screenings,
        past_movies=past_movies,
    )
```

- [ ] **Step 4: Register the blueprint**

In `flask_backend/__init__.py`, after the existing `movie` blueprint registration (currently lines 56-58) and before the `blog` blueprint registration, add:

```python
    from .routes import cinema

    app.register_blueprint(cinema.bp)
```

- [ ] **Step 5: Create the cinema list template**

Create `flask_backend/templates/cinema/index.html`:

```html
{% extends "base.html" %}
{% block meta_tags %}
    <meta name="description"
          content="Conheça as salas de cinema alternativo de Porto Alegre: {{ cinemas | map(attribute='name') | join(', ') }}.">
{% endblock meta_tags %}
{% block title %}
    Cinemas
{% endblock title %}
{% block header %}
    <h1>Cinemas</h1>
    <p>Salas de cinema alternativo em Porto Alegre.</p>
{% endblock header %}
{% block content %}
    <div class="row">
        {% for cinema in cinemas %}
            <div class="col-md-6 col-lg-4 mb-4">
                <article class="card h-100">
                    {% if cinema.photo %}
                        {# djlint:off #}
                        <img src="{{ cinema.photo }}"
                             class="card-img-top"
                             loading="lazy"
                             alt="{{ cinema.name }}"
                             style="height: 200px;
                                    object-fit: cover;
                                    object-position: top center">
                        {# djlint:on #}
                    {% else %}
                        {# djlint:off #}
                        <div class="card-img-top d-flex align-items-center justify-content-center"
                             style="height: 200px; background-color: {{ cinema.color }};">
                            <span class="text-white fs-4">{{ cinema.short_name }}</span>
                        </div>
                        {# djlint:on #}
                    {% endif %}
                    <div class="card-body d-flex flex-column">
                        <h5 class="card-title">
                            <a href="{{ url_for('cinema.show', slug=cinema.slug) }}"
                               class="text-decoration-none">{{ cinema.name }}</a>
                        </h5>
                        {% if cinema.address %}<p class="card-text text-muted flex-grow-1">{{ cinema.address }}</p>{% endif %}
                    </div>
                </article>
            </div>
        {% endfor %}
    </div>
{% endblock content %}
```

- [ ] **Step 6: Create the cinema detail template**

Create `flask_backend/templates/cinema/show.html`:

```html
{% extends "base.html" %}
{% block meta_tags %}
    <meta name="description"
          content="{{ cinema.name }}: programação, endereço e informações sobre esta sala de cinema em Porto Alegre.">
{% endblock meta_tags %}
{% block title %}
    {{ cinema.name }}
{% endblock title %}
{% block header %}
    {% if cinema.photo %}
        {# djlint:off #}
        <img src="{{ cinema.photo }}"
             class="img-fluid rounded mb-3"
             alt="{{ cinema.name }}"
             style="max-height: 300px; width: 100%; object-fit: cover;">
        {# djlint:on #}
    {% endif %}
    <h1>{{ cinema.name }}</h1>
    {% if cinema.address %}<p class="mb-1">{{ cinema.address }}</p>{% endif %}
    {% if cinema.opening_hours %}<p class="mb-1 text-muted">{{ cinema.opening_hours }}</p>{% endif %}
    <p>
        <a href="{{ cinema.url }}">Visite o site</a>
        {% if cinema.instagram_url %} · <a href="{{ cinema.instagram_url }}">Instagram</a>{% endif %}
    </p>
    {% if cinema.map_embed_url %}
        <div class="ratio ratio-16x9 mb-3">
            <iframe src="{{ cinema.map_embed_url }}" loading="lazy" allowfullscreen></iframe>
        </div>
    {% endif %}
{% endblock header %}
{% block content %}
    <h2>Em cartaz</h2>
    {% if upcoming_screenings %}
        <div class="row mb-5">
            {% for screening in upcoming_screenings %}
                <div class="col-md-6 col-lg-4 mb-4">
                    <article class="card h-100">
                        {% if screening.image %}
                            {# djlint:off #}
                            <img src="{{ screening.image }}"
                                 class="card-img-top"
                                 loading="lazy"
                                 alt="{{ screening.image_alt or screening.movie.title }}"
                                 style="height: 250px;
                                        object-fit: cover;
                                        object-position: top center">
                            {# djlint:on #}
                        {% endif %}
                        <div class="card-body">
                            <h5 class="card-title">{{ screening.movie.title }}</h5>
                        </div>
                    </article>
                </div>
            {% endfor %}
        </div>
    {% else %}
        <p class="text-muted mb-5">Nenhuma sessão futura cadastrada.</p>
    {% endif %}
    <h2>Já passou por aqui</h2>
    {% if past_movies %}
        <div class="row">
            {% for movie, exclusive in past_movies %}
                <div class="col-md-6 col-lg-4 mb-4">
                    <article class="card h-100">
                        <div class="card-body">
                            <h5 class="card-title">
                                {{ movie.title }}
                                {% if exclusive %}
                                    <span class="badge rounded-pill"
                                          style="background-color: {{ cinema.color }}">exclusivo</span>
                                {% endif %}
                            </h5>
                        </div>
                    </article>
                </div>
            {% endfor %}
        </div>
    {% else %}
        <p class="text-muted">Nenhum filme exibido até o momento.</p>
    {% endif %}
{% endblock content %}
```

- [ ] **Step 7: Add the "Cinemas" nav tab**

In `flask_backend/templates/base.html`, mobile nav block: right after the "Programação" `<li>` (currently lines 122-125) and before the "Acervo" dropdown `<li>`, add:

```html
                    <li class="nav-item">
                        <a class="nav-link {% if request.path == url_for('cinema.index') %}active{% endif %}"
                           href="{{ url_for("cinema.index") }}">Cinemas</a>
                    </li>
```

Desktop nav block: right after the "Programação" `<li>` + `<div class="vr mx-3"></div>` pair (currently lines 190-194) and before the "Acervo" dropdown `<li>`, add:

```html
                <li class="nav-item">
                    <a class="nav-link {% if request.path == url_for('cinema.index') %}active{% endif %}"
                       href="{{ url_for("cinema.index") }}">Cinemas</a>
                </li>
                <div class="vr mx-3"></div>
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_cinema.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Run the base-template test and the full suite**

Run: `pytest flask_backend/tests/test_routes/test_base_template.py flask_backend/tests -v`
Expected: PASS — `test_base_template.py` exercises nav rendering broadly, so it's the fastest signal if the new `<li>` breaks Jinja parsing.

- [ ] **Step 10: Commit**

```bash
git add flask_backend/routes/cinema.py flask_backend/__init__.py \
        flask_backend/templates/cinema/index.html flask_backend/templates/cinema/show.html \
        flask_backend/templates/base.html flask_backend/tests/test_routes/test_cinema.py
git commit -m "feat: add public /cinemas and /cinemas/<slug> pages"
```

---

### Task 4: Admin cinema editing

**Files:**
- Create: `flask_backend/routes/admin/cinemas.py`
- Modify: `flask_backend/__init__.py:68-76` (register the new blueprint)
- Create: `flask_backend/templates/cinema/admin/index.html`
- Create: `flask_backend/templates/cinema/admin/update.html`
- Modify: `flask_backend/templates/base.html` (Admin dropdown — both mobile ~lines 154-174 and desktop ~lines 225-245)
- Test: `flask_backend/tests/test_routes/test_admin/test_admin_cinemas.py` (new file)

**Interfaces:**
- Consumes: `repository.cinemas.get_all()`, `repository.cinemas.get_by_id(id)` (existing), `repository.cinemas.update(...)` (Task 1), `service.screening.validate_image(file)` / `service.screening.save_image(file, app)` (existing, reused as-is), `routes.auth.login_required` (existing).
- Produces: routes `admin_cinemas.index` (`GET /admin/cinemas`) and `admin_cinemas.update` (`GET|POST /admin/cinemas/<int:cinema_id>/update`), both `@login_required`.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_routes/test_admin/test_admin_cinemas.py`:

```python
"""
Tests the basic functionality of /admin/cinemas/* endpoints.
"""

import io
from unittest.mock import patch

from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


class TestAdminCinemasIndex:
    def test_requires_login(self, client, setup_cinemas):
        response = client.get("/admin/cinemas")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200(self, auth_headers, setup_cinemas):
        response = auth_headers.get("/admin/cinemas")
        assert response.status_code == 200


class TestAdminCinemaUpdate:
    def test_requires_login(self, app, client, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id
        response = client.get(f"/admin/cinemas/{cinema_id}/update")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_unknown_id(self, auth_headers, setup_cinemas):
        response = auth_headers.get("/admin/cinemas/9999/update")
        assert response.status_code == 404

    def test_updates_profile_fields(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id

        response = auth_headers.post(
            f"/admin/cinemas/{cinema_id}/update",
            data={
                "name": "Cinemateca Capitólio",
                "url": "http://www.capitolio.org.br/",
                "address": "Rua dos Andradas, 736",
                "opening_hours": "Ter-Dom, 14h-22h",
                "instagram_url": "https://instagram.com/cinemateca.capitolio",
                "map_embed_url": "https://www.google.com/maps/embed?pb=example",
            },
        )

        assert response.status_code == 302
        with app.app_context():
            updated = get_cinema_by_slug("capitolio")
            assert updated.address == "Rua dos Andradas, 736"
            assert updated.opening_hours == "Ter-Dom, 14h-22h"
            assert updated.instagram_url == "https://instagram.com/cinemateca.capitolio"

    def test_missing_name_shows_error(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id

        response = auth_headers.post(
            f"/admin/cinemas/{cinema_id}/update",
            data={"name": "", "url": "http://www.capitolio.org.br/"},
        )

        assert response.status_code == 200
        assert "obrigatório" in response.get_data(as_text=True)

    def test_uploads_photo(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id

        with (
            patch(
                "flask_backend.routes.admin.cinemas.validate_image",
                return_value=(True, None),
            ),
            patch(
                "flask_backend.routes.admin.cinemas.save_image",
                return_value=("photo.jpg", 100, 200),
            ),
        ):
            response = auth_headers.post(
                f"/admin/cinemas/{cinema_id}/update",
                data={
                    "name": "Cinemateca Capitólio",
                    "url": "http://www.capitolio.org.br/",
                    "cinema_photo": (io.BytesIO(b"fake-image-bytes"), "photo.jpg"),
                },
                content_type="multipart/form-data",
            )

        assert response.status_code == 302
        with app.app_context():
            updated = get_cinema_by_slug("capitolio")
            assert updated.photo == "photo.jpg"
            assert updated.photo_width == 100
            assert updated.photo_height == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_cinemas.py -v`
Expected: FAIL — no `/admin/cinemas` route registered yet (404s where 302/200 is expected).

- [ ] **Step 3: Create the `admin_cinemas` blueprint**

Create `flask_backend/routes/admin/cinemas.py`:

```python
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from flask_backend.repository.cinemas import (
    get_all,
    get_by_id,
    update as update_cinema,
)
from flask_backend.routes.auth import login_required
from flask_backend.service.screening import save_image, validate_image

bp = Blueprint("admin_cinemas", __name__)


@bp.route("/admin/cinemas")
@login_required
def index():
    """Admin cinema list, for picking one to edit."""
    cinemas = get_all()
    return render_template("cinema/admin/index.html", cinemas=cinemas)


@bp.route("/admin/cinemas/<int:cinema_id>/update", methods=("GET", "POST"))
@login_required
def update(cinema_id):
    cinema = get_by_id(cinema_id)
    if cinema is None:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        url_value = request.form.get("url", "").strip()
        address = request.form.get("address", "").strip()
        opening_hours = request.form.get("opening_hours", "").strip()
        instagram_url = request.form.get("instagram_url", "").strip()
        map_embed_url = request.form.get("map_embed_url", "").strip()
        error = None

        if not name:
            error = "O nome do cinema é obrigatório."
        if not url_value:
            error = "O site do cinema é obrigatório."

        photo = None
        photo_width = None
        photo_height = None
        cinema_photo = request.files.get("cinema_photo", None)
        if cinema_photo and cinema_photo.filename:
            img_is_valid, message = validate_image(cinema_photo)
            if img_is_valid:
                photo, photo_width, photo_height = save_image(
                    cinema_photo, current_app
                )
            else:
                error = message

        if error is not None:
            flash(error, "danger")
        else:
            update_cinema(
                cinema,
                name=name,
                url=url_value,
                address=address or None,
                opening_hours=opening_hours or None,
                instagram_url=instagram_url or None,
                map_embed_url=map_embed_url or None,
                photo=photo,
                photo_width=photo_width,
                photo_height=photo_height,
            )
            flash(f"Cinema «{name}» atualizado com sucesso!", "success")
            return redirect(url_for("admin_cinemas.update", cinema_id=cinema_id))

    return render_template(
        "cinema/admin/update.html",
        cinema=cinema,
        max_file_size=current_app.config["MAX_CONTENT_LENGTH"],
    )
```

- [ ] **Step 4: Register the blueprint**

In `flask_backend/__init__.py`, after the existing `admin_pipelines` blueprint registration (currently lines 72-74) and before the `page` blueprint registration, add:

```python
    from .routes.admin import cinemas as admin_cinemas

    app.register_blueprint(admin_cinemas.bp)
```

- [ ] **Step 5: Create the admin cinema list template**

Create `flask_backend/templates/cinema/admin/index.html`:

```html
{% extends "base.html" %}
{% block title %}
    Gerenciar Cinemas
{% endblock title %}
{% block header %}
    <h1>Gerenciar Cinemas</h1>
{% endblock header %}
{% block content %}
    <ul class="list-group">
        {% for cinema in cinemas %}
            <li class="list-group-item d-flex justify-content-between align-items-center">
                {{ cinema.name }}
                <a class="btn btn-sm btn-secondary"
                   href="{{ url_for('admin_cinemas.update', cinema_id=cinema.id) }}">Editar</a>
            </li>
        {% endfor %}
    </ul>
{% endblock content %}
```

- [ ] **Step 6: Create the admin cinema edit template**

Create `flask_backend/templates/cinema/admin/update.html`:

```html
{% extends "base.html" %}
{% block title %}
    Editar {{ cinema.name }}
{% endblock title %}
{% block header %}
    <nav aria-label="breadcrumb">
        <ol class="breadcrumb">
            <li class="breadcrumb-item">
                <a href="{{ url_for("admin_cinemas.index") }}">Cinemas</a>
            </li>
            <li class="breadcrumb-item active" aria-current="page">Editar {{ cinema.name }}</li>
        </ol>
    </nav>
    <h1>Editar {{ cinema.name }}</h1>
{% endblock header %}
{% block content %}
    <form method="post" enctype="multipart/form-data">
        <div class="mb-3">
            <label class="form-label" for="name">Nome</label>
            <input class="form-control"
                   id="name"
                   name="name"
                   value="{{ request.form.get('name', cinema.name) }}"
                   required>
        </div>
        <div class="mb-3">
            <label class="form-label" for="url">Site</label>
            <input class="form-control"
                   type="url"
                   id="url"
                   name="url"
                   value="{{ request.form.get('url', cinema.url) }}"
                   required>
        </div>
        <div class="mb-3">
            <label class="form-label" for="address">Endereço</label>
            <input class="form-control"
                   id="address"
                   name="address"
                   value="{{ request.form.get('address', cinema.address or '') }}">
        </div>
        <div class="mb-3">
            <label class="form-label" for="opening_hours">Horário de funcionamento</label>
            <textarea class="form-control" id="opening_hours" name="opening_hours" rows="2">{{ request.form.get('opening_hours', cinema.opening_hours or '') }}</textarea>
        </div>
        <div class="mb-3">
            <label class="form-label" for="instagram_url">Instagram</label>
            <input class="form-control"
                   type="url"
                   id="instagram_url"
                   name="instagram_url"
                   value="{{ request.form.get('instagram_url', cinema.instagram_url or '') }}">
        </div>
        <div class="mb-3">
            <label class="form-label" for="map_embed_url">URL de incorporação do Google Maps</label>
            <input class="form-control"
                   type="url"
                   id="map_embed_url"
                   name="map_embed_url"
                   value="{{ request.form.get('map_embed_url', cinema.map_embed_url or '') }}">
            <div class="form-text">
                No Google Maps, use "Compartilhar" → "Incorporar um mapa" e cole aqui a URL do atributo src do iframe.
            </div>
        </div>
        <div class="mb-3">
            <label class="form-label" for="cinema_photo">Foto</label>
            {% if cinema.photo %}
                {# djlint:off #}
                <img src="{{ cinema.photo }}"
                     alt="{{ cinema.name }}"
                     class="d-block mb-2"
                     style="max-height: 150px;">
                {# djlint:on #}
            {% endif %}
            <input class="form-control"
                   type="file"
                   id="cinema_photo"
                   name="cinema_photo"
                   accept="image/*">
        </div>
        <div class="container mb-3 pb-3">
            <input class="btn btn-primary" type="submit" value="Salvar">
            <a class="btn btn-secondary" href="{{ url_for("admin_cinemas.index") }}">Voltar</a>
        </div>
    </form>
{% endblock content %}
```

- [ ] **Step 7: Add "Cinemas" to the Admin nav dropdown**

In `flask_backend/templates/base.html`, mobile Admin dropdown block: right after the "Alertas" `<li>` (currently lines 159-162) add:

```html
                                <li>
                                    <a class="dropdown-item {% if request.path.startswith('/admin/cinemas') %}active{% endif %}"
                                       href="{{ url_for("admin_cinemas.index") }}">Cinemas</a>
                                </li>
```

Desktop Admin dropdown block: right after the "Alertas" `<li>` (currently lines 230-233) add the same markup (only indentation differs).

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_cinemas.py -v`
Expected: PASS (6 tests)

- [ ] **Step 9: Run the full test suite**

Run: `pytest flask_backend/tests`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add flask_backend/routes/admin/cinemas.py flask_backend/__init__.py \
        flask_backend/templates/cinema/admin/index.html flask_backend/templates/cinema/admin/update.html \
        flask_backend/templates/base.html flask_backend/tests/test_routes/test_admin/test_admin_cinemas.py
git commit -m "feat: add admin UI for editing cinema profile info"
```

---

### Task 5: Lint, format, and final verification

**Files:** none created — this task only runs formatters/linters and fixes anything they flag across the files touched in Tasks 1-4.

**Interfaces:** none — verification-only task.

- [ ] **Step 1: Run ruff**

Run: `uv run ruff check --fix`
Fix any remaining issues it reports manually, re-running until clean.

- [ ] **Step 2: Run ruff format**

Run: `uv run ruff format`

- [ ] **Step 3: Lint templates**

Run: `uv run djlint flask_backend/templates --lint --profile=jinja`
Fix any issues in the four new templates (`cinema/index.html`, `cinema/show.html`, `cinema/admin/index.html`, `cinema/admin/update.html`) and the edited `base.html`.

- [ ] **Step 4: Format templates**

Run: `uv run djlint --reformat flask_backend/templates --format-css --format-js`

- [ ] **Step 5: Run the full test suite one more time**

Run: `pytest flask_backend/tests`
Expected: PASS

- [ ] **Step 6: Commit any formatting changes**

```bash
git add -u
git commit -m "chore: lint and format cinema pages"
```

If there's nothing to commit (formatters made no changes), skip this step.
