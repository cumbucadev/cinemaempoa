# Knowledge Layer Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Phase 1 knowledge graph — a GraphQLite database derived from `flask_backend.sqlite` — with a manual `sync-graph` CLI command to (re)build it and a `graph-query` CLI command to run five proof-of-concept Cypher queries against it.

**Architecture:** A new `flask_backend/service/graph_sync.py` reads Movie/Cinema/Screening/ScreeningDate/Genre/Director/Country rows via SQLAlchemy, wipes the GraphQLite file, and bulk-inserts a fresh graph every run (full rebuild, not incremental). A new `flask_backend/service/graph_queries.py` wraps five read-only Cypher queries as typed Python functions. Two new Click commands (`sync-graph`, `graph-query`) expose both, following the existing `commands.py` pattern.

**Tech Stack:** GraphQLite (`graphqlite` PyPI package, MIT license) — a SQLite-extension embedded graph database with Cypher support — added as a new dependency. Everything else uses the existing Flask/SQLAlchemy/Click/pytest stack; no other new dependencies.

## Global Constraints

- Python 3.14.x via `uv` (project already pinned to `>=3.14.5,<3.15` in `pyproject.toml`).
- Run `uv run ruff check --fix` and `uv run ruff format` before any commit that touches `.py` files — CI fails on unformatted code.
- Test coverage must not regress below the project's `fail_under = 90` threshold (`pyproject.toml` `[tool.coverage.report]`).
- No mocking of GraphQLite itself in tests — exercise the real extension against small real fixture data, per this project's existing test philosophy (`flask_backend/tests/README.md`).
- Every new/modified `.py` file follows the existing `service/`/`repository/` module conventions already present in the codebase (see Task 1 onward for exact precedents).
- Never add a `Co-Authored-By` AI trailer to commits (per `CLAUDE.md`).

---

## Reference: GraphQLite Python API

Confirmed from the library's README and docs (`pip install graphqlite`, MIT license, wheels published for `manylinux2014_x86_64`, Python `>=3.8` — compatible with this project's Python 3.14):

```python
from graphqlite import Graph

g = Graph(db_path)  # ":memory:" or a file path

# Single upserts
g.upsert_node(node_id: str, props: dict, label: str = "Entity") -> int
g.upsert_edge(source: str, target: str, props: dict, rel_type: str = "RELATED") -> int

# Bulk insert (100-500x faster than per-row Cypher CREATE; bypasses the parser)
g.insert_nodes_bulk(nodes: list[tuple[str, dict, str]]) -> dict  # id_map: external_id -> rowid
g.insert_edges_bulk(edges: list[tuple[str, str, dict, str]], id_map: dict) -> None
g.insert_graph_bulk(nodes, edges) -> result  # result.nodes_inserted, result.edges_inserted, result.id_map

# Cypher queries — returns a list of dicts keyed by each RETURN alias
g.query(cypher: str, params: dict | None = None) -> list[dict]
```

Node/edge tuple shapes:
- Node: `(external_id: str, properties: dict, label: str)`
- Edge: `(source_external_id: str, target_external_id: str, properties: dict, rel_type: str)`

`external_id` must be globally unique across the whole graph (not just within a label), so every node builder in this plan prefixes it with its label, e.g. `f"movie:{movie.id}"`, `f"genre:{genre.id}"`. The `sqlite_id` **property** (a plain int) is what queries filter on — the prefixed string is purely a sync-time wiring key.

