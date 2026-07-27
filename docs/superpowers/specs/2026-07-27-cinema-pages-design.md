# Cinema pages — design

Issue: [#74](https://github.com/cumbucadev/cinemaempoa/issues/74) — "Criar página interna de cada cinema"

## Problem

There's no dedicated page per cinema. Visitors unfamiliar with Porto Alegre's
independent cinema scene have no way to learn where a venue is, what it's
about, or browse its catalog (upcoming and past screenings). The only
existing reference is a stale, hardcoded, non-DB-driven list of cinema
websites in `about.html` (missing Cine Cinco), which this work does not
touch.

## Scope

In scope: a public cinema list page, a public per-cinema detail page
(letterboxd-mobile-style), admin-editable venue info (address, hours,
Instagram, map embed, photo), and a new top-level "Cinemas" nav tab.

Out of scope (explicitly deferred): payment methods/prices (mentioned in an
issue comment — skipped because this data goes stale quickly and varies by
day), fixing the stale `about.html` cinema list, creating brand-new cinemas
through the admin UI (the 5 existing rows are edited in place; adding a new
cinema stays a manual DB/seed operation as it is today).

## Data model & migration

Add nullable columns to `Cinema` (`flask_backend/models.py`):

```python
class Cinema(Base):
    __tablename__ = "cinemas"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    address = Column(String, nullable=True)
    opening_hours = Column(Text, nullable=True)       # free-text, e.g. "Ter-Dom, 14h-22h"
    instagram_url = Column(String, nullable=True)
    map_embed_url = Column(String, nullable=True)      # Google Maps iframe src, no API key needed
    photo = Column(String, nullable=True)              # same convention as Screening.image
    photo_width = Column(Integer, nullable=True)
    photo_height = Column(Integer, nullable=True)
```

- New Alembic migration via
  `flask --app flask_backend db-revision --autogenerate -m "add cinema profile fields"`.
- All new columns nullable. No backfill/seed data — the 5 existing cinemas
  keep `NULL` values until filled in through the new admin UI.
- `opening_hours` is one free-text field, not structured per weekday — the
  source data has no more structure than that, and it keeps the admin form
  simple.
- `photo`/`photo_width`/`photo_height` mirror `Screening.image` /
  `image_width` / `image_height` exactly, so the existing
  `service/screening.py` `validate_image`/`save_image` helpers work
  unchanged for the cinema photo upload (local disk in dev, imgBB in
  production, per `APP_ENVIRONMENT`).
- Social media: Instagram only (the platform Porto Alegre's indie cinemas
  actually use) — a single `instagram_url` column, not an open-ended list.

## Repository layer

**`flask_backend/repository/cinemas.py`** — add:

```python
def create(name, slug, url, address=None, opening_hours=None,
           instagram_url=None, map_embed_url=None,
           photo=None, photo_width=None, photo_height=None) -> Cinema: ...

def update(cinema: Cinema, **fields) -> Cinema: ...
```

Mirrors the existing `create`/`update` shape already used in
`repository/screenings.py`.

**Catalog queries**, added to `flask_backend/repository/screenings.py`
(colocated with the other cinema-scoped screening queries):

- Upcoming screenings: reuse the existing
  `get_screenings_with_upcoming_dates(cinema_id=...)` directly — no new
  code needed.
- Past movies with exclusivity flag — new function:

  ```python
  def get_past_movies_for_cinema(cinema_id: int) -> List[Tuple[Movie, bool]]:
      """Distinct movies with a past (or no upcoming) Screening at this
      cinema, paired with whether the movie has ever screened anywhere
      else. Second element is True when exclusive to this cinema."""
  ```

  Implemented as two queries (not N+1): one for distinct `movie_id`s
  screened at `cinema_id` with no future `ScreeningDate`; one grouped query
  (`GROUP BY movie_id HAVING COUNT(DISTINCT cinema_id) = 1`) for the set of
  cinema-exclusive movie IDs across the whole `screenings` table. Combined
  in Python.

## Routes

**Public — `flask_backend/routes/cinema.py`** (new blueprint `cinema`,
registered in `flask_backend/__init__.py` alongside the existing
blueprints):

- `GET /cinemas` — list page, all cinemas via `get_all()`.
- `GET /cinemas/<slug>` — detail page; 404 via `abort(404)` for an unknown
  slug; loads upcoming screenings and past movies via the repository
  functions above.

**Admin — `flask_backend/routes/admin/cinemas.py`** (new blueprint
`admin_cinemas`, every route `@login_required`, matching the
`admin/alerts.py` / `admin/pipelines.py` convention):

- `GET /admin/cinemas` — list with edit links.
- `GET|POST /admin/cinemas/<id>/update` — edit form; POST reads
  `request.form` fields plus an optional `request.files["cinema_photo"]`,
  validated/saved via `validate_image`/`save_image` from
  `service/screening.py`, same as the screening update route.

No admin "create cinema" route — editing existing rows only.

This is a two-blueprint split (public vs. admin), matching the newer
convention the codebase has moved to for admin features (`admin_alerts`,
`admin_pipelines`), rather than mixing public and admin routes into one file
the way the older `screening.py` does.

## Templates & nav

- **`templates/cinema/index.html`** — card grid (`row`/`col-md-6 col-lg-4`,
  following the `blog/index.html` pattern): one card per cinema with photo
  (or the existing `color` badge as fallback when no photo is set), name,
  `short_name` badge, link to the detail page.
- **`templates/cinema/show.html`** — single-column, letterboxd-mobile-style
  layout:
  1. Header: photo banner (or color-badge fallback), name, address,
     opening hours, Instagram icon-link, existing "Visite o site" link
     (`cinema.url`), embedded map (`<iframe src="{{ cinema.map_embed_url }}">`
     — omitted entirely when `NULL`).
  2. "Em cartaz" — upcoming screenings, reusing the screening-card
     markup/partial from `screening/index.html`, filtered to this cinema.
  3. "Já passou por aqui" — past movies grid; movies flagged exclusive by
     the repository query get a small "exclusivo" pill badge, reusing the
     existing color/badge macro pattern.
- **Nav (`templates/base.html`)** — add a "Cinemas" `<li class="nav-item">`
  linking to `cinema.index`, in both the mobile (`#navbar-collapse-9`) and
  desktop nav blocks, as a standalone top-level tab alongside
  Programação/Blog (not nested under "Acervo"). Active-state follows the
  existing `request.path == url_for(...)` convention.

All new fields render conditionally — a cinema with every new column still
`NULL` renders the page with those sections simply omitted, so nothing
breaks before the admin form is used to fill them in.

## Testing

Following existing conventions (the `setup_cinemas` fixture in
`flask_backend/tests/conftest.py` already seeds the 5 production cinemas;
no dedicated cinema tests exist yet, so this establishes the pattern):

- `flask_backend/tests/test_repository/test_cinemas.py` — `create`/`update`,
  and `get_past_movies_for_cinema` (a movie only screened at this cinema →
  exclusive=True; also screened elsewhere → exclusive=False; a movie with
  only future dates → excluded from the past list).
- `flask_backend/tests/test_routes/test_cinema.py` — `/cinemas` returns 200
  and lists all cinemas; `/cinemas/<slug>` returns 200 for a real slug, 404
  for an unknown one; the page renders both the upcoming and past sections.
- `flask_backend/tests/test_routes/test_admin_cinemas.py` — the edit route
  requires login (redirect when `g.user is None`, matching the existing
  `login_required` test pattern); a successful POST updates fields and,
  with a fixture image, `photo`/`photo_width`/`photo_height`.

No scraper tests — this feature doesn't touch `scrapers/`.
