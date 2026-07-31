# Unified Movie/Screening Edit Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the "edit a screening" and "edit a movie's TMDB metadata" screens into one page reachable from a single tap on the mobile index card and from `/admin/alerts`, and replace the current silent title-based movie reattach/create with an explicit, confirmed "Trocar filme" action.

**Architecture:** `screening/update.html` gains two new sections (Filme, Metadados TMDB) alongside its existing form. The TMDB search/link/unlink display and JS already built for `movie/admin/edit.html` are extracted into a shared Jinja include and a shared static JS file so both pages use the same code. One new endpoint, `POST /screening/<id>/movie`, handles the confirmed reattach-or-create; the existing `/movies/search` endpoint is extended (extra JSON fields + an exclude filter) to back the "Trocar filme" search box. The screening form's own POST handler drops `movie_title` entirely and now redirects back to itself instead of the mobile index, so admins editing from `/admin/alerts` keep their place via the browser back button.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, vanilla JS (`fetch`), pytest, `uv`.

## Global Constraints

- Spec of record: `docs/superpowers/specs/2026-07-30-unified-edit-screen-design.md`.
- No DB schema changes — this plan touches only routes, repository functions, templates, and static JS.
- `/admin/movies/<id>` (the movie-only metadata page) and its routes/tests are unchanged and must keep passing as-is.
- All new/modified routes that mutate data require `@login_required` (`flask_backend/routes/auth.py:97`), matching every other admin route in this codebase.
- Run `uv run ruff check --fix`, `uv run ruff format`, `uv run djlint --reformat flask_backend/templates --format-css --format-js` before considering any task done — this repo's CI fails on unformatted code.

---

### Task 1: Repository — `reattach_movie` + extend `get_movies_with_similar_titles`

**Files:**
- Modify: `flask_backend/repository/screenings.py` (add function after `update`, currently ending at line 269)
- Modify: `flask_backend/repository/movies.py:114-117` (`get_movies_with_similar_titles`)
- Test: `flask_backend/tests/test_repository/test_screenings.py` (new class)
- Test: `flask_backend/tests/test_repository/test_movies.py` (new class)

**Interfaces:**
- Produces: `reattach_movie(screening: Screening, movie_id: int) -> None` — sets only `screening.movie_id`, commits. Task 3's new route calls this.
- Produces: `get_movies_with_similar_titles(title: str, exclude_movie_id: Optional[int] = None) -> List[Movie]` — unchanged behavior plus an optional exclusion filter. Task 2's route calls this.

- [ ] **Step 1: Write the failing tests**

In `flask_backend/tests/test_repository/test_screenings.py`, add the import and a new class. Change the import block (line 6) to:

```python
from flask_backend.repository.screenings import (
    reattach_movie,
    # ... keep every existing imported name here unchanged
)
```

Add this class after the imports, before `class TestGetScreeningsWithUpcomingDates:`:

```python
class TestReattachMovie:
    def test_changes_screening_movie_id(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            original_movie = Movie(title="Filme Original", slug="filme-original")
            target_movie = Movie(title="Filme Destino", slug="filme-destino")
            db_session.add_all([original_movie, target_movie])
            db_session.commit()

            screening = Screening(
                movie_id=original_movie.id,
                cinema_id=cinema.id,
                description="desc",
                draft=False,
                dates=[ScreeningDate(date=date.today(), time="20:00")],
            )
            db_session.add(screening)
            db_session.commit()
            screening_id = screening.id
            target_movie_id = target_movie.id

            reattach_movie(screening, target_movie_id)

            updated = db_session.get(Screening, screening_id)
            assert updated.movie_id == target_movie_id

    def test_does_not_touch_other_screening_fields(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_cinema_by_slug("capitolio")
            original_movie = Movie(title="Filme Original 2", slug="filme-original-2")
            target_movie = Movie(title="Filme Destino 2", slug="filme-destino-2")
            db_session.add_all([original_movie, target_movie])
            db_session.commit()

            screening = Screening(
                movie_id=original_movie.id,
                cinema_id=cinema.id,
                description="descrição original",
                draft=True,
                dates=[ScreeningDate(date=date.today(), time="20:00")],
            )
            db_session.add(screening)
            db_session.commit()
            screening_id = screening.id

            reattach_movie(screening, target_movie.id)

            updated = db_session.get(Screening, screening_id)
            assert updated.description == "descrição original"
            assert updated.draft is True
```

In `flask_backend/tests/test_repository/test_movies.py`, change the import (line 4) to:

```python
from flask_backend.repository.movies import (
    create,
    get_by_title_or_create,
    get_movies_with_similar_titles,
)
```

Add this class at the end of the file:

```python
class TestGetMoviesWithSimilarTitles:
    def test_matches_partial_title_case_insensitively(self, app):
        with app.app_context():
            movie = Movie(title="Duna Parte Dois", slug="duna-parte-dois")
            db_session.add(movie)
            db_session.commit()

            results = get_movies_with_similar_titles("duna")

            assert [m.title for m in results] == ["Duna Parte Dois"]

    def test_excludes_given_movie_id(self, app):
        with app.app_context():
            keep = Movie(title="Duna Parte Um", slug="duna-parte-um")
            exclude = Movie(title="Duna Parte Dois", slug="duna-parte-dois-2")
            db_session.add_all([keep, exclude])
            db_session.commit()

            results = get_movies_with_similar_titles(
                "duna", exclude_movie_id=exclude.id
            )

            assert [m.id for m in results] == [keep.id]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py flask_backend/tests/test_repository/test_movies.py -v`
Expected: FAIL — `ImportError: cannot import name 'reattach_movie'` and `TypeError: get_movies_with_similar_titles() got an unexpected keyword argument 'exclude_movie_id'`.

- [ ] **Step 3: Implement**

In `flask_backend/repository/screenings.py`, add this function right after `update` (after line 269, before `def delete(` at line 272):

```python
def reattach_movie(screening: Screening, movie_id: int) -> None:
    screening.movie_id = movie_id
    db_session.add(screening)
    db_session.commit()
```

In `flask_backend/repository/movies.py`, replace `get_movies_with_similar_titles` (lines 114-117):

