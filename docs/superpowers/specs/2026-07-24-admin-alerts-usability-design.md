# Admin Alerts Radical Simplification (Issue #258)

## Problem

The admin "Alerts" tab (`/admin/alerts`, issue #209) grew into eight
detection rules (`flask_backend/service/alert_rules.py`): new movie, single
screening, sessão comentada, mostra, director debut, returning director,
new genre combination, sequel/franchise. Each rule fires once, writes a
persisted `Alert` row, and the admin works through a pending queue
(mark posted / dismiss).

This is over-engineered relative to what the admin actually uses it for.
The real question the admin asks when opening this page is simple: *which
movies are worth timing a social post around, and are they a one-off
screening or a recurring run?* Most of the rule variety, the pipeline that
generates `Alert` rows on a cron, and the point-in-time snapshotting that
rule generation requires, exist to answer questions nobody is acting on.

This design replaces the whole `Alert` system with the two categories the
admin actually wants:

- **Sessão única** — the movie has exactly one exhibition at this cinema.
- **Recorrente** — the movie has more than one exhibition at this cinema,
  with a visible "shows until" date.

## Non-goals

- The `Collection`/`movies.collection_id` TMDB franchise data stays as-is.
  It was only consumed by the now-dropped `sequel_or_franchise` rule, but
  it's populated by a separate concern (`movie_metadata_pipeline.py`) and
  removing it is out of scope here.
- No changes to `import-json`, `fetch-posters`, `fetch-movie-metadata`
  pipelines or their entries in `/admin/pipelines`, other than removing
  `generate-alerts`'s own entry.
- Title cleaning (`service/title_cleaning.py`, `RULE_CATEGORIES`,
  `Screening.title_cleaning_rules`/`raw_title`) is untouched — those are
  used outside the alert system (title display) and stay.

## Architecture

`/admin/alerts` becomes a hybrid:

1. **The Pendentes list is always computed live** from `Screening` +
   `ScreeningDate` — there is no generation pipeline, no cron, no dedup
   keys, no point-in-time snapshot that can go stale. Single vs. recorrente
   is a fact about the current schedule, recomputed on every page load.
2. **A small, append-only action log persists posting history and
   reminders.** Marking a screening posted or dismissed is a real action
   worth keeping a record of (that's the point of the page), but it no
   longer needs to track *why a candidate was generated* — only *what the
   admin did about it, and when to bring it back*.

Each row represents one `Screening` (a movie+cinema pairing), never a
`Movie`. `Screening` is already scoped to a single cinema, so this is what
makes "Sessão única" unambiguously per-cinema: a movie playing at two
cinemas simultaneously can be única at one and recorrente at the other,
shown as two independent rows. No movie-level grouping or rule-priority
logic is needed at all.

## Data model

New table, replacing `alerts` entirely:

```
alert_actions
  id                 PK
  screening_id       FK -> screenings.id, NOT NULL, indexed
  action             String NOT NULL   # "posted" | "dismissed"
  remind_at          Date, NULLABLE    # if set, row resurfaces in Pendentes on/after this date
  created_at         DateTime NOT NULL
  created_by_user_id FK -> users.id, NULLABLE
```

No `dedup_key`, `rule_name`, `drafted_text`, or `context` — none of that
is persisted, since the pending facts are always recomputed and the
posting-history rows only need to record the action itself. Multiple rows
per `screening_id` are expected and intentional (e.g. posted once,
reminder brings it back into Pendentes, dismissed later) — this is what
gives the admin a real posting history per screening, not just a single
mutable status.

One migration:

- Drop `alerts` table (and its indexes).
- Drop `movies.metadata_alerts_evaluated_at` (+ index) — no more
  metadata-rule pipeline to gate.
- Drop `screenings.core_alerts_evaluated_at` (+ index) — no more
  core-rule pipeline to gate.
- Create `alert_actions` (+ indexes on `screening_id`, `action`).

`collections`, `movies.collection_id`, `screenings.title_cleaning_rules`,
`screenings.raw_title` are untouched.

## Classification rule

**Visibility filter** — a screening appears in Pendentes only if:

- `draft == False`, and
- it has at least one `ScreeningDate >= today`.

**Única vs. recorrente** — count that screening's `ScreeningDate` rows
where `date >= today - RECORRENTE_GRACE_PERIOD`, combining past-within-window
and future dates. `RECORRENTE_GRACE_PERIOD` is a code constant, default 6
months (`relativedelta(months=6)`, `python-dateutil` is already a
dependency). Exactly 1 → **Sessão única**; more than 1 → **Recorrente**.

The grace period exists to avoid a real bug in the naive version (count
only future dates): a recorring screening's remaining-future-date count
drops to 1 on its last scheduled day, which would misclassify it as
"única" right when it's actually wrapping up a long run. Counting
recent-past dates too means a screening that already ran (say) 20 times
in the last two months still reads as Recorrente on its final day. A
screening whose only prior occurrence is outside the window (e.g. it
played once 8 months ago and is now booked for a single fresh date) is
correctly treated as a new única, not a continuation.

**"Até quando" column** (Recorrente rows only) — the last upcoming
(`>= today`) `ScreeningDate` for that screening. Unaffected by the grace
period; única rows leave this column blank since the row already shows
the one date.

## Pending row resolution (action + reminder)

A screening that passes the visibility filter is excluded from Pendentes
if its most recent `alert_actions` row has `remind_at` that is `NULL` or
still in the future (`> today`). It reappears once `remind_at <= today`,
or immediately if it has no action rows at all. "Most recent" is by
`created_at` — the log is append-only, so a screening can cycle through
pending → posted (with reminder) → pending → dismissed, etc.

The visibility filter and the action-resolution filter are independent and
ANDed, so a `remind_at` set *after* the screening's last upcoming date is
moot: the visibility filter alone will already exclude the row by the time
that reminder date arrives. To prevent an admin from unknowingly setting a
reminder that will never fire, the reminder `<input type="date">` gets a
`max` attribute equal to the screening's last upcoming `ScreeningDate`,
so the browser's own date picker simply won't offer out-of-range dates.
This is front-end only — no server-side re-validation — consistent with
this being a low-stakes internal admin tool.

## Pendentes view

Columns:

- **Regra** — badge: "Sessão única — `{cinema.name}`" or "Recorrente —
  `{cinema.name}`". The cinema is always named, not just for única — since
  every row is per-screening (per-cinema) in both categories, a movie
  playing at two cinemas can otherwise produce two identically-labeled
  "Recorrente" rows with nothing distinguishing them at a glance.
- **Filme** — linked title, same as today.
- **Imagem** — unchanged.
- **Até quando** — last upcoming date, Recorrente rows only.
- **Texto sugerido** — copyable textarea, same shape as today's
  `alert_text.build_drafted_text` (title, release year, director(s), next
  date + cinema), rebuilt from the live `Screening`/`ScreeningDate` data.
  Emoji keyed off the two categories (e.g. ⏳ única, 🔁 recorrente)
  instead of 8 rule names.
- **Ações** — "Marcar como postado" / "Descartar", each submitting an
  optional `remind_at` date field (empty by default, a plain date input).
  Submitting either one records a new `alert_actions` row for that
  screening.

Sort: ascending by nearest upcoming `ScreeningDate` for that screening
(matches the issue's ask — soonest-expiring opportunities first).

## History tabs

Postados / Descartados list `alert_actions` rows (not screenings),
newest-first, paginated. Each row renders the screening's movie/cinema/date
context live at render time (joins, not a stored snapshot). This gives the
admin the posting-history view they asked for — "what did we post, and
when" — without needing the pending-row facts (which change over time) to
be frozen at action time.

## Removed entirely

- `flask_backend/service/alert_rules.py`, `alert_pipeline.py`,
  `alert_text.py` — replaced by a new
  `flask_backend/service/screening_alerts.py` (pure functions: classify,
  last-upcoming-date, drafted text, pending-row filtering — same
  "pure function, no DB writes" convention `alert_rules.py` used).
- `flask_backend/repository/alerts.py` — replaced by
  `flask_backend/repository/alert_actions.py` (new schema; queries:
  create, get pending screenings, get paginated actions by type, delete
  for screening, repoint to screening).
- `Alert` model, `ALERT_STATUSES` constant (replaced by a small
  `ALERT_ACTIONS = ["posted", "dismissed"]`), `Movie.metadata_alerts_evaluated_at`,
  `Screening.core_alerts_evaluated_at` — new `AlertAction` model added.
- `flask generate-alerts` CLI command (`commands.py`) and its
  registration.
- `.github/workflows/generate-alerts.yml`.
- The `generate-alerts` branch in `routes/admin/pipelines.py`
  (`get_by_pipeline_run_id`/`get_alerts_by_run` usage, the
  `pipeline_name == "generate-alerts"` case) and its row in the pipeline
  list — there's no generation run left to track.
- `repository/movies.py`: `get_earlier_movies_with_director`,
  `get_earlier_genre_id_sets`, `get_earlier_movies_with_collection`,
  `get_movies_due_for_metadata_alert_evaluation` — only consumers were the
  dropped metadata rules.
- `repository/screenings.py`: `get_screenings_due_for_core_alert_evaluation`.
- Tests: `test_alert_pipeline.py`, `test_alert_rules.py`,
  `test_alert_text.py` deleted; `test_admin_alerts.py` rewritten for the
  new grouped/live behavior; new tests added for
  `service/screening_alerts.py`.

## Integration points to port (not remove)

Three call sites reference `repository/alerts.py` for cleanup/repointing
and need their new-module equivalents:

- `repository/movies.py`'s `delete()` — currently calls
  `alerts.delete_for_movie(movie.id)` once, movie-wide. Since the new
  schema has no `movie_id` column (only `screening_id`), this becomes a
  per-screening `alert_actions.delete_for_screening(_scr.id)` call inside
  the existing loop that already deletes each screening's dates and
  `PosterFetchAttempt` rows.
- `repository/screenings.py`'s `delete()` — same call, ported directly:
  `alert_actions.delete_for_screening(screening.id)`.
- `service/movie_merge.py`'s `_merge_screenings()` — currently calls
  `alerts.repoint_to_screening(screening.id, existing.id)` when two
  duplicate `Screening` rows collapse into one; ports directly to
  `alert_actions.repoint_to_screening(...)`.
- `service/movie_merge.py`'s `merge_movies()` — currently also calls
  `alerts.repoint_to_movie(duplicate.id, survivor.id)`. This has no
  equivalent and is simply dropped: `alert_actions` rows are always
  reached via `screening_id`, and screenings already carry their
  `alert_actions` history with them when they move to the survivor movie
  (via `survivor.screenings.append(screening)`) or get repointed above.

## Edge cases

- A screening whose only dates are all in the past: excluded from
  Pendentes by the visibility filter (same as before), regardless of any
  `alert_actions` history.
- A recorrente screening on its last scheduled day: still classified
  Recorrente because of the grace-period window (see "Classification
  rule").
- A screening dismissed with no `remind_at`: stays out of Pendentes
  indefinitely; naturally drops off entirely once its last date passes.
- A screening posted with a `remind_at` in the past (edge case: reminder
  date already elapsed at submit time): resurfaces immediately on next
  load, which is correct — nothing to wait for.
- Two screenings with the same nearest upcoming date: no explicit
  tiebreaker needed at this scale (unlike the old design's movie-level
  grouping, which needed a deterministic secondary sort for pagination
  stability); ties can be left to natural query order.

## Testing

- Unit tests for `service/screening_alerts.py`: classification
  (única/recorrente, including the grace-period boundary and the
  last-day-of-a-run case), last-upcoming-date, drafted text, pending-row
  filtering by latest action's `remind_at` — pure functions, no DB
  needed beyond constructing `Screening`/`ScreeningDate`/`AlertAction`
  fixtures.
- Integration test for the route: seed screenings across única/recorrente/
  draft/past-only/dismissed-with-future-reminder/dismissed-with-past-reminder
  combinations; hit `/admin/alerts?status=pending`; assert exactly the
  expected rows and sort order.
- Test for posted/dismissed actions: submit with and without `remind_at`;
  assert the `alert_actions` row is created and the screening's presence
  in Pendentes reflects the new state on next fetch.
- Test for the delete/merge integration points: deleting a movie or
  screening removes its `alert_actions` rows; merging duplicate screenings
  repoints them instead of losing them.
