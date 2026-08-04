# Cinema Inspector Agent — Design

## Problem

Movies are linked to TMDB entries by `flask fetch-movie-metadata`
(`flask_backend/service/movie_metadata_pipeline.py`), which searches TMDB by
`movie.title` and takes the first result (`TMDBClient.search_movie`). Because
many films share a Portuguese title, this regularly attaches the wrong TMDB
entry — the linked director/year/country/genre then silently disagree with
what the cinema's own screening description says.

Two concrete examples:

- `/movies/a-capela`: sala-redenção's description reads "Jean-Michel
  Tchissoukou / CG / 1979 / 80 min / Comédia, Sátira / 12 anos", but the
  movie is linked to TMDB's "La ermita" (2023, Spain, dir. Carlota Pereda).
- `/movies/mostra-ufrgs`: the title is a festival/showcase umbrella name, and
  the description actually lists several distinct films. **Out of scope for
  this design** — see Non-Goals.

There is currently no automated check that a movie's TMDB match is
consistent with what the cinema itself published about the film.

## Goals

- Detect when a movie's linked TMDB entry disagrees with the director,
  year, country, or genre stated in its screening description(s).
- When a better match can be positively identified (via TMDB search, not
  guessed), re-link the movie to it automatically.
- When the agent can't confidently identify a fix, leave the data untouched
  and flag it for a human.
- Give a human a dashboard to review everything the agent did or flagged,
  and to revert an automated fix.

## Non-Goals (v1)

- Detecting/splitting screenings whose description bundles multiple
  distinct films under one title (the `mostra-ufrgs` case). Different
  failure mode, deferred to a future iteration.
- Correcting showtimes/dates, posters, or any other screening field. The
  agent's only write capability in v1 is re-linking a movie to a different
  TMDB id.
- Open-ended web search. The agent may only re-fetch a screening's own
  `url`, not search the wider web.
- Real-time/on-demand triggering from the UI. v1 is a batch CLI command,
  same operating model as `fetch-movie-metadata`.

## Architecture

