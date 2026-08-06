# Focus Motif Family Standardization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the three "N+ currently-screening movies in category X" motifs into a consistent `*FocusMotif` family, and rewrite `CinemaGenreFocusMotif` (→ `GenreFocusMotif`) to detect genre focus across all cinemas the same way `CountryFocusMotif`/`DirectorFocusMotif` already detect director/country focus across all cinemas, instead of per single cinema against that cinema's own history.

**Architecture:** All changes are confined to `flask_backend/service/motifs.py` (the motif definitions) and their three test files. No other module references these class names or `motif_name` string values (confirmed via repo-wide grep). `motif_ranking.py` needs no changes — it only reads `Observation.motif_name` generically.

**Tech Stack:** Python 3.14, pytest, GraphQLite (Cypher-style queries via `graph.query(...)`).

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-08-05-motif-focus-family-design.md` — full rationale for every rename and the `GenreFocusMotif` query rewrite.
- `GENRE_FOCUS_THRESHOLD = 2` (confirmed with user — same value as `DIRECTOR_FOCUS_THRESHOLD`/`COUNTRY_FOCUS_THRESHOLD`, not `4`).
- `DirectorReturnMotif` and `AnniversaryMotif` are out of scope — do not touch them.
- Run `uv run ruff check --fix` and `uv run ruff format` before considering any task done (project convention, see `CLAUDE.md`).
- Never add an AI/agent co-author trailer to commits (see `CLAUDE.md`).
- When opening the PR for this work, post the full design spec (`docs/superpowers/specs/2026-08-05-motif-focus-family-design.md`, before it's deleted in Task 3) as a PR comment — this step is easy to skip and has been missed before.

---

### Task 1: Rename `MultipleMoviesSameDirectorMotif` → `DirectorFocusMotif` and `CountryClusterMotif` → `CountryFocusMotif`

Pure rename — no detection logic changes. This covers the class names, the
`name` attribute strings, and the two threshold constants.

**Files:**
- Modify: `flask_backend/service/motifs.py:49-160` (`COUNTRY_CLUSTER_THRESHOLD`, `MULTIPLE_MOVIES_THRESHOLD`, `MultipleMoviesSameDirectorMotif`, `CountryClusterMotif`), and `flask_backend/service/motifs.py:433-439` (`MOTIF_REGISTRY`)
- Modify: `flask_backend/tests/test_service/test_motifs.py:21-29,56-171,438-448`
- Modify: `flask_backend/tests/test_service/test_motif_ranking.py:127,201`
- Modify: `flask_backend/tests/test_service/test_motif_commands.py:62,81`

**Interfaces:**
- Produces: `DirectorFocusMotif` (was `MultipleMoviesSameDirectorMotif`), `.name = "director_focus"` (was `"multiple_movies_same_director"`); `CountryFocusMotif` (was `CountryClusterMotif`), `.name = "country_focus"` (was `"country_cluster"`); constants `DIRECTOR_FOCUS_THRESHOLD` (was `MULTIPLE_MOVIES_THRESHOLD`, value `2`, unchanged) and `COUNTRY_FOCUS_THRESHOLD` (was `COUNTRY_CLUSTER_THRESHOLD`, value `2`, unchanged). All other behavior (query, confidence, metadata shape) is byte-for-byte identical to before.

- [ ] **Step 1: Update the test files to reference the new names (this will fail first)**

In `flask_backend/tests/test_service/test_motifs.py`, update the import block (lines 21-29):

```python
from flask_backend.service.motifs import (
    MOTIF_REGISTRY,
    AnniversaryMotif,
    CinemaGenreFocusMotif,
    CountryFocusMotif,
    DirectorFocusMotif,
    DirectorReturnMotif,
    _dedupe_preserve_order,
)
```

Rename `class TestMultipleMoviesSameDirectorMotif:` (line 56) to `class TestDirectorFocusMotif:`, and inside it replace every `MultipleMoviesSameDirectorMotif()` call (lines 75, 105, 125) with `DirectorFocusMotif()`. Update the assertion at line 79 from `assert obs.motif_name == "multiple_movies_same_director"` to `assert obs.motif_name == "director_focus"`.

Rename `class TestCountryClusterMotif:` (line 128) to `class TestCountryFocusMotif:`, and inside it replace every `CountryClusterMotif()` call (lines 147, 171) with `CountryFocusMotif()`. Update the assertion at line 150 from `assert observations[0].motif_name == "country_cluster"` to `assert observations[0].motif_name == "country_focus"`.

At the bottom, update `TestMotifRegistry.test_contains_one_instance_of_each_motif` (lines 439-448) — only rename the two strings, leave `cinema_genre_focus` as-is for now (Task 2 handles it):

```python
class TestMotifRegistry:
    def test_contains_one_instance_of_each_motif(self):
        names = {motif.name for motif in MOTIF_REGISTRY}
        assert names == {
            "director_focus",
            "country_focus",
            "director_return",
            "cinema_genre_focus",
            "anniversary",
        }
        assert len(MOTIF_REGISTRY) == 5
