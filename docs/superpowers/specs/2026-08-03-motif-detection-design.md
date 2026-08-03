# Design: Deterministic Editorial Motif Detection (Phase 1)

## Status

Design approved. Source PRD: "Deterministic Editorial Motif Detection" (draft).

## Context

Phase 1 of the knowledge layer (`graph_sync.py`, `graph_queries.py`, the
`sync-graph`/`graph-query` CLI commands, merged in #299) mirrors Movie/Cinema/
Screening/ScreeningDate/Genre/Director/Country from SQLite into a GraphQLite
graph and exposes a handful of hand-written Cypher-style queries.

This design is the next layer on top: a deterministic **motif detection
engine** that inspects the graph, detects predefined editorial patterns
("motifs"), and produces a ranked list of structured `Observation`s. It does
not generate prose, call an LLM, or persist anything — that's explicitly
future work per the source PRD's non-goals.

## Scope for this phase

The source PRD proposes 7 motifs. Two require data that doesn't exist yet:

- **Shared Actor** — no `Actor` entity exists in the DB or graph.
- **Festival Coincidence** — no `Festival` entity exists in the DB or graph.

Both are **deferred** to a future phase (would need new models, TMDB
ingestion for cast data, and a data source for festival selections).

**Director Return** is in scope but with a caveat: the DB only has screening
history back to January 2025 (~19 months). Its threshold is set low (180
days) to be usable now, and its observations carry a reduced confidence
score (0.7) to reflect that "return" is a soft judgment call given thin
history, not a hard multi-year-gap fact. This will need revisiting as more
history accumulates.

In scope for this phase: **MultipleMoviesSameDirector, CountryCluster,
DirectorReturn, CinemaGenreFocus, Anniversary**.

## Architecture

Two new modules under `flask_backend/service/`, mirroring the existing
`graph_sync.py` / `graph_queries.py` split (build vs. query → detect vs.
rank):

```
flask_backend/service/motifs.py          # Motif base class, Observation, GraphEvidence,
                                          # the 5 concrete Motif subclasses, MOTIF_REGISTRY
flask_backend/service/motif_ranking.py   # scoring formula + dedup + run_motifs() orchestrator
```

`run_motifs(graph) -> list[Observation]` in `motif_ranking.py` is the single
entry point: runs every registered motif, concatenates results, deduplicates,
scores, and sorts (highest score first). No motif imports another motif or
the ranking module — only `motif_ranking.py` imports `motifs.py`. This keeps
the PRD's "no motif depends on another motif" and "adding a motif requires
only a new subclass + registry entry" properties intact.

`motifs.py` uses a class-based `Motif` per the PRD's literal data model, even
though the rest of `flask_backend/service/` is currently function-based —
this is an intentional, explicit deviation from local convention to match the
PRD's design exactly, since the design doc is the source of truth here.

## Data model

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GraphEvidence:
    nodes: list[str]                    # graph node IDs, e.g. "movie:42", "director:7"
    edges: list[tuple[str, str, str]]   # (from_id, to_id, edge_type)
    query: str | None = None            # the Cypher used, for explainability


@dataclass
class Observation:
    motif_name: str
    confidence: float
    score: float                        # 0.0 until the ranking stage fills it in
    headline: str
    summary: str
    evidence: GraphEvidence
    metadata: dict = field(default_factory=dict)


class Motif(ABC):
    name: str
    description: str
    version: str

    @abstractmethod
    def detect(self, graph) -> list[Observation]: ...
```

## The 5 in-scope motifs

All motifs restrict to non-draft screenings only, matching the existing
`directors_currently_showing`/`countries_this_month` convention in
`graph_queries.py`.

### 1. MultipleMoviesSameDirector

- **Pattern:** group currently-showing movies (screening date ≥ today) by
  director.
- **Condition:** ≥ 2 movies per director.
- **Observation:** one per qualifying director. `confidence: 1.0` (pure
  count, no judgment call). `metadata: {director, movies: [titles]}`.

### 2. CountryCluster

- **Pattern:** group currently-showing movies by production country.
- **Condition:** ≥ 2 movies per country (named constant
  `COUNTRY_CLUSTER_THRESHOLD = 2`, tunable later).
- **Observation:** one per qualifying country. `confidence: 1.0`.

### 3. DirectorReturn

- **Pattern:** for each director, all screening dates across all their
  movies, sorted chronologically.
- **Condition:** gap between the last screening before the current window
  and the earliest currently-showing screening exceeds `DIRECTOR_RETURN_GAP_DAYS
  = 180` (named constant).
- **Observation:** `confidence: 0.7`. Summary text notes the gap is measured
  against limited history.

### 4. CinemaGenreFocus

- **Pattern:** for each cinema, compare current month's genre distribution
  against that cinema's all-time genre distribution.
- **Condition:** a genre's current-period share exceeds its historical share
  by ≥ `CINEMA_GENRE_FOCUS_MULTIPLIER = 1.5`, and has ≥
  `CINEMA_GENRE_FOCUS_MIN_COUNT = 3` screenings this period (avoids flagging
  on tiny samples).
- **Observation:** `confidence: 0.7` (statistical threshold, not a hard
  fact).

### 5. Anniversary

- **Pattern:** for currently-showing movies only (not the whole catalog).
- **Condition:** `current_year - release_year` is in
  `ANNIVERSARY_YEARS = {10, 20, 25, 30, 40, 50, 75, 100}`.
- **Observation:** `confidence: 1.0`.

Each motif's `detect()` queries the graph directly via `graph.query(...)`
(same Cypher style as `graph_queries.py`) and builds its own `GraphEvidence`
from the node IDs/edges it touched.

## Ranking

The PRD's formula (`rarity`, `timeliness`, `historical_significance`,
`graph_complexity`) assumes years of trend data and dozens of motifs we
don't have. `historical_significance` is dropped for this phase — there's no
honest signal to back it with yet (no popularity/awards/critical data). The
remaining three signals are redistributed:

```
score = 0.45 * rarity + 0.30 * timeliness + 0.25 * graph_complexity
```

- **rarity** = `1 / (1 + sibling_count)`, where `sibling_count` is how many
  other observations *the same motif* produced in the current run.
- **timeliness** = `1.0` if any evidence screening date falls within the
  next 7 days, decaying linearly to `0.0` by 60 days out.
- **graph_complexity** = `min(len(evidence.nodes) / 10, 1.0)`.

Weights and the 7-day/60-day/10-node constants live as named constants in
`motif_ranking.py`, satisfying the PRD's "formula should remain configurable"
requirement without building a config system nobody needs yet.

## Deduplication

Two observations merge when their `evidence.nodes` sets intersect (e.g.
Director Return and Anniversary both citing the same `movie:42` node). The
higher-scored observation is kept; the lower-scored one's `motif_name` is
appended to the survivor's `metadata["merged_from"]` list, and it is dropped
from the output. Pairwise comparison is acceptable at this scale (dozens of
observations per run, not thousands).

## CLI integration

New command, following `sync-graph`/`graph-query`'s existing conventions in
`flask_backend/commands.py`:

```
flask --app flask_backend detect-motifs [--limit N] [--json]
```

- Same missing-graph-file check as `graph_query_command` (points the user to
  `sync-graph` first).
- Default: prints a table (headline, score, motif_name) for the top N
  (default 10) ranked observations.
- `--json`: prints full `Observation` objects (including evidence and
  metadata) as JSON.

## Testing

Following the existing `flask_backend/tests/test_service/` structure:

- `test_motifs.py` — one test class per motif, built against small
  hand-constructed graphs (same fixture style as `test_graph_queries.py`),
  covering the threshold boundary (e.g. exactly 2 vs 1 movies by the same
  director) and the "no match" case.
- `test_motif_ranking.py` — scoring formula (each signal in isolation),
  dedup merge behavior (overlapping vs disjoint evidence), sort order.
- `test_motif_commands.py` — CLI happy path, missing-graph-file error,
  `--json` output shape — mirroring `test_graph_commands.py`.

## Non-goals (carried from the PRD)

- No LLM integration, no prose generation, no blog/social output.
- No graph mining or autonomous discovery of new motifs.
- No persistence of observations (recomputed fresh each CLI invocation).
- No Shared Actor / Festival Coincidence motifs (deferred — see Scope).
