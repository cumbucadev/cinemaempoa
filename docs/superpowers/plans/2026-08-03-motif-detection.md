# Motif Detection Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic motif detection engine that inspects the knowledge graph (Phase 1's GraphQLite mirror), detects 5 predefined editorial patterns, and produces a ranked list of structured `Observation`s, exposed via a new `detect-motifs` CLI command.

**Architecture:** Two new modules in `flask_backend/service/`: `motifs.py` (data model + 5 `Motif` subclasses + registry) and `motif_ranking.py` (scoring + deduplication + `run_motifs()` orchestrator). A new `detect-motifs` CLI command in `flask_backend/commands.py` wires it up, mirroring the existing `sync-graph`/`graph-query` commands.

**Tech Stack:** Python 3.14, GraphQLite (`graphqlite.Graph`, Cypher queries via `graph.query(cypher, params)`), pytest, Flask CLI (`click`).

## Global Constraints

- Full spec: `docs/superpowers/specs/2026-08-03-motif-detection-design.md` — read it before starting if anything below is ambiguous.
- Follow existing codebase conventions: dataclasses + plain functions everywhere in `flask_backend/service/` **except** `Motif`, which is a class per the spec's explicit deviation.
- All motifs restrict to non-draft screenings (`s.draft = false`), matching `graph_queries.py`'s existing convention.
- Run `uv run ruff check --fix` and `uv run ruff format` before considering any task's code complete (no templates are touched, so `djlint` is not needed).
- Every task ends with `uv run pytest flask_backend/tests/test_service/ -v` passing for the files touched in that task, plus a full `uv run pytest -q` at the very end (Task 9).

### Critical GraphQLite quirks discovered during design (do not rediscover these by trial and error)

1. **`min()`/`max()` on string-typed properties (e.g. `sd.date`) are broken** — they return a bare integer (observed: `min(sd.date)` on `'2026-08-20'`/`'2026-08-05'` returned `2026`, not the earliest date string). **Never use `min()`/`max()` in Cypher on date strings.** Instead, `collect(sd.date)` and compute `min()`/`max()` in Python — ISO 8601 date strings (`YYYY-MM-DD`) sort correctly with plain string comparison, so Python's `min()`/`max()` on the string list works fine.
2. **`collect(DISTINCT x.prop)` does not deduplicate** — it behaves like plain `collect(x.prop)` (observed: `collect(DISTINCT m.id)` returned `['m:1', 'm:1']` for a movie matched twice). **Never rely on `DISTINCT` inside `collect()` for property values.** Instead, `collect(x.prop)` (no `DISTINCT`) and deduplicate in Python with the `_dedupe_preserve_order()` helper from Task 1.
3. **`count(DISTINCT node_variable)` (not a property) works correctly** — e.g. `count(DISTINCT m)` correctly deduplicates when `m` is matched multiple times via multiple screening dates. Safe to use.
4. **`WITH x, count(...) AS c, collect(...) AS xs WHERE c >= N RETURN ...`** (post-aggregation filtering via `WITH ... WHERE`) works correctly. **`RETURN ... HAVING ...` is not supported** (syntax error) — always use `WITH ... WHERE` instead.
5. Every node has an `id` property equal to its external ID string (e.g. `"movie:42"`, set automatically by `insert_graph_bulk`/`insert_nodes_bulk`) — safe to `RETURN n.id AS ...` for evidence node IDs.

---

### Task 1: Data model + dedupe helper

**Files:**
- Create: `flask_backend/service/motifs.py`
- Test: `flask_backend/tests/test_service/test_motifs.py`

**Interfaces:**
- Produces: `GraphEvidence` (dataclass: `nodes: list[str]`, `edges: list[tuple[str, str, str]]`, `query: str | None = None`), `Observation` (dataclass: `motif_name: str`, `confidence: float`, `score: float`, `headline: str`, `summary: str`, `evidence: GraphEvidence`, `metadata: dict`), `Motif` (ABC: `name: str`, `description: str`, `version: str`, `detect(self, graph) -> list[Observation]`), `_dedupe_preserve_order(items: list) -> list`.

- [ ] **Step 1: Write the failing test**

Create `flask_backend/tests/test_service/test_motifs.py`:

