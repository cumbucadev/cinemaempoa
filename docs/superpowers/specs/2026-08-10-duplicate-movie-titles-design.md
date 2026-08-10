# Handling movie title conflicts (#292)

## Problem

`Movie.slug` (derived from `slugify(title)`) is used as the de facto identity
key for a film everywhere in the app: find-or-create on import
(`repository/movies.get_by_title_or_create`), the public movie page
(`routes/movie.show`, keyed by slug), and the `run-dedupper` auto-merge script
(`scripts/dedupper.py`, which groups movies by exact slug match and merges
them).

Two distinct films can share the same Portuguese release title. When that
happens, they collide onto the same `Movie` row, which can only ever hold one
TMDB association (`tmdb_id`, `original_title`, `release_year`, etc. are all
scalar columns) — so metadata ends up wrong for one of the two films.

The admin "trocar filme" UI on the screening update page
(`templates/screening/update.html`) already has a "Criar novo filme" action
for pointing a screening at a different movie, but it's suppressed whenever a
same-titled movie already exists (`hasExactMatch` check), and even if it
weren't, the backend (`get_by_title_or_create`) would resolve the colliding
slug back to the existing movie rather than creating a new one. There is
currently no way to create a second movie with a title that collides with an
existing one.

Concrete case: "Uma mulher diferente" is the pt-BR title for two different
films that have screened at cinemaempoa — one at Capitólio
(screening 1194), and one at Paulo Amorim / Cinebancários (screenings 325,
329). They're incorrectly grouped under a single `Movie` row today.

## Scope

This fix covers the **admin UI path only**: enabling a logged-in user to
manually create a second, distinct movie for a screening despite a title
collision, from the screening update page.

The **scraper import path** (`service.screening.import_scrapped_results`,
which also calls `get_by_title_or_create`) keeps today's behavior. A fresh
scrape that happens to collide on title with an existing movie will still
auto-attach to it; that gets corrected by hand afterward through this same
admin UI, the same way the existing "Uma mulher diferente" case will be
corrected once this ships. Import-time detection/avoidance of title
collisions is out of scope for this change.

No database migration is required — `Movie.slug` has no uniqueness
constraint at the schema level; only application logic currently assumes one
slug maps to one film.

## Design

### Backend

**New repository function**, `flask_backend/repository/movies.py`, alongside
the existing `create()` / `get_by_title_or_create()`:

```python
def create_distinct(title: str, pipeline_run_id: Optional[int] = None) -> Movie:
    """Always creates a new Movie, even if one with this title/slug already
    exists — disambiguates the slug instead of reusing the existing row."""
    base_slug = slugify(title)
    slug = base_slug
    suffix = 2
    while get_by_slug(slug) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return create(title=title, slug=slug, pipeline_run_id=pipeline_run_id)
```

**Route change**, `flask_backend/routes/screening.py` (`change_movie`,
currently lines 435-461): accept a new boolean field in the JSON payload,
`force_new_movie`. When `new_title` is given together with
`force_new_movie: true`, call `create_distinct(new_title)` instead of
`get_movie_by_title_or_create(new_title)`, then `reattach_movie` as today.
Plain `new_title` without the flag is unchanged.

The numeric-suffix slug (`foo-2`, `foo-3`, ...) is permanent — it is not
upgraded to a year-based slug later when TMDB metadata is fetched. This
keeps the change minimal: one code path decides the slug, once, at creation
time.

**Side effect (no code change, but worth a regression test):** because the
two movies now have genuinely different slugs, `run-dedupper` — which groups
strictly by exact slug match — naturally leaves them alone.

### Frontend

In `flask_backend/templates/screening/update.html`
(`fetchMovieCandidates`, lines 330-355, and its helpers):

- Keep the `hasExactMatch` check, but instead of suppressing the "create new"
  option when there's a match, render a distinct item for that case:
  - No match → existing "Criar novo filme "X"" (unchanged, sends
    `{new_title}`).
  - Exact match found → "Criar um segundo filme "X" (filme diferente)",
    visually distinguished (e.g. warning styling), sends
    `{new_title, force_new_movie: true}`.
- The confirmation text (`showMovieChangeConfirm`, lines 383-390) gets a
  distinct message for the force-create case:
  > "Já existe um filme "X" cadastrado. Isso criará um SEGUNDO filme com o
  > mesmo título — use apenas se forem filmes diferentes. Esta sessão será
  > desvinculada de "{currentMovieTitle}"."

The low-friction path for the common case (no collision) is unchanged; the
force-create path is a clearly-labeled, clearly-worded escape hatch using the
same confirm-before-submit pattern already in the file.

## Testing

- Repository test for `create_distinct`: same title twice → two `Movie` rows;
  second gets a `-2` slug, third gets `-3`.
- Route test for `change_movie` with `force_new_movie: true`: creates a new
  movie even when an exact-title movie exists, and reattaches the screening
  to the *new* movie, not the existing one. Without the flag, behavior is
  unchanged.
- Dedupper regression test: two movies with the same title but disambiguated
  slugs are not merged by `run-dedupper`.

## Fixing the existing "Uma mulher diferente" data

No migration or one-off script. Once this ships, fix it by hand through the
UI: open the Capitólio screening's update page, use "criar um segundo filme,"
then re-run `fetch-movie-metadata` / `movie-metadata-review` to attach the
correct TMDB id to the newly split-off movie.