```python
def get_movies_with_similar_titles(
    title: str, exclude_movie_id: Optional[int] = None
) -> List[Movie]:
    query = db_session.query(Movie).filter(Movie.title.ilike(f"%{title}%"))
    if exclude_movie_id is not None:
        query = query.filter(Movie.id != exclude_movie_id)
    return query.limit(3).all()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_repository/test_screenings.py flask_backend/tests/test_repository/test_movies.py -v`
Expected: PASS (all tests, including pre-existing ones in both files).

- [ ] **Step 5: Commit**

```bash
git add flask_backend/repository/screenings.py flask_backend/repository/movies.py flask_backend/tests/test_repository/test_screenings.py flask_backend/tests/test_repository/test_movies.py
git commit -m "feat: add reattach_movie and exclude_movie_id filter for similar-title search"
```

---

### Task 2: Route — extend `/movies/search` response and add `exclude_movie_id`

**Files:**
- Modify: `flask_backend/routes/movie.py:127-132` (`search_movies`)
- Test: `flask_backend/tests/test_routes/test_movies.py` (`TestMoviesSearch`, ends at line 401)

**Interfaces:**
- Consumes: `get_movies_with_similar_titles(title, exclude_movie_id=None)` from Task 1.
- Produces: `GET /movies/search?title=<q>&exclude_movie_id=<id>` now returns `[{"id": int, "title": str, "release_year": Optional[int]}]` instead of `[{"title": str}]`. `exclude_movie_id` is optional. Task 6's "Trocar filme" JS calls this with `exclude_movie_id` set; `create.html`'s existing autocomplete calls it without that param and only reads `.title`, so it is unaffected by the shape change.

- [ ] **Step 1: Write the failing tests**

In `flask_backend/tests/test_routes/test_movies.py`, add to `class TestMoviesSearch` (after `test_returns_matching_titles`, before `class TestMovieShow:` at line 404):

```python
    def test_returns_id_and_release_year(
        self, auth_headers, app, sample_movies_with_screenings
    ):
        with app.app_context():
            movie = db_session.query(Movie).first()
            movie.release_year = 2021
            db_session.commit()
            target_title = movie.title
            movie_id = movie.id

        response = auth_headers.get(f"/movies/search?title={target_title}")
        assert response.status_code == 200
        results = response.get_json()
        match = next(item for item in results if item["id"] == movie_id)
        assert match["release_year"] == 2021

    def test_excludes_movie_id_when_given(
        self, auth_headers, app, sample_movies_with_screenings
    ):
        with app.app_context():
            movie = db_session.query(Movie).first()
            target_title = movie.title
            movie_id = movie.id

        response = auth_headers.get(
            f"/movies/search?title={target_title}&exclude_movie_id={movie_id}"
        )
        assert response.status_code == 200
        ids = [item["id"] for item in response.get_json()]
        assert movie_id not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_movies.py -v -k TestMoviesSearch`
Expected: FAIL — `test_returns_id_and_release_year` fails with `KeyError: 'id'`; `test_excludes_movie_id_when_given` fails because the current route ignores `exclude_movie_id` and still returns the movie.

- [ ] **Step 3: Implement**

In `flask_backend/routes/movie.py`, replace `search_movies` (lines 127-132):

```python
@bp.route("/movies/search", methods=["GET"])
@login_required
def search_movies():
    title = request.args.get("title")
    exclude_movie_id = request.args.get("exclude_movie_id", type=int)
    movies = get_movies_with_similar_titles(title, exclude_movie_id=exclude_movie_id)
    return jsonify(
        [
            {"id": movie.id, "title": movie.title, "release_year": movie.release_year}
            for movie in movies
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_movies.py -v -k TestMoviesSearch`
Expected: PASS (all four tests in the class).

- [ ] **Step 5: Commit**

```bash
git add flask_backend/routes/movie.py flask_backend/tests/test_routes/test_movies.py
git commit -m "feat: return id/release_year from /movies/search and support exclude_movie_id"
```

---

### Task 3: Route — `POST /screening/<id>/movie` (the confirmed reattach-or-create endpoint)

**Files:**
- Modify: `flask_backend/routes/screening.py` (add route after `update`, i.e. after line 442 as it exists today; imports block at lines 30-41)
- Test: `flask_backend/tests/test_routes/test_screening.py` (new class, after `class TestScreeningUpdate:`)

**Interfaces:**
- Consumes: `reattach_movie(screening, movie_id)` (Task 1), `get_movie_by_id` and `get_movie_by_title_or_create` (already imported in `screening.py` at lines 27-28).
- Produces: `POST /screening/<int:id>/movie` with JSON body `{"movie_id": int}` **or** `{"new_title": str}` (exactly one). Returns `200 {"movie": {"id": int, "title": str, "slug": str}}` on success; `400` if the body has neither or both keys; `404` if the screening or the given `movie_id` doesn't exist. No-op (no DB write) if the resolved movie is already the screening's current movie. Endpoint name: `screening.change_movie`. Task 6's "Trocar filme" JS calls this by URL (`url_for('screening.change_movie', id=...)`).

- [ ] **Step 1: Write the failing tests**

In `flask_backend/tests/test_routes/test_screening.py`, add this class after `class TestScreeningUpdate:` (after line 473, before `class TestScreeningDelete:`):