New dependency: **atomic-agents** (built on
[Instructor](https://github.com/jxnl/instructor) + Pydantic). Instructor
talks to Gemini via the `instructor[google-genai]` extra, so this reuses the
existing `GEMINI_API_KEY` config — no new provider account.

New code:

- `flask_backend/service/movie_inspector.py` — orchestration loop, tool
  implementations, verdict schema.
- `flask_backend/repository/movie_inspections.py` + `MovieInspection` model
  (new migration) — one audit row per inspection.
- `inspect-movies` CLI command in `flask_backend/commands.py`, registered as
  a new `pipeline_name` on the existing `PipelineRun` tracker (same pattern
  as `fetch-movie-metadata`).
- `flask_backend/routes/admin/movies.py` (or a new `admin/inspections.py`
  blueprint) — `/admin/movies/inspections` dashboard, with a Revert action
  on `fixed` rows.

## Components

**Orchestrator agent**: one `AtomicAgent[OrchestratorInput, OrchestratorDecision]`.

- `OrchestratorInput`: the movie's current TMDB-derived metadata (title,
  original_title, release_year, original_language, directors, countries,
  genres) plus, for every `Screening` linked to that movie, the cinema name
  and `description` text.
- `OrchestratorDecision`: either a tool call (name + args) or a `conclude`
  action carrying the final verdict. This mirrors atomic-agents' own
  orchestration-agent example ("decide next tool vs. finish"); atomic-agents
  does not run its own agentic loop, so the loop itself is plain Python in
  `movie_inspector.py`, capped at 4 tool calls before a forced conclusion.

**Tools:**

1. `search_tmdb_candidates(title)` — wraps existing
   `TMDBClient.search_movies`.
2. `get_tmdb_details(tmdb_id)` — wraps existing
   `TMDBClient.get_movie_details`.
3. `fetch_screening_source(screening_id)` — re-fetches `screening.url` (plain
   HTTP GET + text extraction, not a cinema-specific scraper) for context
   beyond the stored `description`. Returns an error string as the
   observation (rather than raising) if the URL is missing or unreachable.
4. `rematch_movie(movie_id, tmdb_id)` **(write)** — wraps the existing
   `apply_tmdb_details` / `clear_tmdb_metadata` from
   `movie_metadata_pipeline.py`. Only ever invoked when the verdict is
   `fixed`.

**Verdict schema:**

```python
class InspectionVerdict(BaseIOSchema):
    status: Literal["consistent", "fixed", "needs_review"]
    reasoning: str
    new_tmdb_id: Optional[int]  # required when status == "fixed"
```

The agent can only reach `status="fixed"` after having used
`search_tmdb_candidates`/`get_tmdb_details` to positively identify a
specific replacement id — it cannot invent one. If it suspects a mismatch
but can't positively identify the correct replacement, the verdict must be
`needs_review`.

## Data Model

New table `movie_inspections`:

| column | type | notes |
|---|---|---|
| `id` | Integer PK | |
| `movie_id` | FK → movies | |
| `pipeline_run_id` | FK → pipeline_runs, nullable | ties row to a CLI invocation |
| `status` | String | `consistent` \| `fixed` \| `needs_review` \| `error` \| `reverted` |
| `reasoning` | Text | agent's explanation |
| `checked_tmdb_id` | Integer, nullable | the movie's `tmdb_id` at the time of this check |
| `previous_snapshot` | Text (JSON), nullable | before-state (title/original_title/release_year/directors/countries), populated for `fixed`/`reverted` rows |
| `new_snapshot` | Text (JSON), nullable | after-state, populated for `fixed`/`reverted` rows |
| `created_at` | DateTime | |

Snapshots are JSON text, matching the existing `PipelineRun.summary`
convention, since directors/countries are relational and the row needs to
render historical before/after state even after further changes happen.

Append-only: a Revert action does not edit an existing row — it creates a
new `movie_inspections` row with `status="reverted"`, calling `rematch_movie`
back to the stored `previous_snapshot`'s tmdb_id. This mirrors the
`AlertAction` append-only-log pattern already used for `/admin/alerts`.

## Data Flow

1. `flask inspect-movies [--limit N]` starts a `PipelineRun`
   (`pipeline_name="inspect-movies"`).
2. Select movies needing inspection via a new repository query:
   `movie.tmdb_id IS NOT NULL AND movie.tmdb_id != <checked_tmdb_id of latest movie_inspections row for this movie>`
   (rows with no prior inspection count as needing one). This means a movie
   is only re-inspected when its match has actually changed since the last
   check — not on every run.
3. For each movie: build `OrchestratorInput` from the movie's current TMDB
   metadata and all linked screenings' cinema/description text, run the
   orchestration loop (≤4 tool calls).
4. On conclusion:
   - `consistent` → persist a `movie_inspections` row
     (`checked_tmdb_id = movie.tmdb_id`), no writes to `Movie`.
   - `fixed` → snapshot before-state, call `rematch_movie`, snapshot
     after-state, persist the row.
   - `needs_review` → persist the row with reasoning, no writes to `Movie`.
5. Any per-movie exception (Gemini/Instructor error, TMDB error) → caught,
   persist a `status="error"` row, continue to the next movie. Batch summary
   recorded on `PipelineRun.summary` as `fetch-movie-metadata` already does.

## Error Handling

- Gemini/Instructor errors (rate limit, network) for a given movie are
  caught per-movie; the batch continues (matches `run_pipeline`'s existing
  per-movie try/except in `movie_metadata_pipeline.py`).
- `fetch_screening_source` never raises into the agent loop — network/missing
  URL failures become an observation string, and the agent proceeds without
  that context.
- Exceeding the tool-call cap forces a `needs_review` verdict with reasoning
  noting the inspection was inconclusive — never a silent failure.
- `rematch_movie` failing (e.g. TMDB lookup error on the chosen id) marks the
  whole inspection `status="error"`; no partial write to `Movie` (matches
  `apply_tmdb_details`'s existing clear-then-apply-then-commit shape).

## Admin UI

`/admin/movies/inspections`: lists `movie_inspections` rows (most recent
first, filterable by status), each showing the movie title, involved
cinema(s), status, reasoning, and — for `fixed`/`reverted` rows — the
before/after snapshot. Each row links to the existing
`/admin/movies/<id>/edit` page. `fixed` rows get a **Revert** button that
triggers the append-only revert flow described above.

## Testing

- `movie_inspector.py`: unit tests mock the Instructor client's response
  sequence (same `unittest.mock.patch` style as
  `test_service/test_gemini_api.py` and `test_service/test_tmdb.py` — no real
  Gemini/TMDB calls). Cover: dispatch for each of the 4 tools, forced
  conclusion at the step cap, and all four verdict outcomes
  (`consistent`/`fixed`/`needs_review`/`error`) writing the expected
  `movie_inspections` row.
- `repository/movie_inspections.py`: standard repository tests for the
  "needs inspection" query and row creation.
- `inspect-movies` CLI: test it starts/finishes a `PipelineRun` with the
  expected summary, mirroring existing `fetch-movie-metadata` command tests.
- Admin route: render test for the listing page; a test that Revert creates
  a new audit row and re-applies the previous `tmdb_id` (TMDB mocked, no
  network).
- No test exercises real Gemini or TMDB APIs, consistent with the rest of
  the suite.