```

In `flask_backend/tests/test_service/test_motif_ranking.py`, change line 127 from `assert observations[0].motif_name == "multiple_movies_same_director"` to `assert observations[0].motif_name == "director_focus"`, and line 201 from `assert "country_cluster" in motif_names` to `assert "country_focus" in motif_names`.

In `flask_backend/tests/test_service/test_motif_commands.py`, change line 62 from `assert "multiple_movies_same_director" in result.output` to `assert "director_focus" in result.output`, and line 81 from `assert payload[0]["motif_name"] == "multiple_movies_same_director"` to `assert payload[0]["motif_name"] == "director_focus"`.

- [ ] **Step 2: Run the tests to confirm they fail on the old class names**

Run: `pytest flask_backend/tests/test_service/test_motifs.py flask_backend/tests/test_service/test_motif_ranking.py flask_backend/tests/test_service/test_motif_commands.py -v`
Expected: FAIL — `ImportError: cannot import name 'CountryFocusMotif'` (or `DirectorFocusMotif`) from `flask_backend.service.motifs`.

- [ ] **Step 3: Rename the constants and classes in `motifs.py`**

At line 49-50, change:

```python
COUNTRY_CLUSTER_THRESHOLD = 2
MULTIPLE_MOVIES_THRESHOLD = 2
```

to:

```python
COUNTRY_FOCUS_THRESHOLD = 2
DIRECTOR_FOCUS_THRESHOLD = 2
```

Rename `class MultipleMoviesSameDirectorMotif(Motif):` (line 53) to:

```python
class DirectorFocusMotif(Motif):
    name = "director_focus"
    description = "Detects directors with 2+ movies currently screening."
    version = "1.0"
```

and in `detect()` update the constant reference at line 72 from `MULTIPLE_MOVIES_THRESHOLD` to `DIRECTOR_FOCUS_THRESHOLD`. No other lines in this class change.

Rename `class CountryClusterMotif(Motif):` (line 107) to:

```python
class CountryFocusMotif(Motif):
    name = "country_focus"
    description = (
        f"Detects production countries with {COUNTRY_FOCUS_THRESHOLD}+ "
        "movies currently screening."
    )
    version = "1.0"
```

and in `detect()` update the constant reference at line 129 from `COUNTRY_CLUSTER_THRESHOLD` to `COUNTRY_FOCUS_THRESHOLD`. No other lines in this class change.

Update `MOTIF_REGISTRY` (lines 433-439):

```python
MOTIF_REGISTRY: list[Motif] = [
    DirectorFocusMotif(),
    CountryFocusMotif(),
    DirectorReturnMotif(),
    CinemaGenreFocusMotif(),
    AnniversaryMotif(),
]
```

(`CinemaGenreFocusMotif` stays in the registry list under its current name for now — Task 2 renames it.)

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest flask_backend/tests/test_service/test_motifs.py flask_backend/tests/test_service/test_motif_ranking.py flask_backend/tests/test_service/test_motif_commands.py -v`
Expected: PASS, all tests green.

- [ ] **Step 5: Lint, format, commit**

```bash
uv run ruff check --fix flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py flask_backend/tests/test_service/test_motif_ranking.py flask_backend/tests/test_service/test_motif_commands.py
uv run ruff format flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py flask_backend/tests/test_service/test_motif_ranking.py flask_backend/tests/test_service/test_motif_commands.py
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py flask_backend/tests/test_service/test_motif_ranking.py flask_backend/tests/test_service/test_motif_commands.py
git commit -m "refactor: rename MultipleMoviesSameDirector/CountryCluster motifs to the Focus family"
```

---

### Task 2: Rewrite `CinemaGenreFocusMotif` → `GenreFocusMotif` (citywide count threshold, no historical baseline)

**Files:**
- Modify: `flask_backend/service/motifs.py:247-368` (`CINEMA_GENRE_FOCUS_MULTIPLIER`, `CINEMA_GENRE_FOCUS_MIN_COUNT`, `CinemaGenreFocusMotif`), `flask_backend/service/motifs.py:9` (`calendar` import), `flask_backend/service/motifs.py:433-439` (`MOTIF_REGISTRY`)
- Modify: `flask_backend/tests/test_service/test_motifs.py:5,17-19,241-374,441-448` (`calendar` import, `get_or_create_genre` import, `_this_month_date` helper, `TestCinemaGenreFocusMotif` → `TestGenreFocusMotif`, registry name set)