```python
class TestScreeningChangeMovie:
    def test_requires_login(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening()
        response = client.post(f"/screening/{screening_id}/movie", json={"movie_id": 1})
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_missing_screening(self, auth_headers):
        response = auth_headers.post(
            "/screening/999999/movie", json={"movie_id": 1}
        )
        assert response.status_code == 404

    def test_returns_400_when_neither_field_given(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.post(f"/screening/{screening_id}/movie", json={})
        assert response.status_code == 400

    def test_returns_400_when_both_fields_given(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"movie_id": 1, "new_title": "X"},
        )
        assert response.status_code == 400

    def test_returns_404_when_movie_id_does_not_exist(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.post(
            f"/screening/{screening_id}/movie", json={"movie_id": 999999}
        )
        assert response.status_code == 404

    def test_reattaches_to_existing_movie_by_id(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo")
            target = Movie(title="Filme Novo", slug="filme-novo-alvo")
            db_session.add(target)
            db_session.commit()
            target_id = target.id

        response = auth_headers.post(
            f"/screening/{screening_id}/movie", json={"movie_id": target_id}
        )
        assert response.status_code == 200
        assert response.get_json()["movie"]["id"] == target_id
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie_id == target_id

    def test_creates_new_movie_when_new_title_has_no_match(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo 2")

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"new_title": "Filme Totalmente Novo"},
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie.title == "Filme Totalmente Novo"

    def test_reattaches_to_existing_movie_when_new_title_matches_by_slug(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo 3")
            existing = Movie(title="Filme Existente", slug="filme-existente")
            db_session.add(existing)
            db_session.commit()
            existing_id = existing.id

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"new_title": "Filme Existente"},
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie_id == existing_id
            assert (
                db_session.query(Movie).filter_by(slug="filme-existente").count() == 1
            )

    def test_is_a_noop_when_target_equals_current_movie(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Mesmo")
            screening = db_session.get(Screening, screening_id)
            current_movie_id = screening.movie_id

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"movie_id": current_movie_id},
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie_id == current_movie_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k TestScreeningChangeMovie`
Expected: FAIL — every test gets a 404 for an unknown route, so the `test_requires_login`/`test_returns_400_*` assertions on status codes fail.

- [ ] **Step 3: Implement**

In `flask_backend/routes/screening.py`, add the following import to the existing `from flask_backend.repository.screenings import (...)` block (lines 30-41), alongside `update as update_screening`:

```python
from flask_backend.repository.screenings import (
    create as create_screening,
    delete as delete_screening,
    get_days_screenings_by_cinema_id,
    get_month_screening_dates,
    get_screening_by_id,
    get_screening_dates_for_movies,
    get_screenings_in_date_range,
    get_weekend_screening_dates,
    reattach_movie,
    update as update_screening,
    update_screening_dates,
)
```

Add this route after `update` (after line 442, before `def delete(` — check current line numbers, it follows the `update` view):

```python
@bp.route("/screening/<int:id>/movie", methods=["POST"])
@login_required
def change_movie(id):
    screening = get_screening_by_id(id)
    if not screening:
        abort(404)

    payload = request.get_json(silent=True) or {}
    movie_id = payload.get("movie_id")
    new_title = payload.get("new_title")

    if bool(movie_id) == bool(new_title):
        return jsonify(
            {"error": "Envie exatamente um de movie_id ou new_title."}
        ), 400

    if movie_id:
        movie = get_movie_by_id(movie_id)
        if not movie:
            abort(404)
    else:
        movie, _ = get_movie_by_title_or_create(new_title)

    if movie.id != screening.movie_id:
        reattach_movie(screening, movie.id)

    return jsonify(
        {"movie": {"id": movie.id, "title": movie.title, "slug": movie.slug}}
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k TestScreeningChangeMovie`
Expected: PASS (all 9 tests).

- [ ] **Step 5: Run the full screening test file to check for regressions**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS (no regressions in existing classes).

- [ ] **Step 6: Commit**

```bash
git add flask_backend/routes/screening.py flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: add POST /screening/<id>/movie confirmed reattach-or-create endpoint"
```

---

### Task 4: Route — drop `movie_title` from `screening.update`, redirect to self on success

**Files:**
- Modify: `flask_backend/routes/screening.py:373-442` (`update`)
- Test: `flask_backend/tests/test_routes/test_screening.py` (`class TestScreeningUpdate:`, lines 352-473)

**Interfaces:**
- Produces: `POST /screening/<id>/update` no longer reads or requires `movie_title`; on success it redirects to `url_for("screening.update", id=id)` instead of `screening.index`. No new names — this only removes behavior from an existing endpoint.

- [ ] **Step 1: Update the test file to match the new contract**

In `flask_backend/tests/test_routes/test_screening.py`, inside `class TestScreeningUpdate:`:

Delete `test_update_post_missing_title_shows_error` (lines 370-376) entirely — the route will no longer validate a `movie_title` field.

Replace `test_update_post_success_updates_screening` (lines 413-423):

```python
    def test_update_post_success_updates_description(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form(description="Nova descrição de teste.")
        response = auth_headers.post(
            f"/screening/{screening_id}/update", data=form, follow_redirects=True
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.description == "Nova descrição de teste."

    def test_update_post_ignores_movie_title_field(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Titulo Original")
        form = _valid_create_form(movie_title="Titulo Que Deveria Ser Ignorado")
        auth_headers.post(f"/screening/{screening_id}/update", data=form)
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie.title == "Titulo Original"

    def test_update_post_success_redirects_to_update_page(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form()
        response = auth_headers.post(
            f"/screening/{screening_id}/update", data=form, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == f"/screening/{screening_id}/update"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k TestScreeningUpdate`
Expected: FAIL — `test_update_post_success_redirects_to_update_page` fails because the route still redirects to `/` (`screening.index`); `test_update_post_ignores_movie_title_field` fails because the route still applies `movie_title`.

- [ ] **Step 3: Implement**

In `flask_backend/routes/screening.py`, replace the `update` view (lines 373-442):

```python
@bp.route("/screening/<int:id>/update", methods=("GET", "POST"))
@login_required
def update(id):
    screening = get_screening_by_id(id)
    image = None
    if not screening:
        abort(404)

    if request.method == "POST":
        description = request.form.get("description")
        screening_dates = request.form.getlist("screening_dates")
        status = request.form.get("status")
        image_alt = request.form.get("image_alt")
        error = None

        if not description:
            error = "O campo descrição é obrigatório."
        if not screening_dates:
            error = "Selecione ao menos uma data de exibição."
        if not status:
            error = "Selecione o status do cadastro."

        try:
            parsed_screening_dates = build_dates(screening_dates)
        except ValueError:
            error = "Data de exibição inválida."

        movie_poster = request.files.get("movie_poster", None)
        image = screening.image
        image_width = screening.image_width
        image_height = screening.image_height

        if movie_poster and movie_poster.filename:
            img_is_valid, message = validate_image(movie_poster)
            if img_is_valid:
                new_img, image_width, image_height = save_image(
                    movie_poster, current_app
                )
                image = new_img
            else:
                error = message

        if error is not None:
            flash(error, "danger")
        else:
            update_screening_dates(screening, parsed_screening_dates)

            update_screening(
                screening,
                screening.movie_id,
                description,
                image,
                image_width,
                image_height,
                status == "draft",
                image_alt,
            )
            flash(
                f"Sessão «{screening.movie.title}» atualizada com sucesso!", "success"
            )
            return redirect(url_for("screening.update", id=id))

    return render_template(
        "screening/update.html",
        current_movie_poster=image or screening.image,
        screening=screening,
        max_file_size=current_app.config["MAX_CONTENT_LENGTH"],
    )
```