```python
"""
Tests flask_backend/service/motifs.py.
"""

from flask_backend.service.motifs import _dedupe_preserve_order


class TestDedupePreserveOrder:
    def test_removes_duplicates_keeping_first_occurrence_order(self):
        assert _dedupe_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_returns_empty_list_unchanged(self):
        assert _dedupe_preserve_order([]) == []

    def test_returns_list_with_no_duplicates_unchanged(self):
        assert _dedupe_preserve_order(["a", "b", "c"]) == ["a", "b", "c"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` (`flask_backend.service.motifs` does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `flask_backend/service/motifs.py`:

```python
"""Deterministic editorial motif detection: inspects the knowledge graph
(GraphQLite, synced via graph_sync.py) and produces structured Observation
objects for predefined editorial patterns. See
docs/superpowers/specs/2026-08-03-motif-detection-design.md for the full
design rationale, including the GraphQLite quirks this module works around
(min()/max() on date strings, collect(DISTINCT ...) not deduplicating).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class GraphEvidence:
    nodes: list[str]
    edges: list[tuple[str, str, str]]
    query: str | None = None


@dataclass
class Observation:
    motif_name: str
    confidence: float
    score: float
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


def _dedupe_preserve_order(items: list) -> list:
    """GraphQLite's collect(DISTINCT x.prop) does not deduplicate (see
    module docstring / design doc), so every motif that collects a property
    list must dedupe it here instead."""
    return list(dict.fromkeys(items))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git commit -m "feat: add motif data model (Observation, GraphEvidence, Motif)"
```

---

### Task 2: MultipleMoviesSameDirector motif

**Files:**
- Modify: `flask_backend/service/motifs.py`
- Test: `flask_backend/tests/test_service/test_motifs.py`

**Interfaces:**
- Consumes: `Motif`, `Observation`, `GraphEvidence`, `_dedupe_preserve_order` from Task 1.
- Produces: `MultipleMoviesSameDirectorMotif` class, importable from `flask_backend.service.motifs`.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_motifs.py`:

```python
from datetime import date, timedelta

from graphqlite import Graph

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_sync import sync_graph
from flask_backend.service.motifs import MultipleMoviesSameDirectorMotif


def _screening(cinema_slug, days_from_today, draft=False):
    return Screening(
        cinema_id=get_cinema_by_slug(cinema_slug).id,
        description="d",
        draft=draft,
        dates=[ScreeningDate(date=date.today() + timedelta(days=days_from_today), time="19:00")],
    )


class TestMultipleMoviesSameDirectorMotif:
    def test_flags_director_with_two_currently_showing_movies(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie_a = Movie(title="Paris, Texas", slug="paris-texas")
            movie_a.directors = [director]
            movie_a.screenings = [_screening("capitolio", 1)]
            movie_b = Movie(title="Perfect Days", slug="perfect-days")
            movie_b.directors = [director]
            movie_b.screenings = [_screening("capitolio", 2)]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = MultipleMoviesSameDirectorMotif().detect(graph)

            assert len(observations) == 1
            obs = observations[0]
            assert obs.motif_name == "multiple_movies_same_director"
            assert obs.confidence == 1.0
            assert sorted(obs.metadata["movies"]) == sorted(
                ["Paris, Texas", "Perfect Days"]
            )
            assert obs.metadata["director"] == "Wim Wenders"
            assert obs.metadata["next_screening_date"] == (
                date.today() + timedelta(days=1)
            ).isoformat()

    def test_does_not_flag_director_with_only_one_currently_showing_movie(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Agnès Varda")
            movie = Movie(title="Cléo de 5 à 7", slug="cleo-de-5-a-7")
            movie.directors = [director]
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert MultipleMoviesSameDirectorMotif().detect(graph) == []

    def test_excludes_draft_screenings_from_the_count(self, app, setup_cinemas, tmp_path):
        with app.app_context():
            director = get_or_create_director(1, "Diretor")
            published = Movie(title="Publicado", slug="publicado")
            published.directors = [director]
            published.screenings = [_screening("capitolio", 1)]
            draft = Movie(title="Rascunho", slug="rascunho")
            draft.directors = [director]
            draft.screenings = [_screening("capitolio", 1, draft=True)]
            db_session.add_all([published, draft])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert MultipleMoviesSameDirectorMotif().detect(graph) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k MultipleMoviesSameDirector`
Expected: FAIL with `ImportError: cannot import name 'MultipleMoviesSameDirectorMotif'`.

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/motifs.py`:

```python
class MultipleMoviesSameDirectorMotif(Motif):
    name = "multiple_movies_same_director"
    description = "Detects directors with 2+ movies currently screening."
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        rows = graph.query(
            "MATCH (d:Director)<-[:DIRECTED_BY]-(m:Movie)-[:HAS_SCREENING]->"
            "(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "WITH d, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, "
            "collect(m.title) AS titles, collect(sd.date) AS dates "
            "WHERE movie_count >= 2 "
            "RETURN d.id AS director_id, d.name AS director_name, movie_count, "
            "movie_ids, titles, dates "
            "ORDER BY director_name",
            {"today": today},
        )

        observations = []
        for row in rows:
            movie_ids = _dedupe_preserve_order(row["movie_ids"])
            titles = _dedupe_preserve_order(row["titles"])
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=1.0,
                    score=0.0,
                    headline=f"Múltiplos filmes de {row['director_name']} em cartaz",
                    summary=(
                        f"{len(movie_ids)} filmes dirigidos por "
                        f"{row['director_name']} estão em cartaz atualmente."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["director_id"], *movie_ids],
                        edges=[
                            (mid, row["director_id"], "DIRECTED_BY")
                            for mid in movie_ids
                        ],
                    ),
                    metadata={
                        "director": row["director_name"],
                        "movies": titles,
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k MultipleMoviesSameDirector`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git commit -m "feat: add MultipleMoviesSameDirector motif"
```

---

### Task 3: CountryCluster motif

**Files:**
- Modify: `flask_backend/service/motifs.py`
- Test: `flask_backend/tests/test_service/test_motifs.py`

**Interfaces:**
- Consumes: same as Task 2.
- Produces: `CountryClusterMotif` class with `COUNTRY_CLUSTER_THRESHOLD = 2` module-level constant in `motifs.py`.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_motifs.py`:

```python
from flask_backend.repository.countries import get_or_create_by_iso_code
from flask_backend.service.motifs import CountryClusterMotif


class TestCountryClusterMotif:
    def test_flags_country_with_two_currently_showing_movies(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            japan = get_or_create_by_iso_code("JP", "Japan")
            movie_a = Movie(title="Filme A", slug="filme-a")
            movie_a.countries = [japan]
            movie_a.screenings = [_screening("capitolio", 1)]
            movie_b = Movie(title="Filme B", slug="filme-b")
            movie_b.countries = [japan]
            movie_b.screenings = [_screening("capitolio", 2)]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = CountryClusterMotif().detect(graph)

            assert len(observations) == 1
            assert observations[0].motif_name == "country_cluster"
            assert observations[0].metadata["country"] == "Japan"
            assert sorted(observations[0].metadata["movies"]) == sorted(
                ["Filme A", "Filme B"]
            )

    def test_does_not_flag_country_with_only_one_currently_showing_movie(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            france = get_or_create_by_iso_code("FR", "France")
            movie = Movie(title="Filme Único", slug="filme-unico")
            movie.countries = [france]
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert CountryClusterMotif().detect(graph) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k CountryCluster`
Expected: FAIL with `ImportError: cannot import name 'CountryClusterMotif'`.

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/motifs.py`:

```python
COUNTRY_CLUSTER_THRESHOLD = 2


class CountryClusterMotif(Motif):
    name = "country_cluster"
    description = (
        f"Detects production countries with {COUNTRY_CLUSTER_THRESHOLD}+ "
        "movies currently screening."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        rows = graph.query(
            "MATCH (m:Movie)-[:PRODUCED_IN]->(c:Country), "
            "(m)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "WITH c, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, "
            "collect(m.title) AS titles, collect(sd.date) AS dates "
            "WHERE movie_count >= $threshold "
            "RETURN c.id AS country_id, c.name AS country_name, movie_count, "
            "movie_ids, titles, dates "
            "ORDER BY country_name",
            {"today": today, "threshold": COUNTRY_CLUSTER_THRESHOLD},
        )

        observations = []
        for row in rows:
            movie_ids = _dedupe_preserve_order(row["movie_ids"])
            titles = _dedupe_preserve_order(row["titles"])
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=1.0,
                    score=0.0,
                    headline=f"Cinema de {row['country_name']} em destaque",
                    summary=(
                        f"{len(movie_ids)} filmes de {row['country_name']} "
                        "estão em cartaz atualmente."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["country_id"], *movie_ids],
                        edges=[
                            (mid, row["country_id"], "PRODUCED_IN")
                            for mid in movie_ids
                        ],
                    ),
                    metadata={
                        "country": row["country_name"],
                        "movies": titles,
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k CountryCluster`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git commit -m "feat: add CountryCluster motif"
```

---

### Task 4: DirectorReturn motif

**Files:**
- Modify: `flask_backend/service/motifs.py`
- Test: `flask_backend/tests/test_service/test_motifs.py`

**Interfaces:**
- Consumes: same as Task 2.
- Produces: `DirectorReturnMotif` class with `DIRECTOR_RETURN_GAP_DAYS = 180` module-level constant.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_motifs.py`:

```python
from flask_backend.service.motifs import DirectorReturnMotif


class TestDirectorReturnMotif:
    def test_flags_director_returning_after_a_long_gap(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Agnès Varda")
            old_movie = Movie(title="Filme Antigo", slug="filme-antigo")
            old_movie.directors = [director]
            old_movie.screenings = [_screening("capitolio", -200)]
            new_movie = Movie(title="Filme Novo", slug="filme-novo")
            new_movie.directors = [director]
            new_movie.screenings = [_screening("capitolio", 1)]
            db_session.add_all([old_movie, new_movie])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = DirectorReturnMotif().detect(graph)

            assert len(observations) == 1
            obs = observations[0]
            assert obs.motif_name == "director_return"
            assert obs.confidence == 0.7
            assert obs.metadata["director"] == "Agnès Varda"
            assert obs.metadata["movies"] == ["Filme Novo"]
            assert obs.metadata["gap_days"] >= 180

    def test_does_not_flag_director_with_a_short_gap(self, app, setup_cinemas, tmp_path):
        with app.app_context():
            director = get_or_create_director(1, "Diretor Recente")
            old_movie = Movie(title="Filme Antigo", slug="filme-antigo")
            old_movie.directors = [director]
            old_movie.screenings = [_screening("capitolio", -30)]
            new_movie = Movie(title="Filme Novo", slug="filme-novo")
            new_movie.directors = [director]
            new_movie.screenings = [_screening("capitolio", 1)]
            db_session.add_all([old_movie, new_movie])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert DirectorReturnMotif().detect(graph) == []

    def test_does_not_flag_director_with_no_prior_screening_history(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Diretor Estreante")
            movie = Movie(title="Primeiro Filme", slug="primeiro-filme")
            movie.directors = [director]
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert DirectorReturnMotif().detect(graph) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k DirectorReturn`
Expected: FAIL with `ImportError: cannot import name 'DirectorReturnMotif'`.

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/motifs.py`:

```python
DIRECTOR_RETURN_GAP_DAYS = 180


class DirectorReturnMotif(Motif):
    name = "director_return"
    description = (
        f"Detects directors whose currently-screening movie follows a gap "
        f"of {DIRECTOR_RETURN_GAP_DAYS}+ days since their last recorded "
        "screening. Threshold is deliberately short: the DB only has "
        "screening history back to Jan 2025, so this cannot yet detect a "
        "true multi-year gap."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        rows = graph.query(
            "MATCH (d:Director)<-[:DIRECTED_BY]-(m:Movie)-[:HAS_SCREENING]->"
            "(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE s.draft = false "
            "RETURN d.id AS director_id, d.name AS director_name, "
            "m.id AS movie_id, m.title AS title, sd.date AS date "
            "ORDER BY director_name",
        )

        by_director: dict[str, dict] = {}
        for row in rows:
            entry = by_director.setdefault(
                row["director_id"],
                {"name": row["director_name"], "past": [], "current": []},
            )
            bucket = "current" if row["date"] >= date.today().isoformat() else "past"
            entry[bucket].append((row["movie_id"], row["title"], row["date"]))

        observations = []
        for director_id, entry in by_director.items():
            if not entry["past"] or not entry["current"]:
                continue

            last_past_date = max(d for _, _, d in entry["past"])
            first_current_date = min(d for _, _, d in entry["current"])
            gap_days = (
                date.fromisoformat(first_current_date)
                - date.fromisoformat(last_past_date)
            ).days
            if gap_days <= DIRECTOR_RETURN_GAP_DAYS:
                continue

            current_movie_ids = _dedupe_preserve_order(
                [mid for mid, _, _ in entry["current"]]
            )
            current_titles = _dedupe_preserve_order(
                [title for _, title, _ in entry["current"]]
            )
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=0.7,
                    score=0.0,
                    headline=f"{entry['name']} retorna após {gap_days} dias",
                    summary=(
                        f"Um filme de {entry['name']} volta a ser exibido "
                        f"após {gap_days} dias sem sessões registradas."
                    ),
                    evidence=GraphEvidence(
                        nodes=[director_id, *current_movie_ids],
                        edges=[
                            (mid, director_id, "DIRECTED_BY")
                            for mid in current_movie_ids
                        ],
                    ),
                    metadata={
                        "director": entry["name"],
                        "movies": current_titles,
                        "gap_days": gap_days,
                        "next_screening_date": first_current_date,
                    },
                )
            )
        return observations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k DirectorReturn`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git commit -m "feat: add DirectorReturn motif"
```

---

### Task 5: CinemaGenreFocus motif

**Files:**
- Modify: `flask_backend/service/motifs.py`
- Test: `flask_backend/tests/test_service/test_motifs.py`

**Interfaces:**
- Consumes: same as Task 2.
- Produces: `CinemaGenreFocusMotif` class with `CINEMA_GENRE_FOCUS_MULTIPLIER = 1.5` and `CINEMA_GENRE_FOCUS_MIN_COUNT = 3` module-level constants.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_motifs.py`:

```python
import calendar

from flask_backend.repository.genres import (
    get_or_create_by_tmdb_id as get_or_create_genre,
)
from flask_backend.service.motifs import CinemaGenreFocusMotif


def _this_month_date(day_offset=0):
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    day = min(15 + day_offset, last_day)
    return today.replace(day=day)


class TestCinemaGenreFocusMotif:
    def test_flags_genre_with_no_historical_precedent_and_min_count_met(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            cinema = get_cinema_by_slug("capitolio")
            for i in range(3):
                movie = Movie(title=f"Doc {i}", slug=f"doc-{i}")
                movie.genres = [doc_genre]
                movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = CinemaGenreFocusMotif().detect(graph)

            assert len(observations) == 1
            assert observations[0].motif_name == "cinema_genre_focus"
            assert observations[0].metadata["cinema"] == "Cinemateca Capitólio"
            assert observations[0].metadata["genre"] == "Documentário"

    def test_does_not_flag_genre_below_the_minimum_count(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            cinema = get_cinema_by_slug("capitolio")
            for i in range(2):
                movie = Movie(title=f"Doc {i}", slug=f"doc-{i}")
                movie.genres = [doc_genre]
                movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert CinemaGenreFocusMotif().detect(graph) == []

    def test_does_not_flag_genre_matching_its_historical_share(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            drama_genre = get_or_create_genre(2, "Drama")
            cinema = get_cinema_by_slug("capitolio")

            # Historical baseline: 3 documentaries, 3 dramas, all in the past
            # (outside this month) so current-period counts don't also
            # inflate the baseline disproportionately.
            for i in range(3):
                doc_movie = Movie(title=f"Doc Antigo {i}", slug=f"doc-antigo-{i}")
                doc_movie.genres = [doc_genre]
                doc_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=date(2025, 1, i + 1), time="19:00")],
                    )
                ]
                db_session.add(doc_movie)

                drama_movie = Movie(title=f"Drama Antigo {i}", slug=f"drama-antigo-{i}")
                drama_movie.genres = [drama_genre]
                drama_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=date(2025, 1, i + 1), time="19:00")],
                    )
                ]
                db_session.add(drama_movie)

            # Current period: same 1:1 ratio, at the minimum count.
            for i in range(3):
                doc_movie = Movie(title=f"Doc Novo {i}", slug=f"doc-novo-{i}")
                doc_movie.genres = [doc_genre]
                doc_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(doc_movie)

                drama_movie = Movie(title=f"Drama Novo {i}", slug=f"drama-novo-{i}")
                drama_movie.genres = [drama_genre]
                drama_movie.screenings = [
                    Screening(
                        cinema_id=cinema.id,
                        description="d",
                        draft=False,
                        dates=[ScreeningDate(date=_this_month_date(i), time="19:00")],
                    )
                ]
                db_session.add(drama_movie)

            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert CinemaGenreFocusMotif().detect(graph) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k CinemaGenreFocus`
Expected: FAIL with `ImportError: cannot import name 'CinemaGenreFocusMotif'`.

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/motifs.py` (add `import calendar` to the top of the file alongside the existing `from datetime import date, timedelta`):

```python
CINEMA_GENRE_FOCUS_MULTIPLIER = 1.5
CINEMA_GENRE_FOCUS_MIN_COUNT = 3


class CinemaGenreFocusMotif(Motif):
    name = "cinema_genre_focus"
    description = (
        "Detects cinemas whose current-month genre distribution is "
        f"unusually skewed toward one genre (>= {CINEMA_GENRE_FOCUS_MULTIPLIER}x "
        "its historical share at that cinema, with at least "
        f"{CINEMA_GENRE_FOCUS_MIN_COUNT} screenings this month). The "
        "historical baseline is everything strictly before the current "
        "month - it must exclude the current period, otherwise a cinema "
        "with no prior history in a genre would show current == historical "
        "(both 100%) and never trip the multiplier check."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        start = today.replace(day=1).isoformat()
        end = today.replace(day=last_day).isoformat()

        current_rows = graph.query(
            "MATCH (ci:Cinema)<-[:AT_CINEMA]-(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
            "(s)<-[:HAS_SCREENING]-(m:Movie)-[:HAS_GENRE]->(g:Genre) "
            "WHERE sd.date >= $start AND sd.date <= $end AND s.draft = false "
            "WITH ci, g, count(sd) AS screening_count, collect(m.id) AS movie_ids, "
            "collect(sd.date) AS dates "
            "RETURN ci.id AS cinema_id, ci.name AS cinema_name, g.id AS genre_id, "
            "g.name AS genre_name, screening_count, movie_ids, dates",
            {"start": start, "end": end},
        )
        historical_rows = graph.query(
            "MATCH (ci:Cinema)<-[:AT_CINEMA]-(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
            "(s)<-[:HAS_SCREENING]-(m:Movie)-[:HAS_GENRE]->(g:Genre) "
            "WHERE sd.date < $start AND s.draft = false "
            "WITH ci, g, count(sd) AS screening_count "
            "RETURN ci.id AS cinema_id, g.id AS genre_id, screening_count",
            {"start": start},
        )

        historical_by_pair: dict[tuple[str, str], int] = {}
        historical_totals: dict[str, int] = {}
        for row in historical_rows:
            key = (row["cinema_id"], row["genre_id"])
            historical_by_pair[key] = historical_by_pair.get(key, 0) + row[
                "screening_count"
            ]
            historical_totals[row["cinema_id"]] = (
                historical_totals.get(row["cinema_id"], 0) + row["screening_count"]
            )

        current_totals: dict[str, int] = {}
        for row in current_rows:
            current_totals[row["cinema_id"]] = (
                current_totals.get(row["cinema_id"], 0) + row["screening_count"]
            )

        observations = []
        for row in current_rows:
            if row["screening_count"] < CINEMA_GENRE_FOCUS_MIN_COUNT:
                continue

            cinema_total = current_totals[row["cinema_id"]]
            current_share = row["screening_count"] / cinema_total

            hist_key = (row["cinema_id"], row["genre_id"])
            hist_count = historical_by_pair.get(hist_key, 0)
            hist_total = historical_totals.get(row["cinema_id"], 0)

            if hist_total == 0 or hist_count == 0:
                qualifies = True
            else:
                historical_share = hist_count / hist_total
                qualifies = current_share >= CINEMA_GENRE_FOCUS_MULTIPLIER * historical_share

            if not qualifies:
                continue

            movie_ids = _dedupe_preserve_order(row["movie_ids"])
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=0.7,
                    score=0.0,
                    headline=(
                        f"{row['cinema_name']} em foco: {row['genre_name']}"
                    ),
                    summary=(
                        f"{row['cinema_name']} está com programação "
                        f"incomumente voltada a {row['genre_name']} este mês."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["cinema_id"], row["genre_id"], *movie_ids],
                        edges=[
                            (mid, row["genre_id"], "HAS_GENRE") for mid in movie_ids
                        ],
                    ),
                    metadata={
                        "cinema": row["cinema_name"],
                        "genre": row["genre_name"],
                        "screening_count": row["screening_count"],
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k CinemaGenreFocus`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git commit -m "feat: add CinemaGenreFocus motif"
```

---

### Task 6: Anniversary motif + MOTIF_REGISTRY

**Files:**
- Modify: `flask_backend/service/motifs.py`
- Test: `flask_backend/tests/test_service/test_motifs.py`

**Interfaces:**
- Consumes: same as Task 2.
- Produces: `AnniversaryMotif` class with `ANNIVERSARY_YEARS = {10, 20, 25, 30, 40, 50, 75, 100}` module-level constant; `MOTIF_REGISTRY: list[Motif]` module-level list containing one instance of each of the 5 motifs — this is what `motif_ranking.py` (Task 7) imports.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_motifs.py`:

```python
from flask_backend.service.motifs import MOTIF_REGISTRY, AnniversaryMotif


class TestAnniversaryMotif:
    def test_flags_movie_at_a_recognized_anniversary_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            anniversary_year = date.today().year - 50
            movie = Movie(
                title="Filme Clássico",
                slug="filme-classico",
                release_year=anniversary_year,
            )
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = AnniversaryMotif().detect(graph)

            assert len(observations) == 1
            assert observations[0].motif_name == "anniversary"
            assert observations[0].metadata["movie"] == "Filme Clássico"
            assert observations[0].metadata["years"] == 50

    def test_does_not_flag_movie_at_a_non_recognized_anniversary_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(
                title="Filme Comum",
                slug="filme-comum",
                release_year=date.today().year - 13,
            )
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert AnniversaryMotif().detect(graph) == []

    def test_does_not_flag_movie_with_no_release_year(self, app, setup_cinemas, tmp_path):
        with app.app_context():
            movie = Movie(title="Sem Ano", slug="sem-ano")
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert AnniversaryMotif().detect(graph) == []


class TestMotifRegistry:
    def test_contains_one_instance_of_each_motif(self):
        names = {motif.name for motif in MOTIF_REGISTRY}
        assert names == {
            "multiple_movies_same_director",
            "country_cluster",
            "director_return",
            "cinema_genre_focus",
            "anniversary",
        }
        assert len(MOTIF_REGISTRY) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v -k "Anniversary or Registry"`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `flask_backend/service/motifs.py`:

```python
ANNIVERSARY_YEARS = {10, 20, 25, 30, 40, 50, 75, 100}


class AnniversaryMotif(Motif):
    name = "anniversary"
    description = (
        "Detects currently-screening movies whose age since release "
        f"matches a recognized anniversary year: {sorted(ANNIVERSARY_YEARS)}."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        rows = graph.query(
            "MATCH (m:Movie)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->"
            "(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "RETURN m.id AS movie_id, m.title AS title, m.release_year AS "
            "release_year, sd.date AS date "
            "ORDER BY m.title, sd.date",
            {"today": today},
        )

        by_movie: dict[str, dict] = {}
        for row in rows:
            entry = by_movie.setdefault(
                row["movie_id"],
                {
                    "title": row["title"],
                    "release_year": row["release_year"],
                    "dates": [],
                },
            )
            entry["dates"].append(row["date"])

        current_year = date.today().year
        observations = []
        for movie_id, entry in by_movie.items():
            if entry["release_year"] is None:
                continue
            years = current_year - entry["release_year"]
            if years not in ANNIVERSARY_YEARS:
                continue

            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=1.0,
                    score=0.0,
                    headline=f"{entry['title']} completa {years} anos em cartaz",
                    summary=(
                        f"{entry['title']}, lançado há {years} anos, está "
                        "de volta aos cinemas."
                    ),
                    evidence=GraphEvidence(nodes=[movie_id], edges=[]),
                    metadata={
                        "movie": entry["title"],
                        "years": years,
                        "next_screening_date": min(entry["dates"]),
                    },
                )
            )
        return observations


MOTIF_REGISTRY: list[Motif] = [
    MultipleMoviesSameDirectorMotif(),
    CountryClusterMotif(),
    DirectorReturnMotif(),
    CinemaGenreFocusMotif(),
    AnniversaryMotif(),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motifs.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git commit -m "feat: add Anniversary motif and MOTIF_REGISTRY"
```

---

### Task 7: Ranking, deduplication, and run_motifs()

**Files:**
- Create: `flask_backend/service/motif_ranking.py`
- Test: `flask_backend/tests/test_service/test_motif_ranking.py`

**Interfaces:**
- Consumes: `Observation`, `GraphEvidence`, `MOTIF_REGISTRY` from `flask_backend.service.motifs` (Tasks 1–6).
- Produces: `rank_observations(observations: list[Observation]) -> list[Observation]`, `run_motifs(db_path: str | None = None) -> list[Observation]`, module-level `GRAPH_DB_PATH` (mirrors `graph_queries.py`'s pattern so tests can `monkeypatch` it).

- [ ] **Step 1: Write the failing test**

Create `flask_backend/tests/test_service/test_motif_ranking.py`:

```python
"""
Tests flask_backend/service/motif_ranking.py.
"""

from datetime import date, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_sync import sync_graph
from flask_backend.service.motif_ranking import rank_observations, run_motifs
from flask_backend.service.motifs import GraphEvidence, Observation


def _observation(motif_name, nodes, next_screening_date, confidence=1.0):
    return Observation(
        motif_name=motif_name,
        confidence=confidence,
        score=0.0,
        headline="h",
        summary="s",
        evidence=GraphEvidence(nodes=nodes, edges=[]),
        metadata={"next_screening_date": next_screening_date},
    )


class TestRankObservations:
    def test_returns_empty_list_for_empty_input(self):
        assert rank_observations([]) == []

    def test_sorts_by_score_descending(self):
        today = date.today().isoformat()
        far_future = (date.today() + timedelta(days=90)).isoformat()

        # Same motif (so rarity ties), but one is timely and one is not,
        # and the timely one has more evidence nodes (graph_complexity) -
        # both push its score above the other's.
        near = _observation("m", ["a", "b", "c"], today)
        far = _observation("m", ["d"], far_future)

        ranked = rank_observations([far, near])

        assert ranked[0] is near
        assert ranked[1] is far
        assert ranked[0].score > ranked[1].score

    def test_rarity_penalizes_motifs_with_many_siblings(self):
        today = date.today().isoformat()
        solo = _observation("solo_motif", ["a"], today)
        crowded = [
            _observation("crowded_motif", [f"n{i}"], today) for i in range(5)
        ]

        ranked = rank_observations([solo, *crowded])

        solo_score = next(o.score for o in ranked if o.motif_name == "solo_motif")
        crowded_score = next(
            o.score for o in ranked if o.motif_name == "crowded_motif"
        )
        assert solo_score > crowded_score

    def test_merges_observations_with_overlapping_evidence(self):
        today = date.today().isoformat()
        low = _observation("anniversary", ["movie:1"], today)
        high = _observation("director_return", ["movie:1", "director:1"], today)

        ranked = rank_observations([low, high])

        assert len(ranked) == 1
        survivor = ranked[0]
        assert survivor.motif_name == "director_return"
        assert survivor.metadata["merged_from"] == ["anniversary"]

    def test_does_not_merge_observations_with_disjoint_evidence(self):
        today = date.today().isoformat()
        a = _observation("motif_a", ["movie:1"], today)
        b = _observation("motif_b", ["movie:2"], today)

        ranked = rank_observations([a, b])

        assert len(ranked) == 2


class TestRunMotifs:
    def test_returns_ranked_observations_from_a_real_graph(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie_a = Movie(title="Paris, Texas", slug="paris-texas")
            movie_a.directors = [director]
            movie_a.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(
                            date=date.today() + timedelta(days=1), time="19:00"
                        )
                    ],
                )
            ]
            movie_b = Movie(title="Perfect Days", slug="perfect-days")
            movie_b.directors = [director]
            movie_b.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(
                            date=date.today() + timedelta(days=2), time="19:00"
                        )
                    ],
                )
            ]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            observations = run_motifs(db_path=db_path)

            assert len(observations) == 1
            assert observations[0].motif_name == "multiple_movies_same_director"
            assert observations[0].score > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motif_ranking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'flask_backend.service.motif_ranking'`.

- [ ] **Step 3: Write minimal implementation**

Create `flask_backend/service/motif_ranking.py`:

```python
"""Scores, deduplicates, and ranks the Observations produced by every motif
in MOTIF_REGISTRY. See flask_backend/service/motifs.py for the motifs
themselves and docs/superpowers/specs/2026-08-03-motif-detection-design.md
for the ranking formula's rationale (the PRD's historical_significance
signal is dropped - no honest data to back it with yet)."""

from datetime import date

from graphqlite import Graph

from flask_backend.env_config import GRAPH_DB_PATH
from flask_backend.service.motifs import MOTIF_REGISTRY, Observation

RARITY_WEIGHT = 0.45
TIMELINESS_WEIGHT = 0.30
GRAPH_COMPLEXITY_WEIGHT = 0.25

TIMELINESS_FULL_SCORE_DAYS = 7
TIMELINESS_ZERO_SCORE_DAYS = 60
GRAPH_COMPLEXITY_NODE_CAP = 10


def _open(db_path: str | None = None) -> Graph:
    return Graph(db_path or GRAPH_DB_PATH)


def _timeliness(observation: Observation) -> float:
    next_date_str = observation.metadata.get("next_screening_date")
    if not next_date_str:
        return 0.0

    days_until = (date.fromisoformat(next_date_str) - date.today()).days
    if days_until <= TIMELINESS_FULL_SCORE_DAYS:
        return 1.0
    if days_until >= TIMELINESS_ZERO_SCORE_DAYS:
        return 0.0

    span = TIMELINESS_ZERO_SCORE_DAYS - TIMELINESS_FULL_SCORE_DAYS
    return 1.0 - (days_until - TIMELINESS_FULL_SCORE_DAYS) / span


def _score(observation: Observation, sibling_count: int) -> float:
    rarity = 1 / sibling_count
    timeliness = _timeliness(observation)
    graph_complexity = min(
        len(observation.evidence.nodes) / GRAPH_COMPLEXITY_NODE_CAP, 1.0
    )
    return (
        RARITY_WEIGHT * rarity
        + TIMELINESS_WEIGHT * timeliness
        + GRAPH_COMPLEXITY_WEIGHT * graph_complexity
    )


def _deduplicate(observations: list[Observation]) -> list[Observation]:
    """Merges observations whose evidence node sets overlap: the
    higher-scored observation survives, the lower-scored one's motif_name
    is recorded in the survivor's metadata['merged_from'] and it is
    dropped."""
    kept: list[Observation] = []
    for obs in observations:
        obs_nodes = set(obs.evidence.nodes)
        match_index = next(
            (
                i
                for i, existing in enumerate(kept)
                if obs_nodes & set(existing.evidence.nodes)
            ),
            None,
        )
        if match_index is None:
            kept.append(obs)
            continue

        existing = kept[match_index]
        if obs.score > existing.score:
            obs.metadata.setdefault("merged_from", []).append(existing.motif_name)
            kept[match_index] = obs
        else:
            existing.metadata.setdefault("merged_from", []).append(obs.motif_name)
    return kept


def rank_observations(observations: list[Observation]) -> list[Observation]:
    if not observations:
        return []

    motif_counts: dict[str, int] = {}
    for obs in observations:
        motif_counts[obs.motif_name] = motif_counts.get(obs.motif_name, 0) + 1

    for obs in observations:
        obs.score = _score(obs, motif_counts[obs.motif_name])

    deduped = _deduplicate(observations)
    return sorted(deduped, key=lambda o: o.score, reverse=True)


def run_motifs(db_path: str | None = None) -> list[Observation]:
    graph = _open(db_path)
    observations: list[Observation] = []
    for motif in MOTIF_REGISTRY:
        observations.extend(motif.detect(graph))
    return rank_observations(observations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motif_ranking.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/motif_ranking.py flask_backend/tests/test_service/test_motif_ranking.py
git commit -m "feat: add motif ranking, deduplication, and run_motifs orchestrator"
```

---

### Task 8: detect-motifs CLI command

**Files:**
- Modify: `flask_backend/commands.py`
- Test: `flask_backend/tests/test_service/test_motif_commands.py`

**Interfaces:**
- Consumes: `run_motifs`, `GRAPH_DB_PATH` from `flask_backend.service.motif_ranking` (Task 7).
- Produces: `detect_motifs_command` click command, registered as `detect-motifs`.

- [ ] **Step 1: Write the failing test**

Create `flask_backend/tests/test_service/test_motif_commands.py`:

```python
"""
Tests the detect-motifs CLI command in flask_backend/commands.py.
"""

import json
from datetime import date, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_sync import sync_graph


class TestDetectMotifsCommand:
    def _seed_two_movies_by_same_director(self):
        director = get_or_create_director(1, "Wim Wenders")
        movie_a = Movie(title="Paris, Texas", slug="paris-texas")
        movie_a.directors = [director]
        movie_a.screenings = [
            Screening(
                cinema_id=get_cinema_by_slug("capitolio").id,
                description="d",
                draft=False,
                dates=[
                    ScreeningDate(
                        date=date.today() + timedelta(days=1), time="19:00"
                    )
                ],
            )
        ]
        movie_b = Movie(title="Perfect Days", slug="perfect-days")
        movie_b.directors = [director]
        movie_b.screenings = [
            Screening(
                cinema_id=get_cinema_by_slug("capitolio").id,
                description="d",
                draft=False,
                dates=[
                    ScreeningDate(
                        date=date.today() + timedelta(days=2), time="19:00"
                    )
                ],
            )
        ]
        db_session.add_all([movie_a, movie_b])
        db_session.commit()

    def test_prints_ranked_observations_as_a_table(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            self._seed_two_movies_by_same_director()
            sync_graph()

        result = runner.invoke(args=["detect-motifs"])

        assert result.exit_code == 0
        assert "multiple_movies_same_director" in result.output
        assert "Wim Wenders" in result.output

    def test_json_flag_prints_full_observation_objects(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            self._seed_two_movies_by_same_director()
            sync_graph()

        result = runner.invoke(args=["detect-motifs", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["motif_name"] == "multiple_movies_same_director"
        assert "evidence" in payload[0]

    def test_limit_option_caps_the_number_of_results(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            self._seed_two_movies_by_same_director()
            sync_graph()

        result = runner.invoke(args=["detect-motifs", "--json", "--limit", "0"])

        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_no_observations_prints_no_results_message(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )
        with app.app_context():
            sync_graph()

        result = runner.invoke(args=["detect-motifs"])

        assert result.exit_code == 0
        assert "Nenhuma observação." in result.output

    def test_missing_graph_file_raises_usage_error_naming_sync_graph(
        self, app, runner, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "never-synced.db")
        monkeypatch.setattr(
            "flask_backend.service.motif_ranking.GRAPH_DB_PATH", db_path
        )

        result = runner.invoke(args=["detect-motifs"])

        assert result.exit_code != 0
        assert db_path in result.output
        assert "sync-graph" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_service/test_motif_commands.py -v`
Expected: FAIL with `Error: No such command 'detect-motifs'`.

- [ ] **Step 3: Write minimal implementation**

In `flask_backend/commands.py`:

1. Add `app.cli.add_command(detect_motifs_command)` inside `register_commands()`, right after the existing `app.cli.add_command(graph_query_command)` line.

2. Append this command definition after `graph_query_command` (near the bottom of the file, keeping it next to the other graph-related commands):

```python
@click.command("detect-motifs")
@click.option(
    "--limit", type=int, default=10, help="Número máximo de observações a exibir."
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Imprime as observações completas (com evidências) em JSON.",
)
def detect_motifs_command(limit, as_json):
    """Executa o motor de detecção de motivos editoriais sobre o grafo de
    conhecimento e imprime as observações de maior pontuação.
    """
    import dataclasses

    from flask_backend.service import motif_ranking

    if not os.path.exists(motif_ranking.GRAPH_DB_PATH):
        raise click.UsageError(
            f"Grafo não encontrado em {motif_ranking.GRAPH_DB_PATH}. "
            "Rode `flask --app flask_backend sync-graph` primeiro."
        )

    observations = motif_ranking.run_motifs()[:limit]

    if as_json:
        click.echo(
            json.dumps(
                [dataclasses.asdict(o) for o in observations],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not observations:
        click.echo("Nenhuma observação.")
        return

    for observation in observations:
        click.echo(
            f"{observation.score:.2f} | {observation.motif_name} | "
            f"{observation.headline}"
        )
```

`json` and `os` are already imported at the top of `flask_backend/commands.py` — no new top-level imports are needed beyond the function-local `dataclasses` and `motif_ranking` imports (matching the existing lazy-import style used by `sync_graph_command`/`graph_query_command`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest flask_backend/tests/test_service/test_motif_commands.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add flask_backend/commands.py flask_backend/tests/test_service/test_motif_commands.py
git commit -m "feat: add detect-motifs CLI command"
```

---

### Task 9: Full suite, lint, format

**Files:** none created; verification only.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass (baseline was 755 passed before this feature; the new files add roughly 25-30 tests).

- [ ] **Step 2: Lint and format**

Run:
```bash
uv run ruff check --fix flask_backend/service/motifs.py flask_backend/service/motif_ranking.py flask_backend/commands.py flask_backend/tests/test_service/test_motifs.py flask_backend/tests/test_service/test_motif_ranking.py flask_backend/tests/test_service/test_motif_commands.py
uv run ruff format flask_backend/service/motifs.py flask_backend/service/motif_ranking.py flask_backend/commands.py flask_backend/tests/test_service/test_motifs.py flask_backend/tests/test_service/test_motif_ranking.py flask_backend/tests/test_service/test_motif_commands.py
```
Expected: no remaining lint errors; formatting applied cleanly.

- [ ] **Step 3: Re-run the full test suite after formatting**

Run: `uv run pytest -q`
Expected: all tests still pass (formatting must not have changed behavior).

- [ ] **Step 4: Commit if ruff/format changed anything**

```bash
git add -A
git status
# Only commit if there are actual changes from ruff/format:
git commit -m "chore: lint and format motif detection files"
```

If `git status` shows no changes, skip this commit.