**Interfaces:**
- Produces: `GenreFocusMotif` (was `CinemaGenreFocusMotif`), `.name = "genre_focus"` (was `"cinema_genre_focus"`), `.version = "2.0"` (was `"1.0"` — behavior changed, not just renamed). Constant `GENRE_FOCUS_THRESHOLD = 2` replaces `CINEMA_GENRE_FOCUS_MULTIPLIER`/`CINEMA_GENRE_FOCUS_MIN_COUNT`. `Observation.metadata` shape becomes `{"genre": str, "movies": list[str], "next_screening_date": str}` (drops `"cinema"`, `"screening_count"`). `Observation.confidence` becomes `1.0` (was `0.7`).

- [ ] **Step 1: Replace `TestCinemaGenreFocusMotif` with `TestGenreFocusMotif` in the test file (this will fail first)**

In `flask_backend/tests/test_service/test_motifs.py`, remove the now-unused `calendar` import (line 5) and the `_this_month_date` helper (lines 241-245) — nothing else in the file uses either after this task. Leave the existing `get_or_create_genre` import (lines 17-19) untouched — it's still used by the rewritten tests below.

Replace the entire `TestCinemaGenreFocusMotif` class (lines 248-374) with:

```python
class TestGenreFocusMotif:
    def test_flags_genre_with_two_currently_showing_movies(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            movie_a = Movie(title="Doc A", slug="doc-a")
            movie_a.genres = [doc_genre]
            movie_a.screenings = [_screening("capitolio", 1)]
            movie_b = Movie(title="Doc B", slug="doc-b")
            movie_b.genres = [doc_genre]
            movie_b.screenings = [_screening("sala-redencao", 2)]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = GenreFocusMotif().detect(graph)

            assert len(observations) == 1
            obs = observations[0]
            assert obs.motif_name == "genre_focus"
            assert obs.confidence == 1.0
            assert obs.metadata["genre"] == "Documentário"
            assert sorted(obs.metadata["movies"]) == sorted(["Doc A", "Doc B"])
            assert (
                obs.metadata["next_screening_date"]
                == (date.today() + timedelta(days=1)).isoformat()
            )

    def test_does_not_flag_genre_with_only_one_currently_showing_movie(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            doc_genre = get_or_create_genre(1, "Documentário")
            movie = Movie(title="Doc Único", slug="doc-unico")
            movie.genres = [doc_genre]
            movie.screenings = [_screening("capitolio", 1)]
            db_session.add(movie)
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            assert GenreFocusMotif().detect(graph) == []

    def test_counts_movies_across_all_cinemas(self, app, setup_cinemas, tmp_path):
        """The whole point of this motif post-rewrite: a genre with 2
        movies split across two different cinemas must still be flagged,
        not just when both screen at the same cinema."""
        with app.app_context():
            drama_genre = get_or_create_genre(2, "Drama")
            movie_a = Movie(title="Drama A", slug="drama-a")
            movie_a.genres = [drama_genre]
            movie_a.screenings = [_screening("capitolio", 1)]
            movie_b = Movie(title="Drama B", slug="drama-b")
            movie_b.genres = [drama_genre]
            movie_b.screenings = [_screening("cinebancarios", 2)]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)
            graph = Graph(db_path)

            observations = GenreFocusMotif().detect(graph)

            assert len(observations) == 1
            assert sorted(observations[0].metadata["movies"]) == sorted(
                ["Drama A", "Drama B"]
            )
```

`_screening` is the existing module-level helper (line 43) already used by every other test class in this file — it takes a cinema slug and a day offset. `"sala-redencao"` and `"cinebancarios"` are both seeded by the `setup_cinemas` fixture (see `flask_backend/seeds/cinema_seeds.py`), same as `"capitolio"` used throughout the rest of this file.

Update `TestMotifRegistry.test_contains_one_instance_of_each_motif` (rewritten already in Task 1) to replace `"cinema_genre_focus"` with `"genre_focus"`:

```python
class TestMotifRegistry:
    def test_contains_one_instance_of_each_motif(self):
        names = {motif.name for motif in MOTIF_REGISTRY}
        assert names == {
            "director_focus",
            "country_focus",
            "director_return",
            "genre_focus",
            "anniversary",
        }
        assert len(MOTIF_REGISTRY) == 5
```

Update the import block to swap `CinemaGenreFocusMotif` for `GenreFocusMotif`:

