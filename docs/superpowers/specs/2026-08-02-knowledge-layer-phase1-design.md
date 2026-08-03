# Knowledge Layer — Phase 1 Design

## Status

Approved design, ready for implementation planning.

## Background

We propose a "Knowledge Layer" modeling the cinema ecosystem
(movies, cinemas, screenings, and their metadata) as a graph
derived from the existing SQLite relational database, to support
relationship-traversal queries (e.g. "which directors are showing at a given
cinema") that are awkward as SQL joins. This document resolves technology implementation
questions for a phase 1: a factual graph containing only explicit data already present
in SQLite, with no embeddings, inference, or LLM integration.

## Schema

**Decision:** Phase 1 syncs only what exists in SQLite today. `ScreeningDate` gets
its own graph node (see Schema below). `Collection` is out of scope for Phase 1.

## Technology choice: GraphQLite

Given this project's operational philosophy — a single VM,
SQLite as the only datastore, no other services running alongside Flask,
nginx, and Traefik (`docker-compose.production.yml`) — an embedded,
file-based store was strongly preferred over a separate service (Neo4j,
Memgraph) to avoid new ops burden (new container, memory budget, backups).

Candidates evaluated:

| Option | Ops footprint | Query language | Risk |
|---|---|---|---|
| **GraphQLite** (chosen) | Zero — SQLite extension, sibling file | Cypher | Pre-1.0 (v0.6.0), ~1 year old, 5 contributors (~85% from one author). Mitigated: graph is fully rebuildable from SQLite, so engine risk is low-stakes. |
| networkx (already an unused dependency) | Zero — pure Python, in-process | None — hand-written Python traversal | Safest maturity-wise, but no Cypher; weaker foundation for future agent query generation (Phase 3). |
| Kùzu (via community fork) | Zero — embedded, single-file | Cypher | Original project archived Oct 2025 after its company was acquired by Apple; only community forks remain. Strictly worse risk profile than GraphQLite for the same benefit. |
| ArcadeDB (embedded mode) | New — requires a JVM in the Docker image | Cypher/Gremlin/SQL | Adds a runtime this Python project doesn't have today. |
| Neo4j / Memgraph (separate service) | New — extra container, memory, backups | Cypher | Most mature tooling, heaviest ops for this project's scale. |

**Decision:** [GraphQLite](https://github.com/colliery-io/graphqlite) — MIT
licensed, a SQLite extension adding Cypher query support and built-in graph
algorithms, with Python bindings (`pip install graphqlite`). It fits the
project's existing "everything is a SQLite file" philosophy exactly, and
gives a real query language for Phase 3 agent workflows without adding any
new service. The graph is explicitly a derived, disposable artifact (see
Synchronization below), which de-risks betting on an immature dependency:
if GraphQLite stalls, the graph can be regenerated with a different engine
without any data loss, since SQLite remains the sole source of truth.

**Expected size:** current data (981 movies, 5 cinemas, 1,042 screenings,
4,428 screening dates, 19 genres, 713 directors, 74 countries) yields
~2,834 nodes and ~5,172 edges in Phase 1's scope — a few hundred KB to low
single-digit MB on disk regardless of engine. Not a real constraint even at
5-10x future growth.

## Graph Schema

**Nodes** (label — properties, mirroring SQLite columns 1:1):

| Label | Properties |
|---|---|
| `Movie` | sqlite_id, title, slug, original_title, release_year, original_language, tmdb_id |
| `Cinema` | sqlite_id, slug, name |
| `Screening` | sqlite_id, url, draft |
| `ScreeningDate` | sqlite_id, date, time |
| `Genre` | sqlite_id, tmdb_id, name |
| `Director` | sqlite_id, tmdb_id, name |
| `Country` | sqlite_id, iso_3166_1, name |

**Edges:**

- `(Movie)-[:HAS_GENRE]->(Genre)`
- `(Movie)-[:DIRECTED_BY]->(Director)`
- `(Movie)-[:PRODUCED_IN]->(Country)`
- `(Movie)-[:HAS_SCREENING]->(Screening)`
- `(Screening)-[:AT_CINEMA]->(Cinema)`
- `(Screening)-[:HAS_DATE]->(ScreeningDate)`

**Node identity:** each node stores its source table's integer primary key
as a `sqlite_id` property, scoped by label (e.g. `Movie.sqlite_id`,
`Genre.sqlite_id` are independent id spaces). No UUIDs — SQLite is the only
source system for the foreseeable future, so mirroring its PKs keeps sync
logic simple and debuggable.

**Why `ScreeningDate` is its own node** rather than a list property on
`Screening`: several query examples are inherently temporal ("genres shown...
in 2025", "screenings of a movie since its release", "this month's schedule").
A dedicated node with a `date` property makes these simple Cypher `WHERE` clauses;
a list-valued property on `Screening` would require unpacking in every query.

## Architecture

Code follows the existing `service/`/`repository/` conventions:

- `flask_backend/service/graph_sync.py` — builds the graph from SQLite and
  writes it via GraphQLite. Same shape as `poster_pipeline.py` /
  `movie_metadata_pipeline.py`.
- `flask_backend/service/graph_queries.py` — typed query functions, one per
  query.
- Two new CLI commands registered in `commands.py`'s `register_commands()`:
  `sync-graph` and `graph-query`.
- `env_config.py` gains `GRAPH_DB_PATH` (default e.g.
  `./flask_backend_graph.sqlite`), following the `UPLOAD_DIR`/`DATABASE_URL`
  pattern — a sibling file next to `flask_backend.sqlite`, not inside it.
- `graphqlite` added to `pyproject.toml`.

## Synchronization

`sync-graph` is a **manual CLI command only** in Phase 1 — not wired into
`import-json`, not a scheduled GitHub Action. It can be automated later once
the graph proves useful.

Flow:

1. Open (or create) the GraphQLite file at `GRAPH_DB_PATH`.
2. Wipe all existing nodes/edges (full `DETACH DELETE`).
3. Read all rows for the six entities via existing repository functions
   (`repository/movies.py`, `repository/cinemas.py`, etc.) — no new SQL
   queries, reuse what's there.
4. Create nodes, then edges. Use GraphQLite's bulk-insert path if the
   Python bindings expose one (bypasses Cypher parsing entirely, ~100-500x
   faster than per-row `CREATE` per GraphQLite's own benchmarks); otherwise
   fall back to per-row Cypher `CREATE` — the exact API surface needs
   confirming against the library during implementation.
5. Print a summary (node/edge counts) to stdout, matching the style of
   `dupe-check` and other reporting commands.

**Full wipe + rebuild, not incremental upsert/diff.** At ~8,000 elements
this rebuilds in well under a second. It also makes idempotency trivial —
same SQLite state in, same graph out, every run — and avoids an entire
class of diffing bugs that incremental sync would introduce for no
practical benefit at this scale.

**No schema migrations for the graph.** Since it's a fully derived, fully
disposable store, a schema change is just an update to `graph_sync.py`
followed by re-running `sync-graph`. No Alembic-style migration history.

**No `PipelineRun` tracking.** That pattern exists for automated/scheduled
pipelines (`import-json`, `fetch-posters`, `fetch-movie-metadata`);
`sync-graph` is a manual, foreground command, so it doesn't participate.

**No dedicated backup/snapshot strategy.** The graph regenerates from
SQLite in under a second; `backup-db.sh` already covers the real source of
truth. If the graph file is lost or corrupted, re-run `sync-graph`.

## Query Layer

Thin, typed Python functions in `graph_queries.py` wrapping Cypher, one per
query example — enough to prove the graph works, not a second
application layer:

- `movies_by_director(name) -> list[Movie]`
- `directors_currently_showing() -> list[Director]`
- `countries_this_month() -> list[Country]`
- `genres_at_cinema(cinema_slug, year) -> list[Genre]`
- `screenings_since_release(movie_slug) -> list[Screening]`

Each opens the GraphQLite file read-only, runs its Cypher query, and returns
plain Python objects (dicts or small dataclasses) — no ORM-style graph
models.

Exposed via a `graph-query` CLI command that takes a query name and prints
results as a table, e.g.:

```bash
flask --app flask_backend graph-query directors-currently-showing
```

Matches the existing `dupe-check` / `title-cleaning-report` pattern of
read-only reporting commands.

## Error Handling

Deliberately minimal. `sync-graph` and `graph-query` are manual, foreground
CLI commands — failures raise and print a traceback; no retry logic. If
GraphQLite's extension fails to load (e.g. a platform wheel issue), that
surfaces immediately rather than being swallowed.

## Testing

`flask_backend/tests/test_service/test_graph_sync.py` and
`test_graph_queries.py`:

- Build a small SQLite fixture (a handful of movies/cinemas/screenings,
  following existing fixture patterns from `tests/README.md`).
- Run the sync against a tmp GraphQLite file.
- Assert on node/edge counts and on each query function's output.

No mocking of GraphQLite — tests exercise the real extension against real
(tiny) fixture data, consistent with this project's general preference for
testing against real dependencies rather than mocks.

## Non-goals

Recommendation systems, embeddings, vector search, knowledge inference, LLM
integration, editorial automation — all explicitly out of scope for Phase
1.

## Open questions for future phases

- Whether `sync-graph` becomes automated (post-`import-json` hook or
  scheduled Action) is deferred until the graph proves useful in practice.
- The query layer exposed to future LLM agents is not designed
  here; `graph_queries.py`'s functions are a Phase 1 sanity-check, not a
  committed API surface.
