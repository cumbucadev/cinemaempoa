# Cinema-Aware Title Collision Resolution on Import (#316) Design

## Problem

`get_by_title_or_create` (`flask_backend/repository/movies.py`) resolves an
incoming scraped title purely by `slugify(title)`. When a title collides with
an existing movie's base slug (e.g. "Noite" -> `noite`), the importer always
attaches the new screening to that first movie, even when a *different* film
with the same title was manually disambiguated earlier via `create_distinct`
(e.g. `noite-2`, added in #292/#315). If the disambiguated movie already has a
screening at the incoming cinema, the importer still creates a *new*,
redundant screening on the wrong movie instead of recognizing the match.

Observed case (production, see issue #316): movie `noite` (dir. Gilberto
Loureiro) has a screening at Capitólio. Movie `noite-2` (a different film) was
manually disambiguated and already has a screening at Sala Redenção. A later
scrape of Sala Redenção's "Noite" listing creates a brand-new screening
attached to `noite` instead of updating `noite-2`'s existing Sala Redenção
screening.

## Goals

- When a title collides with an existing movie's slug family (base slug +
  numeric-suffixed disambiguations), and exactly one movie in that family
  already has a screening at the incoming cinema, attach the new screening to
  that movie instead of blindly using the base slug.
- When the collision can't be resolved this way (no family member has a
  screening at that cinema, or — pathologically — more than one does), keep
  today's behavior (attach to the base-slug movie, publish normally) but flag
  it for admin review, since a human already has a working escape hatch
  (`force_new_movie` / trocar-filme) to fix it.
- No new UI, tables, or migrations.

## Non-goals

- Extending `dupe-check` / `run-dedupper` to also report title-family
  collisions. The pipeline-run summary flag (below) is a sufficient review
  surface for now; revisit only if it proves inadequate in practice.