Full wipe uses plain Cypher: `MATCH (n) DETACH DELETE n` (DELETE is at 100% TCK coverage per the library's own conformance table).

---

### Task 1: Add the GraphQLite dependency and config

**Files:**
- Modify: `pyproject.toml`
- Modify: `flask_backend/env_config.py`
- Create: `flask_backend/tests/test_service/test_graph_sync.py`

**Interfaces:**
- Produces: `flask_backend.env_config.GRAPH_DB_PATH: str` (default `"./flask_backend_graph.sqlite"`) — consumed by Task 4's `sync_graph()`.

- [ ] **Step 1: Add the dependency**

Run: `uv add graphqlite`

This updates `pyproject.toml` and `uv.lock`. Every other dependency in `pyproject.toml` is pinned with `==exact.version`; open `pyproject.toml` after running the command and confirm the new `graphqlite` line matches that style (e.g. `"graphqlite==0.6.0"`) — if `uv add` produced a range instead, edit it to an exact pin for consistency with the rest of the file.

- [ ] **Step 2: Verify the extension actually loads on this platform**

Run: `uv run python -c "from graphqlite import Graph; g = Graph(':memory:'); g.upsert_node('a', {'name': 'A'}, label='Thing'); print(g.query('MATCH (t:Thing) RETURN t.name AS name'))"`

Expected output: `[{'name': 'A'}]`. If this fails (e.g. missing platform wheel), stop and report — the rest of this plan depends on it.

- [ ] **Step 3: Add `GRAPH_DB_PATH` to env_config.py**

Add this line to `flask_backend/env_config.py`, near `UPLOAD_DIR` (both are file-path settings):

```python
GRAPH_DB_PATH = config("GRAPH_DB_PATH", default="./flask_backend_graph.sqlite")
```

- [ ] **Step 4: Write a smoke test locking in the API shape this plan relies on**

Create `flask_backend/tests/test_service/test_graph_sync.py`:

```python
"""
Tests flask_backend/service/graph_sync.py.
"""


class TestGraphqliteSmokeTest:
    def test_extension_loads_and_supports_basic_cypher(self, tmp_path):
        from graphqlite import Graph

        db_path = str(tmp_path / "smoke.db")
        graph = Graph(db_path)
        graph.upsert_node("a", {"name": "A"}, label="Thing")
        graph.upsert_node("b", {"name": "B"}, label="Thing")
        graph.upsert_edge("a", "b", {}, rel_type="RELATED")

        results = graph.query(
            "MATCH (x:Thing)-[:RELATED]->(y:Thing) "
            "RETURN x.name AS x_name, y.name AS y_name"
        )

        assert results == [{"x_name": "A", "y_name": "B"}]
```

- [ ] **Step 5: Run the test**

Run: `pytest flask_backend/tests/test_service/test_graph_sync.py -v`
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock flask_backend/env_config.py flask_backend/tests/test_service/test_graph_sync.py
git commit -m "feat: add graphqlite dependency and GRAPH_DB_PATH config"
```

---

### Task 2: Add `get_all()` to the genre, director, and country repositories

The `graph_sync` module (Task 3) needs every `Genre`/`Director`/`Country` row, not just the `get_or_create_by_*` lookups these repositories currently expose. Follows the existing unfiltered `cinemas.get_all()` precedent (`flask_backend/repository/cinemas.py:9-11`).

**Files:**
- Modify: `flask_backend/repository/genres.py`
- Modify: `flask_backend/repository/directors.py`
- Modify: `flask_backend/repository/countries.py`
- Create: `flask_backend/tests/test_repository/test_genres.py`
- Create: `flask_backend/tests/test_repository/test_directors.py`
- Create: `flask_backend/tests/test_repository/test_countries.py`

**Interfaces:**
- Produces: `repository.genres.get_all() -> List[Genre]`, `repository.directors.get_all() -> List[Director]`, `repository.countries.get_all() -> List[Country]` — consumed by Task 3's `build_graph_data()`.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_repository/test_genres.py`:

```python
"""
Tests flask_backend/repository/genres.py.
"""

from flask_backend.repository.genres import get_all, get_or_create_by_tmdb_id


class TestGetAll:
    def test_returns_every_genre_ordered_by_name(self, app):
        with app.app_context():
            get_or_create_by_tmdb_id(2, "Drama")
            get_or_create_by_tmdb_id(1, "Comédia")

            genres = get_all()

            assert [g.name for g in genres] == ["Comédia", "Drama"]
```

Create `flask_backend/tests/test_repository/test_directors.py`:

```python
"""
Tests flask_backend/repository/directors.py.
"""

from flask_backend.repository.directors import get_all, get_or_create_by_tmdb_id


class TestGetAll:
    def test_returns_every_director_ordered_by_name(self, app):
        with app.app_context():
            get_or_create_by_tmdb_id(2, "Wim Wenders")
            get_or_create_by_tmdb_id(1, "Agnès Varda")

            directors = get_all()

            assert [d.name for d in directors] == ["Agnès Varda", "Wim Wenders"]
```

Create `flask_backend/tests/test_repository/test_countries.py`:

```python
"""
Tests flask_backend/repository/countries.py.
"""

from flask_backend.repository.countries import get_all, get_or_create_by_iso_code


class TestGetAll:
    def test_returns_every_country_ordered_by_name(self, app):
        with app.app_context():
            get_or_create_by_iso_code("US", "United States of America")
            get_or_create_by_iso_code("BR", "Brazil")

            countries = get_all()

            assert [c.name for c in countries] == ["Brazil", "United States of America"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_genres.py flask_backend/tests/test_repository/test_directors.py flask_backend/tests/test_repository/test_countries.py -v`
Expected: all 3 FAIL with `ImportError: cannot import name 'get_all'`.

- [ ] **Step 3: Implement `get_all()` in each repository**

In `flask_backend/repository/genres.py`, add (and add `from typing import List` plus `asc` import):

```python
from typing import List

from sqlalchemy import asc

from flask_backend.db import db_session
from flask_backend.models import Genre


def get_all() -> List[Genre]:
    return db_session.query(Genre).order_by(asc(Genre.name)).all()


def get_or_create_by_tmdb_id(tmdb_id: int, name: str) -> Genre:
    genre = db_session.query(Genre).filter(Genre.tmdb_id == tmdb_id).first()
    if genre is None:
        genre = Genre(tmdb_id=tmdb_id, name=name)
        db_session.add(genre)
        db_session.commit()
        db_session.refresh(genre)
    return genre
```

In `flask_backend/repository/directors.py`, same shape:

```python
from typing import List

from sqlalchemy import asc

from flask_backend.db import db_session
from flask_backend.models import Director


def get_all() -> List[Director]:
    return db_session.query(Director).order_by(asc(Director.name)).all()


def get_or_create_by_tmdb_id(tmdb_id: int, name: str) -> Director:
    director = db_session.query(Director).filter(Director.tmdb_id == tmdb_id).first()
    if director is None:
        director = Director(tmdb_id=tmdb_id, name=name)
        db_session.add(director)
        db_session.commit()
        db_session.refresh(director)
    return director
```

In `flask_backend/repository/countries.py`, same shape:

```python
from typing import List

from sqlalchemy import asc

from flask_backend.db import db_session
from flask_backend.models import Country


def get_all() -> List[Country]:
    return db_session.query(Country).order_by(asc(Country.name)).all()


def get_or_create_by_iso_code(iso_3166_1: str, name: str) -> Country:
    country = db_session.query(Country).filter(Country.iso_3166_1 == iso_3166_1).first()
    if country is None:
        country = Country(iso_3166_1=iso_3166_1, name=name)
        db_session.add(country)
        db_session.commit()
        db_session.refresh(country)
    return country
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_genres.py flask_backend/tests/test_repository/test_directors.py flask_backend/tests/test_repository/test_countries.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/repository/genres.py flask_backend/repository/directors.py flask_backend/repository/countries.py flask_backend/tests/test_repository/test_genres.py flask_backend/tests/test_repository/test_directors.py flask_backend/tests/test_repository/test_countries.py
git commit -m "feat: add get_all() to genre, director, and country repositories"
```

---

### Task 3: Build `graph_sync.build_graph_data()` — the SQLite-to-graph-tuples transform

Pure data transformation: reads SQLAlchemy models, returns node/edge tuples. No GraphQLite writes yet — that's Task 4. Keeping this pure makes it trivial to test without touching the graph engine.

**Files:**
- Create: `flask_backend/service/graph_sync.py`
- Modify: `flask_backend/tests/test_service/test_graph_sync.py`

**Interfaces:**
- Consumes: `repository.cinemas.get_all() -> List[Cinema]`, `repository.genres.get_all() -> List[Genre]`, `repository.directors.get_all() -> List[Director]`, `repository.countries.get_all() -> List[Country]` (Task 2); `flask_backend.models.Movie`, `.Screening` (queried directly — see note below).
- Produces: `graph_sync.build_graph_data() -> tuple[list[NodeTuple], list[EdgeTuple]]`, `graph_sync.NodeTuple = tuple[str, dict, str]`, `graph_sync.EdgeTuple = tuple[str, str, dict, str]` — consumed by Task 4's `sync_graph()`.

**Design note on why `Movie`/`Screening` are queried directly instead of via a repository `get_all()`:** the existing `repository.movies.get_all()` (`flask_backend/repository/movies.py:35-40`) filters to movies with a non-draft screening — it's built for the public movie-listing page, not a faithful full sync. There's no unfiltered equivalent for `Screening` either. Rather than bend those functions' existing contracts (used elsewhere) or add a sync-specific name that doesn't fit the repository layer's general-purpose intent, `graph_sync.py` queries `db_session.query(Movie).all()` and `db_session.query(Screening).all()` directly — matching the PRD's "represent only explicit facts already present" requirement (no draft filtering, no screening-existence filtering).

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_graph_sync.py`:

```python
from datetime import date

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.countries import get_or_create_by_iso_code
from flask_backend.repository.directors import get_or_create_by_tmdb_id as get_or_create_director
from flask_backend.repository.genres import get_or_create_by_tmdb_id as get_or_create_genre
from flask_backend.service.graph_sync import build_graph_data


class TestBuildGraphData:
    def test_builds_nodes_and_edges_for_a_full_movie_record(self, app, setup_cinemas):
        with app.app_context():
            genre = get_or_create_genre(1, "Drama")
            director = get_or_create_director(1, "Wim Wenders")
            country = get_or_create_by_iso_code("DE", "Germany")

            movie = Movie(
                title="Paris, Texas",
                slug="paris-texas",
                original_title="Paris, Texas",
                release_year=1984,
                original_language="en",
                tmdb_id=1071,
            )
            movie.genres = [genre]
            movie.directors = [director]
            movie.countries = [country]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()
            db_session.refresh(movie)
            screening = movie.screenings[0]
            screening_date = screening.dates[0]

            nodes, edges = build_graph_data()

            node_ids = {n[0] for n in nodes}
            assert f"movie:{movie.id}" in node_ids
            assert f"cinema:{get_cinema_by_slug('capitolio').id}" in node_ids
            assert f"genre:{genre.id}" in node_ids
            assert f"director:{director.id}" in node_ids
            assert f"country:{country.id}" in node_ids
            assert f"screening:{screening.id}" in node_ids
            assert f"screeningdate:{screening_date.id}" in node_ids

            movie_node = next(n for n in nodes if n[0] == f"movie:{movie.id}")
            assert movie_node == (
                f"movie:{movie.id}",
                {
                    "sqlite_id": movie.id,
                    "title": "Paris, Texas",
                    "slug": "paris-texas",
                    "original_title": "Paris, Texas",
                    "release_year": 1984,
                    "original_language": "en",
                    "tmdb_id": 1071,
                },
                "Movie",
            )

            screening_date_node = next(
                n for n in nodes if n[0] == f"screeningdate:{screening_date.id}"
            )
            assert screening_date_node == (
                f"screeningdate:{screening_date.id}",
                {"sqlite_id": screening_date.id, "date": "2026-08-01", "time": "19:00"},
                "ScreeningDate",
            )

            assert (
                f"movie:{movie.id}",
                f"genre:{genre.id}",
                {},
                "HAS_GENRE",
            ) in edges
            assert (
                f"movie:{movie.id}",
                f"director:{director.id}",
                {},
                "DIRECTED_BY",
            ) in edges
            assert (
                f"movie:{movie.id}",
                f"country:{country.id}",
                {},
                "PRODUCED_IN",
            ) in edges
            assert (
                f"movie:{movie.id}",
                f"screening:{screening.id}",
                {},
                "HAS_SCREENING",
            ) in edges
            assert (
                f"screening:{screening.id}",
                f"cinema:{get_cinema_by_slug('capitolio').id}",
                {},
                "AT_CINEMA",
            ) in edges
            assert (
                f"screening:{screening.id}",
                f"screeningdate:{screening_date.id}",
                {},
                "HAS_DATE",
            ) in edges

    def test_includes_movies_with_no_screenings_and_no_metadata(self, app):
        with app.app_context():
            movie = Movie(title="Sem Sessão", slug="sem-sessao")
            db_session.add(movie)
            db_session.commit()

            nodes, _edges = build_graph_data()

            node_ids = {n[0] for n in nodes}
            assert f"movie:{movie.id}" in node_ids
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_graph_sync.py::TestBuildGraphData -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError: cannot import name 'build_graph_data'`.

- [ ] **Step 3: Implement `graph_sync.py`**

Create `flask_backend/service/graph_sync.py`:

```python
from typing import Dict, List, Tuple

from flask_backend.db import db_session
from flask_backend.models import Country, Director, Genre, Movie, Screening
from flask_backend.repository import cinemas as cinemas_repo
from flask_backend.repository import countries as countries_repo
from flask_backend.repository import directors as directors_repo
from flask_backend.repository import genres as genres_repo

NodeTuple = Tuple[str, dict, str]
EdgeTuple = Tuple[str, str, dict, str]


def _movie_node(movie: Movie) -> NodeTuple:
    return (
        f"movie:{movie.id}",
        {
            "sqlite_id": movie.id,
            "title": movie.title,
            "slug": movie.slug,
            "original_title": movie.original_title,
            "release_year": movie.release_year,
            "original_language": movie.original_language,
            "tmdb_id": movie.tmdb_id,
        },
        "Movie",
    )


def _cinema_node(cinema) -> NodeTuple:
    return (
        f"cinema:{cinema.id}",
        {"sqlite_id": cinema.id, "slug": cinema.slug, "name": cinema.name},
        "Cinema",
    )


def _screening_node(screening: Screening) -> NodeTuple:
    return (
        f"screening:{screening.id}",
        {"sqlite_id": screening.id, "url": screening.url, "draft": screening.draft},
        "Screening",
    )


def _screening_date_node(screening_date) -> NodeTuple:
    return (
        f"screeningdate:{screening_date.id}",
        {
            "sqlite_id": screening_date.id,
            "date": screening_date.date.isoformat(),
            "time": screening_date.time,
        },
        "ScreeningDate",
    )


def _genre_node(genre: Genre) -> NodeTuple:
    return (
        f"genre:{genre.id}",
        {"sqlite_id": genre.id, "tmdb_id": genre.tmdb_id, "name": genre.name},
        "Genre",
    )


def _director_node(director: Director) -> NodeTuple:
    return (
        f"director:{director.id}",
        {"sqlite_id": director.id, "tmdb_id": director.tmdb_id, "name": director.name},
        "Director",
    )


def _country_node(country: Country) -> NodeTuple:
    return (
        f"country:{country.id}",
        {
            "sqlite_id": country.id,
            "iso_3166_1": country.iso_3166_1,
            "name": country.name,
        },
        "Country",
    )


def build_graph_data() -> Tuple[List[NodeTuple], List[EdgeTuple]]:
    """Reads every row Phase 1's knowledge graph cares about from SQLite and
    returns the full set of graph nodes/edges for a from-scratch rebuild.

    Unfiltered by design: the graph is meant to be a faithful mirror of
    SQLite's explicit facts, not a business-logic view (see graph_sync.py's
    module docstring reasoning in the implementation plan for why Movie and
    Screening are queried directly instead of through the repository
    layer's `get_all()` functions, which apply publish-state filtering).
    """
    nodes: List[NodeTuple] = []
    edges: List[EdgeTuple] = []

    movies = db_session.query(Movie).all()
    for movie in movies:
        nodes.append(_movie_node(movie))
        for genre in movie.genres:
            edges.append((f"movie:{movie.id}", f"genre:{genre.id}", {}, "HAS_GENRE"))
        for director in movie.directors:
            edges.append(
                (f"movie:{movie.id}", f"director:{director.id}", {}, "DIRECTED_BY")
            )
        for country in movie.countries:
            edges.append(
                (f"movie:{movie.id}", f"country:{country.id}", {}, "PRODUCED_IN")
            )

    for cinema in cinemas_repo.get_all():
        nodes.append(_cinema_node(cinema))

    for genre in genres_repo.get_all():
        nodes.append(_genre_node(genre))

    for director in directors_repo.get_all():
        nodes.append(_director_node(director))

    for country in countries_repo.get_all():
        nodes.append(_country_node(country))

    screenings = db_session.query(Screening).all()
    for screening in screenings:
        nodes.append(_screening_node(screening))
        edges.append(
            (
                f"movie:{screening.movie_id}",
                f"screening:{screening.id}",
                {},
                "HAS_SCREENING",
            )
        )
        edges.append(
            (
                f"screening:{screening.id}",
                f"cinema:{screening.cinema_id}",
                {},
                "AT_CINEMA",
            )
        )
        for screening_date in screening.dates:
            nodes.append(_screening_date_node(screening_date))
            edges.append(
                (
                    f"screening:{screening.id}",
                    f"screeningdate:{screening_date.id}",
                    {},
                    "HAS_DATE",
                )
            )

    return nodes, edges
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_graph_sync.py -v`
Expected: `3 passed` (the Task 1 smoke test plus these two).

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/graph_sync.py flask_backend/tests/test_service/test_graph_sync.py
git commit -m "feat: build graph node/edge tuples from SQLite for the knowledge graph"
```

---

### Task 4: `sync_graph()` — wipe and bulk-insert into GraphQLite

**Files:**
- Modify: `flask_backend/service/graph_sync.py`
- Modify: `flask_backend/tests/test_service/test_graph_sync.py`

**Interfaces:**
- Consumes: `graph_sync.build_graph_data()` (Task 3); `graphqlite.Graph`, `.query()`, `.insert_graph_bulk()` (see API reference above); `env_config.GRAPH_DB_PATH` (Task 1).
- Produces: `graph_sync.SyncResult` (dataclass: `nodes_created: int`, `edges_created: int`), `graph_sync.sync_graph(db_path: str | None = None) -> SyncResult` — consumed by Task 5's CLI command and Task 6-8's query tests (as fixture setup).

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_graph_sync.py`:

```python
from graphqlite import Graph

from flask_backend.service.graph_sync import sync_graph


class TestSyncGraph:
    def test_writes_nodes_and_edges_to_the_graph_file(self, app, setup_cinemas, tmp_path):
        with app.app_context():
            movie = Movie(title="Ariabescos", slug="ariabescos")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            result = sync_graph(db_path=db_path)

            assert result.nodes_created > 0
            assert result.edges_created > 0

            graph = Graph(db_path)
            rows = graph.query(
                "MATCH (m:Movie) WHERE m.slug = 'ariabescos' RETURN m.title AS title"
            )
            assert rows == [{"title": "Ariabescos"}]

    def test_is_idempotent_and_removes_stale_data_on_rerun(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            db_path = str(tmp_path / "graph.db")

            # Seed a node that has no corresponding SQLite row.
            stale_graph = Graph(db_path)
            stale_graph.upsert_node("movie:999999", {"title": "Stale"}, label="Movie")

            movie = Movie(title="Filme Real", slug="filme-real")
            db_session.add(movie)
            db_session.commit()

            first = sync_graph(db_path=db_path)
            second = sync_graph(db_path=db_path)

            assert first.nodes_created == second.nodes_created
            assert first.edges_created == second.edges_created

            graph = Graph(db_path)
            rows = graph.query(
                "MATCH (m:Movie) WHERE m.title = 'Stale' RETURN m.title AS title"
            )
            assert rows == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_graph_sync.py::TestSyncGraph -v`
Expected: FAIL with `ImportError: cannot import name 'sync_graph'`.

- [ ] **Step 3: Implement `sync_graph()`**

Add to `flask_backend/service/graph_sync.py` (add `dataclass` and `graphqlite`/`env_config` imports at the top alongside the existing ones):

```python
from dataclasses import dataclass

from graphqlite import Graph

from flask_backend.env_config import GRAPH_DB_PATH
```

Append at the end of the file:

```python
@dataclass
class SyncResult:
    nodes_created: int
    edges_created: int


def sync_graph(db_path: str = None) -> SyncResult:
    """Rebuilds the knowledge graph from scratch: wipes every node/edge in
    the GraphQLite file at db_path (or GRAPH_DB_PATH) and re-inserts a
    fresh graph from the current SQLite state. Idempotent - safe to run
    repeatedly, always converges to the same graph for the same SQLite
    state."""
    path = db_path or GRAPH_DB_PATH
    graph = Graph(path)
    graph.query("MATCH (n) DETACH DELETE n")

    nodes, edges = build_graph_data()
    result = graph.insert_graph_bulk(nodes, edges)

    return SyncResult(
        nodes_created=result.nodes_inserted, edges_created=result.edges_inserted
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_graph_sync.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/graph_sync.py flask_backend/tests/test_service/test_graph_sync.py
git commit -m "feat: sync_graph() rebuilds the knowledge graph from SQLite"
```

---

### Task 5: `sync-graph` CLI command

**Files:**
- Modify: `flask_backend/commands.py`
- Create: `flask_backend/tests/test_service/test_graph_commands.py`

**Interfaces:**
- Consumes: `graph_sync.sync_graph()` (Task 4).
- Produces: registered Click command `sync-graph` (importable as `flask_backend.commands.sync_graph_command`).

- [ ] **Step 1: Write the failing test**

Create `flask_backend/tests/test_service/test_graph_commands.py`:

```python
"""
Tests the sync-graph and graph-query CLI commands in flask_backend/commands.py.
"""


class TestSyncGraphCommand:
    def test_reports_node_and_edge_counts(self, app, runner, setup_cinemas, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "flask_backend.service.graph_sync.GRAPH_DB_PATH", str(tmp_path / "graph.db")
        )

        result = runner.invoke(args=["sync-graph"])

        assert result.exit_code == 0
        assert "nós" in result.output
        assert "arestas" in result.output
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_graph_commands.py -v`
Expected: FAIL — `sync-graph` is not a registered command (Click reports `No such command`).

- [ ] **Step 3: Add the command**

In `flask_backend/commands.py`, add `sync_graph_command` to `register_commands()`:

```python
def register_commands(app):
    app.cli.add_command(import_json)
    app.cli.add_command(dupe_check)
    app.cli.add_command(run_dedupper)
    app.cli.add_command(generate_sitemap)
    app.cli.add_command(fetch_posters)
    app.cli.add_command(poster_review)
    app.cli.add_command(fetch_movie_metadata)
    app.cli.add_command(movie_metadata_review)
    app.cli.add_command(title_cleaning_report_command)
    app.cli.add_command(title_cleaning_backfill_command)
    app.cli.add_command(delete_movie_command)
    app.cli.add_command(sync_graph_command)
```

Then add the command itself, near the other simple reporting commands (e.g. after `dupe_check`):

```python
@click.command("sync-graph")
def sync_graph_command():
    """Reconstrói o grafo de conhecimento (movies, cinemas, sessões, gêneros,
    diretores, países) a partir do SQLite.

    Apaga e recria o grafo inteiro a cada execução - comando manual, não
    faz parte de nenhum pipeline automatizado.
    """
    from flask_backend.service.graph_sync import sync_graph

    result = sync_graph()
    click.echo(
        f"Grafo sincronizado: {result.nodes_created} nós, "
        f"{result.edges_created} arestas."
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest flask_backend/tests/test_service/test_graph_commands.py -v`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/commands.py flask_backend/tests/test_service/test_graph_commands.py
git commit -m "feat: add sync-graph CLI command"
```

---

### Task 6: Query layer — `movies_by_director` and `directors_currently_showing`

**Files:**
- Create: `flask_backend/service/graph_queries.py`
- Create: `flask_backend/tests/test_service/test_graph_queries.py`

**Interfaces:**
- Consumes: `graphqlite.Graph.query()`; `env_config.GRAPH_DB_PATH`; `graph_sync.sync_graph()` (Task 4, used only in tests to populate a graph to query against).
- Produces: `graph_queries.movies_by_director(name: str, db_path: str | None = None) -> list[dict]`, `graph_queries.directors_currently_showing(db_path: str | None = None) -> list[dict]` — consumed by Task 9's CLI command.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_service/test_graph_queries.py`:

```python
"""
Tests flask_backend/service/graph_queries.py.
"""

from datetime import date, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.directors import get_or_create_by_tmdb_id as get_or_create_director
from flask_backend.service.graph_queries import (
    directors_currently_showing,
    movies_by_director,
)
from flask_backend.service.graph_sync import sync_graph


class TestMoviesByDirector:
    def test_returns_movies_directed_by_the_given_name(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie = Movie(title="Paris, Texas", slug="paris-texas")
            movie.directors = [director]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = movies_by_director("Wim Wenders", db_path=db_path)

            assert results == [{"title": "Paris, Texas", "slug": "paris-texas"}]

    def test_returns_empty_list_for_unknown_director(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert movies_by_director("Ninguém", db_path=db_path) == []


class TestDirectorsCurrentlyShowing:
    def test_returns_directors_with_an_upcoming_screening(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Agnès Varda")
            movie = Movie(title="Cléo de 5 à 7", slug="cleo-de-5-a-7")
            movie.directors = [director]
            movie.screenings = [
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
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = directors_currently_showing(db_path=db_path)

            assert results == [{"name": "Agnès Varda"}]

    def test_excludes_directors_whose_movies_have_only_past_screenings(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Diretor do Passado")
            movie = Movie(title="Filme Antigo", slug="filme-antigo")
            movie.directors = [director]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(
                            date=date.today() - timedelta(days=30), time="19:00"
                        )
                    ],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert directors_currently_showing(db_path=db_path) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_graph_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'flask_backend.service.graph_queries'`.

- [ ] **Step 3: Implement `graph_queries.py`**

Create `flask_backend/service/graph_queries.py`:

```python
from datetime import date

from graphqlite import Graph

from flask_backend.env_config import GRAPH_DB_PATH


def _open(db_path: str = None) -> Graph:
    return Graph(db_path or GRAPH_DB_PATH)


def movies_by_director(name: str, db_path: str = None) -> list[dict]:
    """Movies directed by the given director name."""
    graph = _open(db_path)
    return graph.query(
        "MATCH (m:Movie)-[:DIRECTED_BY]->(d:Director) "
        "WHERE d.name = $name "
        "RETURN m.title AS title, m.slug AS slug "
        "ORDER BY m.title",
        {"name": name},
    )


def directors_currently_showing(db_path: str = None) -> list[dict]:
    """Directors with at least one movie that has a screening today or later."""
    graph = _open(db_path)
    return graph.query(
        "MATCH (d:Director)<-[:DIRECTED_BY]-(:Movie)"
        "-[:HAS_SCREENING]->(:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
        "WHERE sd.date >= $today "
        "RETURN DISTINCT d.name AS name "
        "ORDER BY d.name",
        {"today": date.today().isoformat()},
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_graph_queries.py -v`
Expected: `4 passed`. If any Cypher clause is rejected by GraphQLite (e.g. an unsupported anonymous-node pattern `(:Movie)`), the error message will name the unsupported construct — adjust the query to name the node explicitly (`(m:Movie)`) and re-run.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/graph_queries.py flask_backend/tests/test_service/test_graph_queries.py
git commit -m "feat: add movies_by_director and directors_currently_showing graph queries"
```

---

### Task 7: Query layer — `countries_this_month` and `genres_at_cinema`

Both need a date-range filter, unlike Task 6's queries. `ScreeningDate.date` is stored as an ISO `YYYY-MM-DD` string (Task 3's `_screening_date_node`), which sorts identically whether compared lexicographically or chronologically — so both queries use plain `>=`/`<=` string comparisons against computed boundary strings, no Cypher date functions needed.

**Files:**
- Modify: `flask_backend/service/graph_queries.py`
- Modify: `flask_backend/tests/test_service/test_graph_queries.py`

**Interfaces:**
- Consumes: same as Task 6.
- Produces: `graph_queries.countries_this_month(db_path: str | None = None) -> list[dict]`, `graph_queries.genres_at_cinema(cinema_slug: str, year: int, db_path: str | None = None) -> list[dict]` — consumed by Task 9's CLI command.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_service/test_graph_queries.py`:

```python
import calendar

from flask_backend.repository.countries import get_or_create_by_iso_code
from flask_backend.repository.genres import get_or_create_by_tmdb_id as get_or_create_genre
from flask_backend.service.graph_queries import countries_this_month, genres_at_cinema


class TestCountriesThisMonth:
    def test_returns_countries_with_a_screening_this_month(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            country = get_or_create_by_iso_code("DE", "Germany")
            movie = Movie(title="Asas do Desejo", slug="asas-do-desejo")
            movie.countries = [country]
            today = date.today()
            last_day = calendar.monthrange(today.year, today.month)[1]
            mid_month = today.replace(day=min(15, last_day))
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=mid_month, time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert countries_this_month(db_path=db_path) == [{"name": "Germany"}]

    def test_excludes_countries_with_only_next_month_screenings(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            country = get_or_create_by_iso_code("FR", "France")
            movie = Movie(title="Filme Futuro", slug="filme-futuro")
            movie.countries = [country]
            today = date.today()
            next_month_year = today.year + (1 if today.month == 12 else 0)
            next_month = 1 if today.month == 12 else today.month + 1
            far_future_date = date(next_month_year + 1, next_month, 1)
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=far_future_date, time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert countries_this_month(db_path=db_path) == []


class TestGenresAtCinema:
    def test_returns_genres_shown_at_a_cinema_in_a_given_year(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            genre = get_or_create_genre(1, "Documentário")
            movie = Movie(title="Sans Soleil", slug="sans-soleil")
            movie.genres = [genre]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2025, 6, 10), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = genres_at_cinema("capitolio", 2025, db_path=db_path)

            assert results == [{"name": "Documentário"}]

    def test_excludes_screenings_from_other_years_or_cinemas(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            genre = get_or_create_genre(1, "Terror")
            movie = Movie(title="Filme de Outro Ano", slug="filme-de-outro-ano")
            movie.genres = [genre]
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[ScreeningDate(date=date(2024, 6, 10), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert genres_at_cinema("capitolio", 2025, db_path=db_path) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_graph_queries.py::TestCountriesThisMonth flask_backend/tests/test_service/test_graph_queries.py::TestGenresAtCinema -v`
Expected: FAIL with `ImportError: cannot import name 'countries_this_month'`.

- [ ] **Step 3: Implement both functions**

Add to `flask_backend/service/graph_queries.py` (add `import calendar` at the top):

```python
import calendar
```

Append:

```python
def countries_this_month(db_path: str = None) -> list[dict]:
    """Production countries with at least one screening date this month."""
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    start = today.replace(day=1).isoformat()
    end = today.replace(day=last_day).isoformat()

    graph = _open(db_path)
    return graph.query(
        "MATCH (c:Country)<-[:PRODUCED_IN]-(m:Movie)-[:HAS_SCREENING]->"
        "(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
        "WHERE sd.date >= $start AND sd.date <= $end "
        "RETURN DISTINCT c.name AS name "
        "ORDER BY c.name",
        {"start": start, "end": end},
    )


def genres_at_cinema(cinema_slug: str, year: int, db_path: str = None) -> list[dict]:
    """Genres shown at a given cinema during a given calendar year."""
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    graph = _open(db_path)
    return graph.query(
        "MATCH (ci:Cinema)<-[:AT_CINEMA]-(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
        "(s)<-[:HAS_SCREENING]-(m:Movie)-[:HAS_GENRE]->(g:Genre) "
        "WHERE ci.slug = $cinema_slug AND sd.date >= $start AND sd.date <= $end "
        "RETURN DISTINCT g.name AS name "
        "ORDER BY g.name",
        {"cinema_slug": cinema_slug, "start": start, "end": end},
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_graph_queries.py -v`
Expected: `8 passed`. As in Task 6, if GraphQLite rejects a specific pattern (e.g. the comma-separated multi-pattern `MATCH` in `genres_at_cinema`), the error names the construct — split it into two `MATCH` clauses joined by a shared variable if needed, and re-run.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/graph_queries.py flask_backend/tests/test_service/test_graph_queries.py
git commit -m "feat: add countries_this_month and genres_at_cinema graph queries"
```

---

### Task 8: Query layer — `screenings_since_release`

`Movie` has no exact release date in Phase 1's schema (only `release_year`, per the design spec), so "since its release" is interpreted as "every screening date on record for the movie," ordered chronologically.

**Files:**
- Modify: `flask_backend/service/graph_queries.py`
- Modify: `flask_backend/tests/test_service/test_graph_queries.py`

**Interfaces:**
- Consumes: same as Task 6.
- Produces: `graph_queries.screenings_since_release(movie_slug: str, db_path: str | None = None) -> list[dict]` — consumed by Task 9's CLI command.

- [ ] **Step 1: Write the failing test**

Append to `flask_backend/tests/test_service/test_graph_queries.py`:

```python
from flask_backend.service.graph_queries import screenings_since_release


class TestScreeningsSinceRelease:
    def test_returns_every_screening_date_for_the_movie_in_order(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(title="Alice nas Cidades", slug="alice-nas-cidades")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(date=date(2026, 8, 10), time="21:00"),
                        ScreeningDate(date=date(2026, 8, 5), time="19:00"),
                    ],
                )
            ]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            results = screenings_since_release("alice-nas-cidades", db_path=db_path)

            assert results == [
                {"date": "2026-08-05", "time": "19:00", "cinema_name": "Cinemateca Capitólio"},
                {"date": "2026-08-10", "time": "21:00", "cinema_name": "Cinemateca Capitólio"},
            ]

    def test_returns_empty_list_for_a_movie_with_no_screenings(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            movie = Movie(title="Sem Sessões", slug="sem-sessoes")
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            assert screenings_since_release("sem-sessoes", db_path=db_path) == []
```

Check the exact `Cinema.name` seeded for `"capitolio"` before trusting the literal `"Cinemateca Capitólio"` in the assertion above — read it from `flask_backend/seeds/cinema_seeds.py` and adjust the string if it differs.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest flask_backend/tests/test_service/test_graph_queries.py::TestScreeningsSinceRelease -v`
Expected: FAIL with `ImportError: cannot import name 'screenings_since_release'`.

- [ ] **Step 3: Implement the function**

Append to `flask_backend/service/graph_queries.py`:

```python
def screenings_since_release(movie_slug: str, db_path: str = None) -> list[dict]:
    """Every recorded screening date for a movie, across all cinemas,
    ordered chronologically. ("Since its release" simplifies to "all
    screening dates on record" - Phase 1's Movie node has no exact release
    date, only release_year.)"""
    graph = _open(db_path)
    return graph.query(
        "MATCH (m:Movie)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
        "(s)-[:AT_CINEMA]->(ci:Cinema) "
        "WHERE m.slug = $movie_slug "
        "RETURN sd.date AS date, sd.time AS time, ci.name AS cinema_name "
        "ORDER BY sd.date, sd.time",
        {"movie_slug": movie_slug},
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_graph_queries.py -v`
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/service/graph_queries.py flask_backend/tests/test_service/test_graph_queries.py
git commit -m "feat: add screenings_since_release graph query"
```

---

### Task 9: `graph-query` CLI command

A single dispatcher command taking a query name plus the options each specific query needs, per the approved design. Prints results as a simple table.

**Files:**
- Modify: `flask_backend/commands.py`
- Modify: `flask_backend/tests/test_service/test_graph_commands.py`

**Interfaces:**
- Consumes: all five `graph_queries` functions (Tasks 6-8).
- Produces: registered Click command `graph-query`.

- [ ] **Step 1: Write the failing tests**

Append to `flask_backend/tests/test_service/test_graph_commands.py`:

```python
from datetime import date

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository.directors import get_or_create_by_tmdb_id as get_or_create_director
from flask_backend.service.graph_sync import sync_graph


class TestGraphQueryCommand:
    def test_movies_by_director_prints_matching_titles(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        db_path = str(tmp_path / "graph.db")
        monkeypatch.setattr("flask_backend.service.graph_sync.GRAPH_DB_PATH", db_path)
        monkeypatch.setattr("flask_backend.service.graph_queries.GRAPH_DB_PATH", db_path)
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie = Movie(title="Paris, Texas", slug="paris-texas")
            movie.directors = [director]
            db_session.add(movie)
            db_session.commit()
            sync_graph()

        result = runner.invoke(
            args=["graph-query", "movies-by-director", "--director", "Wim Wenders"]
        )

        assert result.exit_code == 0
        assert "Paris, Texas" in result.output

    def test_unknown_query_name_shows_usage_error(self, app, runner):
        result = runner.invoke(args=["graph-query", "not-a-real-query"])

        assert result.exit_code != 0
        assert "not-a-real-query" in result.output

    def test_missing_required_option_shows_usage_error(self, app, runner):
        result = runner.invoke(args=["graph-query", "movies-by-director"])

        assert result.exit_code != 0
        assert "--director" in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_service/test_graph_commands.py::TestGraphQueryCommand -v`
Expected: FAIL — `graph-query` is not a registered command.

- [ ] **Step 3: Add the command**

In `flask_backend/commands.py`, register it:

```python
    app.cli.add_command(sync_graph_command)
    app.cli.add_command(graph_query_command)
```

Then add the command, after `sync_graph_command`:

```python
GRAPH_QUERY_NAMES = [
    "movies-by-director",
    "directors-currently-showing",
    "countries-this-month",
    "genres-at-cinema",
    "screenings-since-release",
]


@click.command("graph-query")
@click.argument("query_name")
@click.option("--director", default=None, help="Nome do diretor.")
@click.option("--cinema", default=None, help="Slug da sala.")
@click.option("--year", type=int, default=None, help="Ano.")
@click.option("--movie", default=None, help="Slug do filme.")
def graph_query_command(query_name, director, cinema, year, movie):
    """Executa uma consulta pré-definida no grafo de conhecimento e imprime
    os resultados em formato de tabela simples.

    QUERY_NAME: movies-by-director | directors-currently-showing |
    countries-this-month | genres-at-cinema | screenings-since-release
    """
    from flask_backend.service import graph_queries

    if query_name not in GRAPH_QUERY_NAMES:
        raise click.UsageError(
            f"Consulta desconhecida: '{query_name}'. Opções: "
            f"{', '.join(GRAPH_QUERY_NAMES)}"
        )

    if query_name == "movies-by-director":
        if not director:
            raise click.UsageError("--director é obrigatório para movies-by-director")
        rows = graph_queries.movies_by_director(director)
    elif query_name == "directors-currently-showing":
        rows = graph_queries.directors_currently_showing()
    elif query_name == "countries-this-month":
        rows = graph_queries.countries_this_month()
    elif query_name == "genres-at-cinema":
        if not cinema or year is None:
            raise click.UsageError(
                "--cinema e --year são obrigatórios para genres-at-cinema"
            )
        rows = graph_queries.genres_at_cinema(cinema, year)
    else:
        if not movie:
            raise click.UsageError(
                "--movie é obrigatório para screenings-since-release"
            )
        rows = graph_queries.screenings_since_release(movie)

    if not rows:
        click.echo("Nenhum resultado.")
        return

    headers = list(rows[0].keys())
    click.echo(" | ".join(headers))
    for row in rows:
        click.echo(" | ".join(str(row[h]) for h in headers))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_service/test_graph_commands.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/commands.py flask_backend/tests/test_service/test_graph_commands.py
git commit -m "feat: add graph-query CLI command"
```

---

### Task 10: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Lint and format**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no remaining lint errors; any reformatted files are included in the final review.

- [ ] **Step 2: Run the full test suite**

Run: `pytest flask_backend/tests`
Expected: all tests pass, including every test added in Tasks 1-9.

- [ ] **Step 3: Run the coverage check**

Run: `coverage run -m pytest && coverage report -m`
Expected: overall coverage stays at or above the project's `fail_under = 90` threshold.

- [ ] **Step 4: Manual smoke test against real data**

Run: `flask --app flask_backend sync-graph`
Expected: prints a nonzero node/edge count summary, matching roughly the counts estimated in the design spec (~2,800 nodes, ~5,200 edges against current production data, fewer against a local dev copy).

Then run: `flask --app flask_backend graph-query directors-currently-showing`
Expected: prints a table of director names with no error.

- [ ] **Step 5: Commit any formatting fixes from Step 1**

```bash
git add -A
git status
```

Review the diff before committing — this should only contain ruff-format whitespace/import-order changes from Step 1, nothing else. If it's empty, skip the commit.

```bash
git commit -m "chore: apply ruff formatting"
```