Note: `get_movie_by_title_or_create` stays imported (line 28 of `screening.py`) — the `create` view (line ~313) still uses it. Do not remove that import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k TestScreeningUpdate`
Expected: PASS (all remaining/new tests in the class).

- [ ] **Step 5: Run the full screening test file to check for regressions**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add flask_backend/routes/screening.py flask_backend/tests/test_routes/test_screening.py
git commit -m "refactor: remove movie_title from screening update, stay on page after save"
```

---

### Task 5: Extract shared TMDB metadata partial + JS from `movie/admin/edit.html`

**Files:**
- Create: `flask_backend/templates/movie/admin/_metadata_panel.html`
- Create: `flask_backend/static/js/movie-tmdb-metadata.js`
- Modify: `flask_backend/templates/movie/admin/edit.html` (full rewrite, currently 230 lines)

**Interfaces:**
- Produces: include template `movie/admin/_metadata_panel.html`, expects a `movie` variable in scope (a `Movie` ORM object). Produces: `static/js/movie-tmdb-metadata.js`, expects a global `const movieId` to already be defined by the including page before this script tag loads. Both are consumed as-is by Task 6's `screening/update.html`.
- This is a pure refactor — no behavior change. The existing `flask_backend/tests/test_routes/test_admin/test_admin_movies.py::TestAdminMoviesEdit::test_returns_200_with_auth` (asserts `b"Filme de Teste" in response.data`) is the safety net: it must keep passing unchanged before and after this task.

- [ ] **Step 1: Confirm the safety-net test currently passes**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_movies.py -v`
Expected: PASS (all tests, unchanged from before this task).

- [ ] **Step 2: Create the shared partial**

Create `flask_backend/templates/movie/admin/_metadata_panel.html` with exactly this content (copied from the `<div id="movie-metadata">` through the `<div id="tmdb-results">` block of the current `movie/admin/edit.html`, lines 18-66):

```jinja
<div id="movie-metadata" class="mb-4">
    <p>
        <strong>Título:</strong> {{ movie.title }}
    </p>
    <p>
        <strong>Título original:</strong> <span id="field-original_title">{{ movie.original_title or "—" }}</span>
    </p>
    <p>
        <strong>Ano:</strong> <span id="field-release_year">{{ movie.release_year or "—" }}</span>
    </p>
    <p>
        <strong>Idioma original:</strong> <span id="field-original_language">{{ movie.original_language or "—" }}</span>
    </p>
    <p>
        <strong>Diretor(es):</strong>
        <span id="field-directors">{{ movie.directors|map(attribute='name') |join(', ') or "—" }}</span>
    </p>
    <p>
        <strong>Gêneros:</strong>
        <span id="field-genres">{{ movie.genres|map(attribute='name') |join(', ') or "—" }}</span>
    </p>
    <p>
        <strong>Coleção:</strong>
        <span id="field-collection">{{ movie.collection.name if movie.collection else "—" }}</span>
    </p>
    <p>
        <strong>TMDB:</strong>
        <span id="field-tmdb-status">
            {% if movie.tmdb_id %}
                Vinculado ao TMDB #{{ movie.tmdb_id }}
            {% else %}
                Não vinculado
            {% endif %}
        </span>
        {% if movie.tmdb_id %}
            <button type="button" id="unlink-btn" class="btn btn-sm btn-outline-danger">Remover vínculo</button>
        {% endif %}
    </p>
</div>
<div class="mb-3">
    <label for="tmdb-query" class="form-label">Buscar no TMDB</label>
    <input autocomplete="off"
           class="form-control"
           id="tmdb-query"
           value="{{ movie.title }}"
           oninput="fetchTmdbCandidates()">
</div>
<div id="tmdb-error" class="alert alert-danger d-none" role="alert"></div>
<div id="tmdb-results" class="row row-cols-2 row-cols-md-4 g-3"></div>
```

- [ ] **Step 3: Create the shared JS file**

Create `flask_backend/static/js/movie-tmdb-metadata.js` with exactly this content (copied from the current `movie/admin/edit.html` inline `<script>`, lines 71-229 — everything after the `const movieId = ...` line):

```javascript
function showError(message) {
    const errorDiv = document.getElementById("tmdb-error");
    errorDiv.textContent = message;
    errorDiv.classList.remove("d-none");
}

function clearError() {
    const errorDiv = document.getElementById("tmdb-error");
    errorDiv.textContent = "";
    errorDiv.classList.add("d-none");
}

function parseJsonResponse(response) {
    return response.json().then((data) => ({
        ok: response.ok,
        data: data
    }));
}

function createCandidateCard(candidate) {
    const col = document.createElement("div");
    col.className = "col";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-link p-0 text-start w-100";
    btn.addEventListener("click", function() {
        linkMovie(candidate.tmdb_id);
    });

    if (candidate.poster_url) {
        const img = document.createElement("img");
        img.src = candidate.poster_url;
        img.className = "img-fluid rounded mb-1";
        img.alt = candidate.title || "";
        btn.appendChild(img);
    }

    const title = document.createElement("div");
    title.textContent = candidate.title || "(sem título)";
    btn.appendChild(title);

    if (candidate.original_title && candidate.original_title !== candidate.title) {
        const originalTitle = document.createElement("div");
        originalTitle.className = "text-muted small";
        originalTitle.textContent = candidate.original_title;
        btn.appendChild(originalTitle);
    }

    if (candidate.release_year) {
        const year = document.createElement("div");
        year.className = "text-muted small";
        year.textContent = candidate.release_year;
        btn.appendChild(year);
    }

    col.appendChild(btn);
    return col;
}