- Changing `dedupper()`'s exact-slug grouping — it already correctly leaves
  disambiguated-slug movies alone (locked in by the #292 regression test).
- Any change to the manual trocar-filme / `force_new_movie` flow — it's the
  existing fix-up path for whatever this design flags.

## Design

### 1. Sibling-aware resolution in `flask_backend/repository/movies.py`

New function `resolve_for_screening`:

```python
def resolve_for_screening(
    title: str, cinema_id: int, pipeline_run_id: Optional[int] = None
) -> Tuple[Movie, bool, bool]:
    """Returns (movie, created, ambiguous)."""
```

Behavior:

1. `slug = slugify(title)`; `base_movie = get_by_slug(slug)`.
2. If `base_movie` is `None`: create it via `create(...)` (today's
   unambiguous path — nothing else can share this slug yet). Returns
   `(movie, True, False)`.
3. If `base_movie` exists, find its disambiguated siblings: movies whose slug
   matches exactly `f"{slug}-{n}"` for integer `n` (the precise pattern
   `create_distinct` produces). This must be an exact-pattern match, not the
   existing `get_movies_with_similar_titles` ilike helper — that helper also
   matches unrelated titles that merely contain the same substring (e.g.
   "Noite" ilike-matches "Noites Paraguayas"), which would break the
   cinema-matching logic below.
4. No siblings found: return `(base_movie, False, False)` — today's behavior,
   still correct because there's no actual collision.
5. Siblings found (a real collision): let
   `candidates = [base_movie, *siblings]`. For each, check
   `get_screening_by_movie_id_and_cinema_id(candidate.id, cinema_id)`
   (existing function, already used in `import_scrapped_results` and
   `dedupper()`).
   - Exactly one candidate has a screening at `cinema_id`: return
     `(that_movie, False, False)` — resolved.
   - Zero or more than one candidate matches: return
     `(base_movie, False, True)` — unresolved, ambiguous.

### 2. Wiring into `import_scrapped_results`

`flask_backend/service/screening.py::import_scrapped_results` currently calls:

```python
movie, movie_created = get_movie_by_title_or_create(
    title_cleaning_result.cleaned_title, pipeline_run_id=pipeline_run_id
)
```

`cinema` is already resolved earlier in the same loop iteration
(`cinema = get_cinema_by_slug(scrapped_cinema.slug)`), so this becomes:

```python
movie, movie_created, ambiguous = resolve_for_screening(
    title_cleaning_result.cleaned_title,
    cinema.id,
    pipeline_run_id=pipeline_run_id,
)
```

When `ambiguous` is `True`, record a dict on a new
`ImportSummary.ambiguous_collisions: List[dict]` field:

```python
{
    "screening_id": <id, filled in after create_screening() if a new
                      screening was created, else the existing screening's id>,
    "title": title_cleaning_result.cleaned_title,
    "cinema": cinema.slug,
    "attached_movie_id": movie.id,
    "candidate_movie_ids": [base_movie.id, *sibling.id for each sibling],
}
```

### 3. Surfacing in the pipeline-run summary

`flask_backend/commands.py::_run_import_json` already builds the JSON
`summary` written to `pipeline_runs` from `ImportSummary`'s fields, and
already sets `status = "warning"` when `features_processed == 0`. Extend
both:

- Add `"ambiguous_collisions": summary.ambiguous_collisions` to the
  `json.dumps(...)` payload (empty list when there were none, matching the
  existing all-fields-always-present convention for the other counters).
- `status = "warning" if features_processed == 0 or summary.ambiguous_collisions else "success"`.

No template changes are needed: `/admin/pipelines` (index and history) and
the per-run detail page already dump `summary` generically via `| tojson`, so
the new key becomes visible immediately, and the "warning" badge (existing
`status_classes`/`status_labels` mapping) makes an ambiguous run visually
distinct from a clean one. An admin can read the `screening_id` straight out
of the JSON and jump to `/screening/<id>/update` to resolve it via the
existing trocar-filme / `force_new_movie` flow.

## Data flow

```
scraped feature (title, cinema)
        |
        v
resolve_for_screening(title, cinema.id)
        |
        +-- no base movie yet -----------------> create; unambiguous
        |
        +-- base movie, no siblings -----------> base movie; unambiguous
        |
        +-- base movie + siblings
                 |
                 +-- exactly one candidate has
                 |   a screening at this cinema -> that movie; unambiguous
                 |
                 +-- zero or >1 candidates match -> base movie; AMBIGUOUS
                                                     (recorded in ImportSummary)
        |
        v
import_scrapped_results proceeds as today (get_screening_by_movie_id_and_cinema_id
on the *resolved* movie, create or update the screening)
        |
        v
_run_import_json writes pipeline_runs.summary including ambiguous_collisions;
status becomes "warning" if non-empty
        |
        v
/admin/pipelines shows the warning badge + raw JSON with screening_id(s) to review
```

## Error handling

- No new failure modes: `resolve_for_screening` always returns a usable
  `Movie` (never raises for the ambiguous case — it falls back to the
  base-slug movie, which is exactly today's behavior, so the pipeline can't
  regress to "worse than before").
- Sibling-slug pattern matching happens in Python (fetch candidates via
  `Movie.slug.like(f"{slug}-%")`, then filter with a regex
  `^{re.escape(slug)}-\d+$`), avoiding a dependency on SQLite's non-standard
  `REGEXP` operator.

## Testing

- `flask_backend/tests/test_repository/test_movies.py`: new
  `TestResolveForScreening` class covering:
  - no base movie -> creates, unambiguous.
  - base movie, no siblings -> returns base movie, unambiguous.
  - base movie + one sibling, sibling has the matching-cinema screening ->
    returns sibling, unambiguous.
  - base movie + one sibling, base movie has the matching-cinema screening ->
    returns base movie, unambiguous.
  - base movie + sibling(s), none has a screening at the target cinema ->
    returns base movie, `ambiguous=True`.
  - base movie + sibling(s), more than one has a screening at the target
    cinema -> returns base movie, `ambiguous=True`.
  - a same-substring, unrelated-title movie (e.g. "Noites Paraguayas" next to
    "Noite") is never treated as a sibling.
- `flask_backend/tests/test_service/test_screening.py`: integration-style
  test reproducing the ticket's exact scenario — a `noite` movie with a
  Capitólio screening, a `noite-2` movie with a Sala Redenção screening, then
  `import_scrapped_results` fed a new "Noite" listing for Sala Redenção;
  assert the screening lands on `noite-2` (no duplicate created on `noite`).
  A second test for the unresolved case asserts `ImportSummary.ambiguous_collisions`
  is populated and the screening still lands on the base movie (unchanged
  behavior for that branch).
- `flask_backend/tests/test_service/test_commands.py`: assert the
  `pipeline_runs.summary` JSON includes `ambiguous_collisions` and that
  `status` is `"warning"` when non-empty.
