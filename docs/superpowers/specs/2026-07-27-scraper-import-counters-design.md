# Accurate Scraper Import Counters — Design

Issue: [#249](https://github.com/guites/cinemaempoa/issues/249)

## Problem

`import_scrapped_results` (`flask_backend/service/screening.py`) increments a
single `created_features` counter for every scraped feature it processes,
regardless of whether anything actually changed. That number is what ends up
in the `/admin/pipelines` summary JSON (`{"created": 69}`), shown on the
index and history pages.

The detail page, meanwhile, independently and correctly queries real newly
created `Screening` rows via their `pipeline_run_id` FK ("sessões criadas:
0"). The two numbers disagree, which is confusing: a run can report "created:
69" while having created zero new screenings, because it re-processed 69
already-known movies/screenings.

Additionally, for Cinemateca Capitólio specifically, the existing "delete
this day's dates and recreate them" strategy (used because Capitólio may
change a screening's time for an already-scraped day) makes every touched
day look "new," even when the date/time is byte-for-byte unchanged — because
the code currently strips out same-day entries from the comparison set
*before* comparing, rather than after.

## Goal

Distinguish, per pipeline run, three kinds of real change:

1. A **new movie** was created.
2. A **new screening** was created (a movie showing at a cinema it wasn't
   showing at before).
3. An **existing screening** registered a **new date/time** it didn't have
   before.

Feed these three counts into the run summary and into the success/warning
status, replacing the current single misleading counter.

## Non-goals (explicitly out of scope, per discussion)

- No detail-page UI changes. The existing "Sessões criadas" list on the
  detail page is untouched. Movies-created and dates-registered get no
  drill-down list — counts only.
- No change to how dates are stored. `update_screening_dates` keeps its
  current delete-all/recreate-all behavior; no schema change to
  `ScreeningDate`, no `pipeline_run_id` column added there. Counting new
  dates happens in-memory, by comparing the screening's date/time set before
  and after, not by tracking new rows.

## Design

### Movie creation tracking

Add a nullable `pipeline_run_id` FK (indexed) to `movies`, mirroring the
existing pattern on `screenings`, `poster_fetch_attempts`, and
`movie_metadata_fetch_attempts`. Set only when a movie is created by a
tracked pipeline run; `NULL` for movies created manually via `/admin` or
other scripts.

`repository/movies.py`:
- `create(title, slug=None, pipeline_run_id=None)` — new optional param,
  passed straight to the `Movie(...)` constructor.
- `get_by_title_or_create(title, pipeline_run_id=None) -> Tuple[Movie, bool]`
  — return type changes from `Movie` to `(Movie, was_created)`. A bare
  `pipeline_run_id` check on the returned movie isn't reliable as a "was
  this created now" signal by itself, since many callers (tests, and this
  function's two call sites in `routes/screening.py`) never pass a
  `pipeline_run_id` at all — the explicit bool is unambiguous regardless.

The two existing call sites in `routes/screening.py` (manual screening
creation/editing in the admin UI) unpack and discard the new bool:
`movie, _ = get_movie_by_title_or_create(movie_title)`. No other behavior
change for them.

### Screening creation tracking

No change needed. The existing `if not screening:` branch in
`import_scrapped_results` already correctly identifies a brand-new
screening and already tags it with `pipeline_run_id` via `create_screening`.
We just start explicitly counting this branch instead of only relying on
it implicitly.

### New date/time tracking (and the Capitólio fix)

Inside the `else` branch of `import_scrapped_results` (screening already
exists), capture the screening's true pre-update `(date, time)` pairs
**before** any of the existing Capitólio-specific filtering:

```python
original_date_time_pairs = {(sd.date, sd.time) for sd in screening.dates}
```

The rest of the existing branch (Capitólio's delete-and-filter logic for
the storage write, or the plain append logic for other cinemas) is
unchanged. After that logic has produced the final `existing_dates` list
that gets persisted via `update_screening_dates`, compare the *scraped*
dates for this run (`screenings_dates`) against `original_date_time_pairs`:

```python
got_new_date = any(
    (nd.date, nd.time) not in original_date_time_pairs
    for nd in screenings_dates
)
```

If `got_new_date`, increment `dates_registered` by one **per screening**
touched this run (not per individual date row) — matching the issue's
framing of "an exhibition registered a new time," a per-screening event.

This is what fixes the Capitólio false positive: today, the comparison set
has already had the received day's old entry filtered out by the time the
"is this new" check runs, so a same-day/same-time re-scrape always looks
new. Capturing `original_date_time_pairs` up front, before any filtering,
means an unchanged date/time correctly compares as "not new."

### Result shape

`import_scrapped_results` returns a small dataclass instead of a bare int:

```python
@dataclass
class ImportSummary:
    movies_created: int
    screenings_created: int
    dates_registered: int
```

`service/runner.py`'s `Runner.import_scrapped_results` passes this through
unchanged (just a type update).

### Command / status logic

`commands.py::_run_import_json`:

```python
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
    f"«{summary.movies_created}» filmes, «{summary.screenings_created}» "
    f"sessões e «{summary.dates_registered}» novos horários registrados!"
)
```

No other error paths change — invalid JSON, unknown cinema, and exception
handling in `_run_import_json` are untouched.

### `/admin/pipelines` UI

No template changes needed. `index.html` and `history.html` already render
the summary dict generically via `| tojson`; the new key names show up
automatically. The detail page's "Sessões criadas" section (driven by
`get_by_pipeline_run_id`, not the summary JSON) is unaffected and stays as
today.

## Testing plan

- `repository/movies.py` (new tests under `flask_backend/tests/test_repository/`):
  - `get_by_title_or_create` returns `(movie, True)` when no matching slug
    exists, `(movie, False)` when one does.
  - `pipeline_run_id` passed through to the created `Movie` row; omitted
    param leaves it `NULL`.
- `service/screening.py` (`flask_backend/tests/test_service/test_screening.py`):
  - New movie + new screening in one run → `movies_created == 1`,
    `screenings_created == 1`, `dates_registered == 0` (the branch that
    increments `dates_registered` never runs for a freshly created
    screening).
  - Existing movie, existing screening (non-Capitólio cinema), scraped with
    an additional date not seen before → `dates_registered == 1`,
    other two counters `0`.
  - **Regression test:** Capitólio, existing screening, re-scraped with the
    exact same date/time as before → `dates_registered == 0`.
  - Capitólio, existing screening, one date's time actually changes →
    `dates_registered == 1`.
  - Fully idempotent re-run of an identical payload → all three counters
    `0`.
- `service/runner.py` (`test_runner.py`): update the mocked
  `import_scrapped_results` return value from the bare int `5` to an
  `ImportSummary(...)` instance; assert the dataclass passes through
  unchanged.
- `test_commands.py`:
  - `test_success_creates_pipeline_run_with_source_and_summary`: replace the
    `'"created": 1'` assertion with checks for `'"movies_created": 1'` and
    `'"screenings_created": 1'` (and `dates_registered: 0`) in `run.summary`.
  - `test_zero_screenings_created_marks_run_as_warning`: no change expected
    — an empty-features payload still yields all-zero counters and
    `status == "warning"`.
- Migration: no dedicated test beyond the existing `db-upgrade` /
  `init-db` paths already exercised by the test suite's DB setup fixtures.