function fetchTmdbCandidates() {
    const query = document.getElementById("tmdb-query").value;
    const resultsDiv = document.getElementById("tmdb-results");
    resultsDiv.innerHTML = "";

    if (query.trim().length < 2) {
        return;
    }

    fetch(`/admin/movies/${movieId}/tmdb-search?q=${encodeURIComponent(query)}`)
        .then(parseJsonResponse)
        .then(({
            ok,
            data
        }) => {
            if (!ok) {
                showError(data.error || "Erro ao buscar no TMDB.");
                return;
            }
            clearError();
            resultsDiv.innerHTML = "";
            if (data.length === 0) {
                resultsDiv.textContent = "Nenhum resultado encontrado.";
                return;
            }
            data.forEach((candidate) => {
                resultsDiv.appendChild(createCandidateCard(candidate));
            });
        })
        .catch(() => {
            showError("Falha de conexão ao buscar no TMDB. Tente novamente.");
        });
}

function updateMetadataDisplay(movie) {
    document.getElementById("field-original_title").textContent = movie.original_title || "—";
    document.getElementById("field-release_year").textContent = movie.release_year || "—";
    document.getElementById("field-original_language").textContent = movie.original_language || "—";
    document.getElementById("field-directors").textContent = movie.directors.join(", ") || "—";
    document.getElementById("field-genres").textContent = movie.genres.join(", ") || "—";
    document.getElementById("field-collection").textContent = movie.collection || "—";
    document.getElementById("field-tmdb-status").textContent = movie.tmdb_id ?
        `Vinculado ao TMDB #${movie.tmdb_id}` :
        "Não vinculado";
}

function linkMovie(tmdbId) {
    fetch(`/admin/movies/${movieId}/tmdb-link`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                tmdb_id: tmdbId
            }),
        })
        .then(parseJsonResponse)
        .then(({
            ok,
            data
        }) => {
            if (!ok) {
                showError(data.error || "Erro ao vincular filme ao TMDB.");
                return;
            }
            clearError();
            updateMetadataDisplay(data);
            document.getElementById("tmdb-results").innerHTML = "";
        })
        .catch(() => {
            showError("Falha de conexão ao vincular filme. Tente novamente.");
        });
}