```python
from flask_backend.service.motifs import (
    MOTIF_REGISTRY,
    AnniversaryMotif,
    CountryFocusMotif,
    DirectorFocusMotif,
    DirectorReturnMotif,
    GenreFocusMotif,
    _dedupe_preserve_order,
)
```

- [ ] **Step 2: Run the tests to confirm they fail (class doesn't exist yet)**

Run: `pytest flask_backend/tests/test_service/test_motifs.py -v`
Expected: FAIL — `ImportError: cannot import name 'GenreFocusMotif' from 'flask_backend.service.motifs'`.

- [ ] **Step 3: Rewrite `CinemaGenreFocusMotif` as `GenreFocusMotif` in `motifs.py`**

Remove the `calendar` import at line 9 (no longer used by any motif after this rewrite).

Replace lines 247-368 (`CINEMA_GENRE_FOCUS_MULTIPLIER` through the end of the `CinemaGenreFocusMotif` class) with:

```python
GENRE_FOCUS_THRESHOLD = 2


class GenreFocusMotif(Motif):
    name = "genre_focus"
    description = (
        "Detects genres with "
        f"{GENRE_FOCUS_THRESHOLD}+ movies currently screening, across all "
        "cinemas."
    )
    version = "2.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        query = (
            "MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre), "
            "(m)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "WITH g, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, "
            "collect(m.title) AS titles, collect(sd.date) AS dates "
            "WHERE movie_count >= $threshold "
            "RETURN g.id AS genre_id, g.name AS genre_name, movie_count, "
            "movie_ids, titles, dates "
            "ORDER BY genre_name"
        )
        rows = graph.query(
            query, {"today": today, "threshold": GENRE_FOCUS_THRESHOLD}
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
                    headline=f"{row['genre_name']} em destaque nos cinemas",
                    summary=(
                        f"{len(movie_ids)} filmes de {row['genre_name']} "
                        "estão em cartaz atualmente."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["genre_id"], *movie_ids],
                        edges=[
                            (mid, row["genre_id"], "HAS_GENRE") for mid in movie_ids
                        ],
                        query=query,
                    ),
                    metadata={
                        "genre": row["genre_name"],
                        "movies": titles,
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations
```

Update `MOTIF_REGISTRY` (the list currently ending in Task 1's version) to use `GenreFocusMotif()` instead of `CinemaGenreFocusMotif()`:

```python
MOTIF_REGISTRY: list[Motif] = [
    DirectorFocusMotif(),
    CountryFocusMotif(),
    DirectorReturnMotif(),
    GenreFocusMotif(),
    AnniversaryMotif(),
]
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest flask_backend/tests/test_service/test_motifs.py -v`
Expected: PASS, all tests green, including the three new `TestGenreFocusMotif` cases.

- [ ] **Step 5: Lint, format, commit**

```bash
uv run ruff check --fix flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
uv run ruff format flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git add flask_backend/service/motifs.py flask_backend/tests/test_service/test_motifs.py
git commit -m "feat: detect genre focus across all cinemas instead of per-cinema"
```

---

### Task 3: Full-suite verification and spec/plan cleanup

**Files:**
- Read-only verification: entire `flask_backend/tests/` suite.
- Delete (per project convention — SDD docs are removed before the final PR, then posted as a PR comment): `docs/superpowers/specs/2026-08-05-motif-focus-family-design.md`, `docs/superpowers/plans/2026-08-05-motif-focus-family.md`

**Interfaces:**
- Consumes: everything produced by Task 1 and Task 2.
- Produces: nothing new — this is a verification and cleanup task.

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest flask_backend/tests`
Expected: PASS, all tests green (no regressions in other suites that might incidentally import `flask_backend.service.motifs`).

- [ ] **Step 2: Run the linters across the whole project**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no errors; if formatting changes files beyond what Tasks 1-2 touched, review the diff before committing.

- [ ] **Step 3: Manually verify the CLI output reads sensibly**

Run: `flask --app flask_backend detect-motifs --json` against a synced dev graph (or `flask --app flask_backend sync-graph` first if needed) and confirm `genre_focus`/`director_focus`/`country_focus` observations show the expected `motif_name`, `headline`, and `metadata` shape described in Task 2's interface.

- [ ] **Step 4: Remove the SDD design spec and plan docs, commit**

Per this repo's convention (write specs/plans for review, remove before the final PR, and post the spec as a PR comment when opening the PR):

```bash
git rm docs/superpowers/specs/2026-08-05-motif-focus-family-design.md docs/superpowers/plans/2026-08-05-motif-focus-family.md
git commit -m "chore: remove sdd specific documentation"
```