const unlinkBtn = document.getElementById("unlink-btn");
if (unlinkBtn) {
    unlinkBtn.addEventListener("click", function() {
        fetch(`/admin/movies/${movieId}/tmdb-unlink`, {
                method: "POST"
            })
            .then(parseJsonResponse)
            .then(({
                ok,
                data
            }) => {
                if (!ok) {
                    showError(data.error || "Erro ao remover vínculo com o TMDB.");
                    return;
                }
                clearError();
                updateMetadataDisplay(data);
                unlinkBtn.remove();
            })
            .catch(() => {
                showError("Falha de conexão ao remover vínculo. Tente novamente.");
            });
    });
}
```

- [ ] **Step 4: Rewrite `movie/admin/edit.html` to use both**

Replace the entire file with:

```jinja
{% extends "base.html" %}
{% block title %}
    Editar metadados — {{ movie.title }}
{% endblock title %}
{% block header %}
    <nav aria-label="breadcrumb">
        <ol class="breadcrumb">
            <li class="breadcrumb-item">
                <a href="{{ url_for('movie.show', slug=movie.slug) }}">{{ movie.title }}</a>
            </li>
            <li class="breadcrumb-item active" aria-current="page">Editar metadados</li>
        </ol>
    </nav>
    <h1>Editar metadados</h1>
{% endblock header %}
{% block content %}
    <div class="container">
        {% include "movie/admin/_metadata_panel.html" %}
    </div>
    <script>
        const movieId = parseInt("{{ movie.id }}", 10);
    </script>
    <script src="{{ url_for('static', filename='js/movie-tmdb-metadata.js') }}"></script>
{% endblock content %}
```

- [ ] **Step 5: Verify the safety-net test still passes**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_movies.py -v`
Expected: PASS (same tests, same results as Step 1 — this confirms the refactor didn't change page output in a way the test can detect).

- [ ] **Step 6: Manual verification of no visual/behavioral regression**

Run: `flask --app flask_backend run --debug`, log in, open `/admin/movies/<id>` for any movie. Confirm the page looks identical to before: metadata block, search box, candidate grid on search, clicking a candidate updates the fields in place, "Remover vínculo" still works when a `tmdb_id` is set.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/templates/movie/admin/_metadata_panel.html flask_backend/static/js/movie-tmdb-metadata.js flask_backend/templates/movie/admin/edit.html
git commit -m "refactor: extract shared TMDB metadata partial and JS from movie/admin/edit.html"
```

---

### Task 6: Template — unify `screening/update.html` (Filme + Metadados TMDB sections, "Trocar filme" flow)

**Files:**
- Modify: `flask_backend/templates/screening/update.html` (full rewrite, currently 227 lines)

**Interfaces:**
- Consumes: `movie/admin/_metadata_panel.html` and `static/js/movie-tmdb-metadata.js` (Task 5), `POST /screening/<id>/movie` / endpoint `screening.change_movie` (Task 3), `GET /movies/search?title=&exclude_movie_id=` (Task 2), the fact that `POST /screening/<id>/update` no longer needs a `movie_title` field and now redirects to itself (Task 4).
- Produces: nothing consumed by later tasks — this is a UI leaf.

- [ ] **Step 1: Confirm the pre-existing update tests still pass before touching the template**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k TestScreeningUpdate`
Expected: PASS (these already passed after Task 4; this step is just a baseline before a template-only change, since none of these tests inspect template content beyond flash text).

- [ ] **Step 2: Rewrite the template**

Replace the entire file with:

```jinja
{% extends "base.html" %}
{% block header %}
    <h1 data-goatcounter-skip="true">
        {% block title %}
            Editar "{{ screening.movie['title'] }}"
        {% endblock title %}
    </h1>
{% endblock header %}
{% block content %}
    <p>
        No cinema <strong>{{ screening.cinema.name }}</strong>
    </p>
    <form method="post" enctype="multipart/form-data">
        <div class="mb-3" id="screenings">
            <p>Exibições</p>
            {% for screening_date in screening.dates %}
                <div class="mb-2">
                    <input class="form-control mb-1"
                           type="datetime-local"
                           name="screening_dates"
                           value="{{ screening_date.date }}T{{ screening_date.time }}"
                           min="2023-01-01T00:00"
                           max="2030-12-31T00:00" />
                    <button onclick="removeScreening(this)" type="button" class="btn btn-sm">Remover</button>
                </div>
            {% endfor %}
        </div>
        <div class="mb-3">
            <button type="button" id="add-screening-btn" class="btn btn-secondary">Outra exibição</button>
        </div>
        <div class="mb-3">
            <div class="d-flex mb-2 align-items-center">
                <label for="movie_poster" class="form-label mb-0 me-3">Imagem do filme</label>
                <button type="button"
                        id="gen-alt-btn"
                        class="btn btn-secondary"
                        onclick="fetchImageAltText(event)">
                    <span id="gen-alt-spinner"
                          class="spinner-border spinner-border-sm d-none"
                          role="status"
                          aria-hidden="true"></span>
                    <span id="gen-alt-btn-label">Gerar alt text</span>
                </button>
            </div>
            <input class="form-control"
                   name="movie_poster"
                   type="file"
                   id="movie_poster"
                   data-max-file-size="{{ max_file_size }}"
                   onchange="verifyFileSize(this)"
                   accept="image/*" />
            <input type="hidden"
                   name="current_movie_poster"
                   id="current_movie_poster"
                   value="{{ current_movie_poster }}" />
            <p class="form-text">
                <span id="file-limit-label"></span>
                <span class="text-danger d-block" id="errorMessage"></span>
            </p>
        </div>
        <div class="mb-3">
            <label class="form-label" for="image_alt">Descrição do poster (texto alternativo)</label>
            <textarea placeholder="Descreva a imagem adicionada acima"
                      class="form-control"
                      name="image_alt"
                      id="image_alt">{{ request.form['image_alt'] or screening['image_alt'] }}</textarea>
        </div>
        <div class="mb-3">
            <label class="form-label">Status do cadastro</label>
            <div class="form-check">
                <input class="form-check-input" type="radio" value="draft" name="status"
                    id="status-draft" {{ "checked" if request.form['status'] == 'draft' or
                    screening.draft }}>
                    <label class="form-check-label" for="status-draft">Salvar rascunho</label>
                </div>
                <div class="form-check">
                    <input class="form-check-input" type="radio" value="published"
                        name="status" id="status-published" {{ "checked" if request.form['status']
                        == 'published' or not screening.draft }} />
                        <label class="form-check-label" for="status-published">Publicar</label>
                    </div>
                </div>
                <div class="mb-3">
                    <label class="form-label" for="screening-description">Body</label>
                    <div class="grow-wrap">
                        <textarea class="form-control" name="description" id="screening-description">
{{ request.form['description'] or screening['description'] }}</textarea>
                    </div>
                </div>
                <div class="container mb-3 pb-3">
                    <input class="btn btn-primary" type="submit" value="Save" />
                    <a id="back-btn"
                       class="btn btn-secondary"
                       href="{{ url_for("screening.index") }}">Voltar</a>
                </div>
            </form>
            <hr class="my-4">
            <section class="mb-4" id="movie-section">
                <h2 class="h5">Filme</h2>
                <p>
                    <strong id="movie-title-display">{{ screening.movie.title }}</strong>
                    <button type="button" id="trocar-filme-btn" class="btn btn-sm btn-outline-secondary">Trocar filme</button>
                </p>
                {% set movie_screenings = screening.movie.screenings %}
                {% if movie_screenings|length > 1 %}
                    <p class="text-muted small">
                        Este filme tem {{ movie_screenings|length }} sessões em:
                        {{ movie_screenings|map(attribute='cinema.name')|unique|join(', ') }} —
                        alterações no filme afetam todas.
                    </p>
                {% endif %}
                <div id="trocar-filme-panel" class="d-none">
                    <input autocomplete="off"
                           class="form-control mb-2"
                           id="trocar-filme-query"
                           placeholder="Buscar filme por título"
                           oninput="fetchMovieCandidates()">
                    <ul class="list-unstyled" id="trocar-filme-results"></ul>
                    <div id="trocar-filme-confirm" class="alert alert-warning d-none">
                        <p id="trocar-filme-confirm-text"></p>
                        <button type="button" class="btn btn-sm btn-secondary" id="trocar-filme-cancel">Cancelar</button>
                        <button type="button" class="btn btn-sm btn-warning" id="trocar-filme-confirm-btn">Confirmar</button>
                    </div>
                </div>
            </section>
            <section class="mb-4" id="tmdb-section">
                <h2 class="h5">Metadados TMDB</h2>
                {% with movie = screening.movie %}
                    {% include "movie/admin/_metadata_panel.html" %}
                {% endwith %}
            </section>
            <script>
                function removeScreening(e) {
                    const screeningWrapper = document.getElementById("screenings");
                    if (screeningWrapper.childElementCount == 2) return;
                    e.parentElement.remove();
                }
                window.onload = () => {

                    // Adjusts the "Body" textarea height to show all written text
                    const description = document.getElementById("screening-description");
                    description.style.height = `${description.scrollHeight}px`;

                    // Prevents accidental click on "Voltar" button
                    const backBtn = document.getElementById("back-btn");
                    backBtn.addEventListener("click", (e) => {
                        const proceed = confirm(
                            "Alterações não salvas serão perdidas. Prosseguir?"
                        );
                        if (!proceed) {
                            e.preventDefault();
                            return;
                        }
                    });

                    // Duplicates latest screening by clicking on the "Outra exibição" button
                    const addScreeningBtn = document.getElementById("add-screening-btn");
                    addScreeningBtn.addEventListener("click", (e) => {
                        const screeningWrapper = document.getElementById("screenings");
                        const screeningDiv = screeningWrapper.lastElementChild;
                        const newScreeningDiv = screeningDiv.cloneNode(true);
                        screeningWrapper.appendChild(newScreeningDiv);
                    });

                    document.getElementById("file-limit-label").innerHTML = `Tamanho máximo de imagem de ${getMaxFileSize(true)}mb!`;
                };

                function getMaxFileSize(in_mb) {
                    const inputEl = document.getElementById("movie_poster");
                    const max_file_size_bytes = inputEl.getAttribute('data-max-file-size');
                    if (in_mb) {
                        return max_file_size_bytes / 1024 / 1024;
                    }
                    return max_file_size_bytes;
                };

                function verifyFileSize(input) {
                    const max_size_mb = getMaxFileSize() / 1024 / 1024;
                    const fileSize = input.files[0].size;
                    const errorMessage = document.getElementById("errorMessage");

                    if (fileSize > getMaxFileSize(false)) {
                        input.value = ''; // Limpar o campo de entrada para que o usuário possa selecionar novamente
                        errorMessage.innerHTML = `O tamanho máximo permitido é ${getMaxFileSize(true)}MB. Por favor, selecione um arquivo menor.`;
                    } else {
                        errorMessage.innerHTML = '';
                    }
                }

                async function getFileFromUrl(url, name, defaultType = 'image/jpeg') {
                    const response = await fetch(url);
                    const data = await response.blob();
                    return new File([data], name, {
                        type: data.type || defaultType,
                    });
                }

                async function fetchImageAltText(e) {
                    const btn = e.currentTarget;
                    const spinner = document.getElementById("gen-alt-spinner");
                    const label = document.getElementById("gen-alt-btn-label");

                    const image_input = document.getElementById("movie_poster");
                    const current_movie_poster = document.getElementById("current_movie_poster")
                    const image_alt = document.getElementById("image_alt");

                    // prevent accidental overwriting of existing
                    // image alt text
                    let confirmation = true;
                    if (image_alt.value != "") {
                        confirmation = confirm("Substituir descrição atual?");
                    }
                    if (!confirmation) {
                        return;
                    }

                    const form = new FormData();

                    // if the user selected a new file via input,
                    // use that
                    if (image_input.files.length > 0) {
                        form.append("image", image_input.files[0]);
                    } else if (current_movie_poster.value != "") {
                        form.append('image', await getFileFromUrl(current_movie_poster.value))
                    }

                    btn.disabled = true;
                    spinner.classList.remove("d-none");
                    label.textContent = "Gerando...";
                    try {
                        const response = await fetch("/screening/image/describe", {
                            method: "POST",
                            body: form
                        });
                        const payload = await response.json();

                        if (!response.ok) {
                            alert(payload.details);
                            if (payload.hasOwnProperty("info")) {
                                console.log(payload.info);
                            }
                        }

                        if (response.ok) {
                            image_alt.value = payload.text;
                        }
                    } finally {
                        btn.disabled = false;
                        spinner.classList.add("d-none");
                        label.textContent = "Gerar alt text";
                    }
                }

                const currentMovieId = {{ screening.movie_id }};
                const currentMovieTitle = {{ screening.movie.title|tojson }};
                let pendingMovieChange = null;
                let trocarFilmeDebounce;

                document.getElementById("trocar-filme-btn").addEventListener("click", () => {
                    document.getElementById("trocar-filme-panel").classList.remove("d-none");
                    document.getElementById("trocar-filme-query").focus();
                });

                document.getElementById("trocar-filme-cancel").addEventListener("click", () => {
                    document.getElementById("trocar-filme-confirm").classList.add("d-none");
                    pendingMovieChange = null;
                });

                function fetchMovieCandidates() {
                    clearTimeout(trocarFilmeDebounce);
                    const query = document.getElementById("trocar-filme-query").value.trim();
                    const resultsEl = document.getElementById("trocar-filme-results");
                    resultsEl.innerHTML = "";
                    if (query.length < 2) {
                        return;
                    }

                    trocarFilmeDebounce = setTimeout(() => {
                        fetch(`/movies/search?title=${encodeURIComponent(query)}&exclude_movie_id=${currentMovieId}`)
                            .then((response) => response.json())
                            .then((movies) => {
                                resultsEl.innerHTML = "";
                                movies.forEach((movie) => {
                                    resultsEl.appendChild(createMovieResultItem(movie));
                                });
                                resultsEl.appendChild(createCreateNewItem(query));
                            });
                    }, 300);
                }

                function createMovieResultItem(movie) {
                    const li = document.createElement("li");
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "btn btn-link";
                    btn.textContent = movie.release_year ? `${movie.title} (${movie.release_year})` : movie.title;
                    btn.addEventListener("click", () => showMovieChangeConfirm({
                        movie_id: movie.id
                    }, movie.title, false));
                    li.appendChild(btn);
                    return li;
                }

                function createCreateNewItem(query) {
                    const li = document.createElement("li");
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "btn btn-link";
                    btn.textContent = `Criar novo filme "${query}"`;
                    btn.addEventListener("click", () => showMovieChangeConfirm({
                        new_title: query
                    }, query, true));
                    li.appendChild(btn);
                    return li;
                }

                function showMovieChangeConfirm(change, targetTitle, isNew) {
                    pendingMovieChange = change;
                    const text = isNew ?
                        `Nenhum filme encontrado — será criado um novo filme "${targetTitle}".` :
                        `Esta sessão será desvinculada de "${currentMovieTitle}" e associada a "${targetTitle}". Outras sessões de "${currentMovieTitle}" não são afetadas.`;
                    document.getElementById("trocar-filme-confirm-text").textContent = text;
                    document.getElementById("trocar-filme-confirm").classList.remove("d-none");
                }

                document.getElementById("trocar-filme-confirm-btn").addEventListener("click", () => {
                    if (!pendingMovieChange) {
                        return;
                    }
                    fetch("{{ url_for('screening.change_movie', id=screening.id) }}", {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json"
                            },
                            body: JSON.stringify(pendingMovieChange),
                        })
                        .then((response) => {
                            if (!response.ok) {
                                throw new Error("failed");
                            }
                            return response.json();
                        })
                        .then(() => {
                            window.location.reload();
                        })
                        .catch(() => {
                            alert("Não foi possível trocar o filme. Tente novamente.");
                        });
                });
            </script>
            <script>
                const movieId = {{ screening.movie_id }};
            </script>
            <script src="{{ url_for('static', filename='js/movie-tmdb-metadata.js') }}"></script>
        {% endblock content %}
```

- [ ] **Step 3: Run the update route tests to verify no regression**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v -k TestScreeningUpdate`
Expected: PASS (same as Step 1 — the form fields these tests post/check are unchanged; the new sections don't interfere with the existing `<form>`).

- [ ] **Step 4: Manual verification**

Run: `flask --app flask_backend run --debug`, log in, open `/screening/<id>/update` for any screening:
- Confirm "Sessão", "Filme", and "Metadados TMDB" sections all render.
- Confirm the TMDB search/link/unlink inside this page works the same as on `/admin/movies/<id>`.
- Click "Trocar filme", search for another existing movie's title, confirm the warning text shows the correct current/target titles, confirm, and check the page reloads with the new title shown in "Filme" and updated (or empty) TMDB fields.
- Type a title with no match, confirm the "Criar novo filme" option appears and behaves correctly.
- Submit the "Sessão" form (e.g. change the description) and confirm the page reloads on itself (URL stays `/screening/<id>/update`) with a success flash, instead of navigating to the mobile index.

- [ ] **Step 5: Commit**

```bash
git add flask_backend/templates/screening/update.html
git commit -m "feat: add Filme and Metadados TMDB sections with Trocar filme flow to screening edit"
```

---

### Task 7: Template — edit link on `/admin/alerts`

**Files:**
- Modify: `flask_backend/templates/alerts/admin/index.html` (desktop table cell around lines 136-148, mobile card around lines 172-182)
- Test: `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py` (`class TestAdminAlertsPendingView:`, after `test_shows_copyable_text`)

**Interfaces:**
- Consumes: `screening.update` endpoint (existing route, unchanged signature).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

In `flask_backend/tests/test_routes/test_admin/test_admin_alerts.py`, add to `class TestAdminAlertsPendingView:` after `test_shows_copyable_text` (after line 160):

```python
    def test_shows_edit_link(self, app, auth_headers, setup_cinemas):
        screening_id = _create_screening_with_future_date(app)

        response = auth_headers.get("/admin/alerts")
        assert response.status_code == 200
        assert f"/screening/{screening_id}/update".encode() in response.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_alerts.py -v -k test_shows_edit_link`
Expected: FAIL — the URL isn't in the page yet.

- [ ] **Step 3: Implement**

In `flask_backend/templates/alerts/admin/index.html`, replace the desktop table cell (lines 136-148):

```jinja
                                <td class="w-25">
                                    <div class="input-group input-group-sm">
                                        <textarea class="form-control"
                                                  rows="5"
                                                  readonly
                                                  id="alert-text-{{ row.screening.id }}">{{ row.drafted_text }}</textarea>
                                        <button type="button"
                                                class="btn btn-outline-secondary"
                                                onclick="navigator.clipboard.writeText(document.getElementById('alert-text-{{ row.screening.id }}').value)">
                                            Copiar
                                        </button>
                                        <a href="{{ url_for('screening.update', id=row.screening.id) }}"
                                           class="btn btn-outline-secondary">Editar</a>
                                    </div>
                                </td>
```

And replace the mobile card's input group (lines 172-182):

```jinja
                            <div class="input-group input-group-sm mb-3">
                                <textarea class="form-control"
                                          rows="5"
                                          readonly
                                          id="alert-text-mobile-{{ row.screening.id }}">{{ row.drafted_text }}</textarea>
                                <button type="button"
                                        class="btn btn-outline-secondary"
                                        onclick="navigator.clipboard.writeText(document.getElementById('alert-text-mobile-{{ row.screening.id }}').value)">
                                    Copiar
                                </button>
                                <a href="{{ url_for('screening.update', id=row.screening.id) }}"
                                   class="btn btn-outline-secondary">Editar</a>
                            </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest flask_backend/tests/test_routes/test_admin/test_admin_alerts.py -v`
Expected: PASS (all tests in the file, including the new one).

- [ ] **Step 5: Manual verification**

Run: `flask --app flask_backend run --debug`, log in, open `/admin/alerts` with some pending rows, on both desktop width and mobile width (browser dev tools device toolbar). Confirm "Editar" appears next to "Copiar" in both layouts, links to the right screening's edit page, and that using the browser back button after editing returns to `/admin/alerts` with any filters/status tab still selected.

- [ ] **Step 6: Commit**

```bash
git add flask_backend/templates/alerts/admin/index.html flask_backend/tests/test_routes/test_admin/test_admin_alerts.py
git commit -m "feat: add edit link to /admin/alerts rows"
```

---

### Task 8: Full suite, lint, and format

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest flask_backend/tests`
Expected: all tests PASS, including every pre-existing test untouched by this plan.

- [ ] **Step 2: Lint**

Run: `uv run ruff check --fix`
Expected: no remaining issues (or only issues unrelated to this feature's files — investigate any hit inside `flask_backend/routes/screening.py`, `flask_backend/routes/movie.py`, `flask_backend/repository/screenings.py`, `flask_backend/repository/movies.py`).

- [ ] **Step 3: Format Python**

Run: `uv run ruff format`
Expected: no diffs outside files touched by this plan, or a clean re-format of them.

- [ ] **Step 4: Lint and format templates**

Run:
```bash
uv run djlint flask_backend/templates --lint --profile=jinja
uv run djlint --reformat flask_backend/templates --format-css --format-js
```
Expected: no lint errors in `flask_backend/templates/screening/update.html`, `flask_backend/templates/movie/admin/edit.html`, `flask_backend/templates/movie/admin/_metadata_panel.html`, `flask_backend/templates/alerts/admin/index.html`.

- [ ] **Step 5: Re-run the full suite after formatting**

Run: `pytest flask_backend/tests`
Expected: still all PASS (formatting must not change behavior).

- [ ] **Step 6: Manual end-to-end smoke test**

Run: `flask --app flask_backend run --debug`. Log in on a mobile-width browser window (or device toolbar). From the mobile index, tap "Edite!" on a card, confirm the unified screen loads with all three sections. Make a screening-only edit and save — confirm you land back on the same edit page with a success message. Use "Trocar filme" to reattach to a different existing movie — confirm the confirmation text names the right movie titles, and after confirming, the page shows the new movie's title and (if it has one) its existing TMDB metadata. From `/admin/alerts`, click "Editar" on a pending row, make an edit, save, then use the browser back button — confirm you're back on `/admin/alerts` with your filters intact. Finally, confirm `/admin/movies/<id>` (the movie-only fallback page) still works exactly as before.

- [ ] **Step 7: Commit any formatting fixups**

```bash
git add -A
git commit -m "chore: lint and format unified edit screen feature"
```

(Skip this step if Steps 2-4 produced no changes.)
