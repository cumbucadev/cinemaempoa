# Favoritos Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/favoritos`'s full-screen reels swipe format with a two-section poster grid ("Em exibição" / "Todos os filmes") that reuses `/cinemas/<slug>`'s existing poster-wall visual language, so a visitor can tell at a glance which favorited movies are currently showing.

**Architecture:** `flask_backend/routes/screening.py::favoritos()` buckets `build_favorites_feed`'s existing per-card `no_sessions` flag into two lists and passes both to a rewritten `favoritos.html` (now extending `base.html` instead of `base_reels.html`). A new partial `_favorites_tile.html` renders each movie as a `<details>` element — reusing `poster_tile`'s CSS classes for the visual tile, adding a remove-favorite star and an expand-in-place detail drawer via native `<details>`/`<summary>` (no custom JS needed for open/close). Two new static files (`favoritos.css`, `favoritos.js`) hold the page-specific styling and the small amount of interaction glue the removed `base_reels.html` context no longer supplies for this page.

**Tech Stack:** Flask, Jinja2, vanilla JS (no build step), Bootstrap/Halfmoon CSS, pytest with Flask test client.

Full design rationale: `docs/superpowers/specs/2026-07-28-favoritos-redesign-design.md`.

## Global Constraints

- No changes to `movie/show.html` / `movie.show`.
- No changes to the main reels feed (`screening/index_mobile.html`) or its swipe format.
- No changes to the `poster_tile` macro (`macros/poster_tile.html`) itself — favoritos gets its own partial reusing its CSS classes, not the macro.
- No backend/data-shape changes to `build_favorites_feed` (`flask_backend/service/screening.py:234`) — splitting into two sections is template/route-only, using the `no_sessions` field it already returns.
- No auth changes — favorites stay the anonymous per-visitor cookie mechanism.
- `favoritos.html` switches from `base_reels.html` to `base.html`; loads `cinema.css` + new `favoritos.css` instead of `reels.css`.
- Accent color is set inline exactly as: `<style>:root { --cinema-accent: #9c5b00; }</style>`.
- Exact copy strings (Portuguese), verbatim:
  - Todos os filmes subhead: `Sem sessões agora. Quando um filme volta a passar, ele sobe pra Em exibição.`
  - No favorites at all: `Você ainda não marcou nenhum filme. Toque na estrela em um filme para adicioná-lo aqui.`
  - Nothing currently showing: `Nenhum dos seus filmes está em cartaz agora.`
  - Toast on re-add: `Filme adicionado de volta!`
  - Toast on share fallback: `Link copiado!`

---

### Task 1: `favoritos.css`

**Files:**
- Create: `flask_backend/static/css/favoritos.css`

**Interfaces:**
- Consumes: nothing (pure CSS, no dependency on other tasks).
- Produces: CSS classes `.favorites-tile[open]`, `.favorites-tile-summary`, `.favorites-tile-star`, `.favorites-tile-star[data-wanted="true"]`, `.favorites-tile-detail`, `.favorites-section-subhead`, `.favorites-empty`, `.favorites-toast` — Task 4's templates apply these class names.

CSS/static assets have no automated test coverage in this project (confirmed: no CSS test tooling in `pytest.ini`/CI beyond `ruff`/`djlint` which don't touch `.css`). This task is verified by existence + a syntax sanity check instead of TDD red/green.

- [ ] **Step 1: Create the file**

```css
/* expand-in-place: an opened tile spans the full grid row, pushing
   subsequent tiles onto the next row via the grid's normal auto-flow */
.favorites-tile[open] {
    grid-column: 1 / -1;
}

.favorites-tile-summary {
    list-style: none;
}

.favorites-tile-summary::-webkit-details-marker {
    display: none;
}

.favorites-tile-star {
    position: absolute;
    top: 0.4rem;
    left: 0.4rem;
    z-index: 1;
    width: 1.9rem;
    height: 1.9rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.45);
    color: #fff;
    font-size: 1.1rem;
    line-height: 1;
    padding: 0;
    cursor: pointer;
}

.favorites-tile-star[data-wanted="true"] {
    color: var(--cinema-accent);
}

.favorites-tile-detail {
    padding: 1rem 0.25rem 1.5rem;
}

.favorites-section-subhead {
    margin-top: -0.5rem;
    margin-bottom: 1rem;
    color: var(--bs-secondary-color);
    font-size: 0.85rem;
}

.favorites-empty {
    text-align: center;
    color: var(--bs-secondary-color);
    padding: 3rem 1rem;
}

/* reels-want-to-watch.js / reels-share.js look up these toasts by id
   (#reels-wtw-toast / #reels-share-toast) and no-op if missing - ids stay
   as-is for that, but the visual styling can't come from reels.css's
   .reels-wtw-toast (scoped to .reels-root, which this page no longer has),
   so it gets its own class here using base.html's existing bootstrap
   variables instead of reels-specific tokens. */
.favorites-toast {
    position: fixed;
    top: 4.5rem;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1080;
    background: var(--bs-content-bg);
    border: 1px solid var(--bs-content-border-color);
    border-radius: 0.5rem;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
}
```

- [ ] **Step 2: Sanity-check with the project's CSS formatter**

Run: `uv run djlint --reformat flask_backend/templates --format-css --format-js`

This only reformats templates, not standalone `.css` files, so it won't touch this file — the real check is that no command in this repo's toolchain errors when the file exists. Instead, verify it parses as valid CSS:

Run: `python3 -c "import tinycss2; tinycss2.parse_stylesheet(open('flask_backend/static/css/favoritos.css').read())" 2>/dev/null || echo "tinycss2 not installed, skip"`

If `tinycss2` isn't available, skip this check — it's a bonus sanity check, not a blocking gate. The real verification happens visually in Task 5.

- [ ] **Step 3: Commit**

```bash
git add flask_backend/static/css/favoritos.css
git commit -m "feat: add favoritos.css for the redesigned /favoritos page"
```

---

### Task 2: `favoritos.js`

**Files:**
- Create: `flask_backend/static/favoritos.js`

**Interfaces:**
- Consumes: `reels-want-to-watch.js`'s existing document-level click handler on `[data-function="want-to-watch"]` (must be loaded on the page *before* this file, so both handlers attach — order doesn't affect correctness since this file uses `preventDefault()`, not `stopPropagation()`). Expects buttons with `data-function="want-to-watch"` to live inside a `.favorites-tile` ancestor, and `[data-function="publish"]`/`[data-function="delete"]` buttons with a `data-screening-id` attribute, matching `_favorites_tile.html` from Task 4.
- Produces: suppresses `<summary>`'s native toggle when its `data-function="want-to-watch"` star is clicked; removes the enclosing `.favorites-tile` from the DOM once that button's `data-wanted` attribute flips to `"false"`; wires up `publish`/`delete` buttons (copied behavior from `base_reels.html`, since this page no longer extends it).

No automated test coverage — this is browser-only interactive behavior (confirmed by the design spec's Testing section: "No feasible automated test for the `<details>`-driven expand/collapse or the star-removal `MutationObserver`"). Verified manually in Task 5.

- [ ] **Step 1: Create the file**

```js
document.addEventListener("click", (event) => {
  if (event.target.closest('[data-function="want-to-watch"]')) {
    event.preventDefault(); // suppress <summary>'s native open/close toggle
  }
});

document.addEventListener("click", (event) => {
  const button = event.target.closest('[data-function="want-to-watch"]');
  if (!button) return;
  const tile = button.closest(".favorites-tile");
  if (!tile) return;
  // reels-want-to-watch.js's own handler (loaded before this file) does the
  // fetch/toggle; once it resolves, data-wanted becomes "false" - a page
  // that only lists favorites shouldn't keep showing an unfavorited tile.
  const observer = new MutationObserver(() => {
    if (button.dataset.wanted === "false") {
      tile.remove();
      observer.disconnect();
    }
  });
  observer.observe(button, { attributes: true, attributeFilter: ["data-wanted"] });
});

document.querySelectorAll('[data-function="publish"]').forEach((btn) => {
  btn.addEventListener("click", () => {
    fetch(`/screening/${btn.dataset.screeningId}/publish`, { method: "POST" })
      .then((response) => { if (response.ok) window.location.reload(); })
      .catch((error) => console.error("Error:", error));
  });
});

document.querySelectorAll('[data-function="delete"]').forEach((btn) => {
  btn.addEventListener("click", () => {
    fetch(`/screening/${btn.dataset.screeningId}/delete`, { method: "POST" })
      .then((response) => { if (response.ok) window.location.reload(); })
      .catch((error) => console.error("Error:", error));
  });
});
```

- [ ] **Step 2: Syntax-check the file**

Run: `node --check flask_backend/static/favoritos.js`

Expected: no output, exit code 0. If `node` isn't available in this environment, skip — the file will still be exercised manually in Task 5.

- [ ] **Step 3: Commit**

```bash
git add flask_backend/static/favoritos.js
git commit -m "feat: add favoritos.js interaction glue for the redesigned /favoritos page"
```

---

### Task 3: Route split, tile partial, page template, and tests

**Files:**
- Modify: `flask_backend/routes/screening.py:518-525` (the `favoritos()` view)
- Create: `flask_backend/templates/screening/_favorites_tile.html`
- Modify: `flask_backend/templates/screening/favoritos.html` (full rewrite)
- Modify: `flask_backend/tests/test_routes/test_screening.py` (`TestFavoritos` class: remove one obsolete test, add five new tests)

**Interfaces:**
- Consumes: `build_favorites_feed(movie_ids, today, user_logged_in)` (existing, `flask_backend/service/screening.py:234`), which returns a list of dicts each with (at minimum) `movie_id`, `movie_title`, `directors`, `release_year`, `description`, `image`, `image_alt`, `cinema_name`, `soonest_date`, `soonest_time`, `next_dates`, `draft`, `screening_url`, `no_sessions`, `screening_id`. Also consumes the `CANONICAL_BASE_URL` constant already defined and imported in `screening.py:68` (`"https://cinemaempoa.com.br"`) — the just-merged `feat/reels-share` work (PR #283, now on `main`) changed `favoritos()` to already pass this as `canonical_base_url` into the template context, because `_reels_card.html`'s share button now builds its URL as `{{ canonical_base_url }}{{ url_for(...) }}` instead of `url_for(..., _external=True)` (see `flask_backend/tests/test_routes/test_screening.py::TestFavoritos::test_share_url_uses_the_canonical_production_domain`, which must keep passing). The new tile partial follows the same convention. Consumes CSS classes/files from Task 1 (`favoritos.css`) and JS from Task 2 (`favoritos.js`).
- Produces: `favoritos()` now renders `screening/favoritos.html` with `em_exibicao` (list, `no_sessions=False`, sorted by soonest date — unchanged from `build_favorites_feed`'s own order), `todos` (list, `no_sessions=True`, sorted alphabetically by `movie_title`), and `canonical_base_url` (unchanged, passed through as before) instead of a single `cards` list.

This task's tests only make sense once the route and both templates exist together (each is untestable alone via this project's HTTP-integration test style), so it follows TDD at the task level: write the new/updated tests first, confirm they fail against the *current* (pre-change) implementation, then implement route + templates, then confirm everything passes.

- [ ] **Step 1: Update `TestFavoritos` in `flask_backend/tests/test_routes/test_screening.py`**

First, delete this now-obsolete test (it asserts on `_reels_card.html`'s custom `data-src`/`IntersectionObserver` lazy-loading, which `favoritos.html` will no longer use — `poster_tile`-style tiles use the browser's native `loading="lazy"` instead, same as `/cinemas/<slug>`):

```python
    def test_third_card_onward_defers_poster_loading_via_shared_scripts(
        self, client, setup_cinemas
    ):
        # /favoritos shares _reels_card.html with the homepage, which only
        # ever loads because base_reels.html carries the lazy-poster
        # IntersectionObserver script both pages extend from - this guards
        # against that script silently going missing again on either page.
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            client.set_cookie("visitor_id", "visitor-a")
            for i in range(3):
                screening_id = _create_screening(
                    movie_title=f"Filme Favorito {i}",
                    image=f"poster{i}.jpg",
                    image_width=100,
                    image_height=200,
                    screening_date=date.today() + timedelta(days=i + 1),
                )
                movie_id = db_session.query(Screening).get(screening_id).movie_id
                toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert 'data-src="poster2.jpg"' in html
        assert "posterObserver" in html
        assert "IntersectionObserver" in html
```

Also note two tests already exist in `TestFavoritos` from the just-merged `feat/reels-share` work that this task doesn't touch but must keep passing: `test_share_url_uses_the_canonical_production_domain` (asserts the share button's `data-share-url` on `/favoritos` resolves to `https://cinemaempoa.com.br/?screening=<id>`) and `test_sidebar_links_back_to_home_and_highlights_meus_filmes` (asserts the offcanvas menu highlights "Meus Filmes" — unaffected by this task since `partials/site_menu.html` is included by `base.html` exactly as it was by `base_reels.html`).

Then, add these five tests at the end of the `TestFavoritos` class, immediately after `test_sidebar_links_back_to_home_and_highlights_meus_filmes` (now the last method in the class), keeping the same indentation/class body:

```python
    def test_splits_movies_into_em_exibicao_and_todos_sections(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            showing_id = _create_screening(
                movie_title="Filme Em Cartaz",
                screening_date=date.today() + timedelta(days=2),
            )
            showing_movie_id = db_session.query(Screening).get(showing_id).movie_id
            stale_id = _create_screening(
                movie_title="Filme Arquivado",
                screening_date=date.today() - timedelta(days=30),
            )
            stale_movie_id = db_session.query(Screening).get(stale_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(showing_movie_id, "visitor-a")
            toggle(stale_movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        em_exibicao_index = html.index("Em exibição")
        todos_index = html.index("Todos os filmes")
        showing_index = html.index("Filme Em Cartaz")
        archived_index = html.index("Filme Arquivado")
        assert em_exibicao_index < showing_index < todos_index < archived_index

    def test_todos_section_sorted_alphabetically(self, client, setup_cinemas):
        with client.application.app_context():
            zeta_id = _create_screening(
                movie_title="Filme Zeta",
                screening_date=date.today() - timedelta(days=10),
            )
            zeta_movie_id = db_session.query(Screening).get(zeta_id).movie_id
            alfa_id = _create_screening(
                movie_title="Filme Alfa",
                screening_date=date.today() - timedelta(days=5),
            )
            alfa_movie_id = db_session.query(Screening).get(alfa_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(zeta_movie_id, "visitor-a")
            toggle(alfa_movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert html.index("Filme Alfa") < html.index("Filme Zeta")

    def test_hides_todos_section_when_everything_is_showing(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Único",
                screening_date=date.today() + timedelta(days=1),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert "Todos os filmes" not in html

    def test_shows_no_screenings_message_when_none_showing(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Parado",
                screening_date=date.today() - timedelta(days=15),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert "Nenhum dos seus filmes está em cartaz agora." in html

    def test_date_badge_only_shown_for_em_exibicao_cards(self, client, setup_cinemas):
        with client.application.app_context():
            showing_id = _create_screening(
                movie_title="Filme Com Data",
                screening_date=date.today() + timedelta(days=3),
            )
            showing_movie_id = db_session.query(Screening).get(showing_id).movie_id
            stale_id = _create_screening(
                movie_title="Filme Sem Data",
                screening_date=date.today() - timedelta(days=20),
            )
            stale_movie_id = db_session.query(Screening).get(stale_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(showing_movie_id, "visitor-a")
            toggle(stale_movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert html.count('class="poster-tile-badge"') == 1
```

- [ ] **Step 2: Run the tests to verify the five new tests fail (and confirm the rest still pass)**

Run: `uv run pytest flask_backend/tests/test_routes/test_screening.py -k TestFavoritos -v`

Expected, precisely (the five new tests don't all fail the same way against the old template — check each on its own terms, not just "red = good"):

- `test_returns_200`, `test_shows_empty_state_without_a_visitor_cookie`, `test_shows_marked_movie_with_upcoming_screening`, `test_share_url_uses_the_canonical_production_domain`, `test_shows_marked_movie_with_no_upcoming_screening_as_stale`, `test_toggle_then_favoritos_then_untoggle_round_trip`, `test_sidebar_links_back_to_home_and_highlights_meus_filmes` — PASS (untouched by this change so far).
- `test_splits_movies_into_em_exibicao_and_todos_sections` — FAILS (errors on `html.index("Em exibição")`, `ValueError: substring not found` — the old template never renders that heading).
- `test_shows_no_screenings_message_when_none_showing` — FAILS (the old template's empty-ish states never render "Nenhum dos seus filmes está em cartaz agora.").
- `test_date_badge_only_shown_for_em_exibicao_cards` — FAILS (the old template has no `poster-tile-badge` class anywhere; count is 0, not 1).
- `test_hides_todos_section_when_everything_is_showing` — may PASS already, vacuously: the old template never renders "Todos os filmes" under any circumstances, so the assertion holds for the wrong reason. That's fine — it becomes a real, meaningful check once Step 5 introduces that heading; don't treat this one passing here as a problem.
- `test_todos_section_sorted_alphabetically` — outcome against the old template is unspecified/order-dependent (the old code's stale-card order comes from iterating a `Set`, not a sort), so it may pass or fail non-deterministically at this checkpoint. Don't rely on its result here; it becomes deterministic and meaningful only after Step 3's `sorted(...)` is in place.

- [ ] **Step 3: Update the route**

In `flask_backend/routes/screening.py`, replace the `favoritos()` view (currently lines 518-525 — note it already passes `canonical_base_url` as of the just-merged `feat/reels-share` PR; this must be preserved, not dropped):

```python
def favoritos():
    visitor_id = get_visitor_id(request)
    movie_ids = list(get_movie_ids_for_visitor(visitor_id)) if visitor_id else []
    user_logged_in = g.user is not None
    cards = build_favorites_feed(movie_ids, date.today(), user_logged_in)
    return render_template(
        "screening/favoritos.html", cards=cards, canonical_base_url=CANONICAL_BASE_URL
    )
```

with:

```python
def favoritos():
    visitor_id = get_visitor_id(request)
    movie_ids = list(get_movie_ids_for_visitor(visitor_id)) if visitor_id else []
    user_logged_in = g.user is not None
    cards = build_favorites_feed(movie_ids, date.today(), user_logged_in)
    em_exibicao = [card for card in cards if not card["no_sessions"]]
    todos = sorted(
        (card for card in cards if card["no_sessions"]),
        key=lambda card: card["movie_title"],
    )
    return render_template(
        "screening/favoritos.html",
        em_exibicao=em_exibicao,
        todos=todos,
        canonical_base_url=CANONICAL_BASE_URL,
    )
```

No new imports needed — `date`, `get_visitor_id`, `get_movie_ids_for_visitor`, `build_favorites_feed`, and `CANONICAL_BASE_URL` are already imported/defined in this file (the `@bp.route("/favoritos")` decorator above the function is unchanged, keep it).

- [ ] **Step 4: Create `flask_backend/templates/screening/_favorites_tile.html`**

`{% include %}` shares the including template's full context by default, so `canonical_base_url` (passed to `favoritos.html` in Step 3) is already in scope here without any extra wiring — same mechanism `_reels_card.html` relies on.

```html
<details class="favorites-tile"
          name="favorites-detail-{{ 'showing' if not card.no_sessions else 'archive' }}">
  <summary class="poster-tile favorites-tile-summary">
    <button type="button"
            class="favorites-tile-star"
            data-function="want-to-watch"
            data-movie-id="{{ card.movie_id }}"
            data-wanted="true"
            aria-pressed="true"
            aria-label="Remover dos meus filmes">
      <span aria-hidden="true">★</span>
    </button>
    {% if card.image %}
      <img class="poster-tile-img" src="{{ card.image }}" loading="lazy"
           alt="{{ card.image_alt or card.movie_title }}">
    {% else %}
      <span class="poster-tile-placeholder" aria-hidden="true">{{ card.movie_title[0] }}</span>
    {% endif %}
    {% if not card.no_sessions %}
      <span class="poster-tile-badge">
        {{ card.soonest_date.strftime("%d/%m") }}{% if card.soonest_time %} {{ card.soonest_time }}{% endif %}
      </span>
    {% endif %}
    <span class="poster-tile-scrim">
      <span class="poster-tile-title">{{ card.movie_title }}</span>
    </span>
  </summary>
  <div class="favorites-tile-detail">
    <h3>{{ card.movie_title }}</h3>
    <p class="text-muted">
      {% if card.directors %}{{ card.directors|join(", ") }}{% endif %}
      {% if card.release_year %}{% if card.directors %}·{% endif %} {{ card.release_year }}{% endif %}
      {% if card.cinema_name %}· {{ card.cinema_name }}{% endif %}
    </p>
    <p>{{ card.description }}</p>
    {% if card.next_dates %}
      <h4 class="h6">Próximas sessões</h4>
      <ul class="list-unstyled">
        {% for next_date in card.next_dates %}
          <li>{{ next_date.date.strftime("%d/%m") }} · {{ next_date.cinema_name }}
            {% if next_date.time %}· {{ next_date.time }}{% endif %}</li>
        {% endfor %}
      </ul>
    {% elif card.no_sessions %}
      <p class="text-muted">Não há sessões previstas no momento.</p>
    {% endif %}
    {# Compute share text once, same pattern _reels_card.html uses, to keep
       the attribute readable and satisfy djlint #}
    {%- if card.soonest_date %}
      {%- set share_text = card.cinema_name + " · " + card.soonest_date.strftime("%d/%m") + ((" " + card.soonest_time) if card.soonest_time else "") %}
    {%- else %}
      {%- set share_text = card.cinema_name %}
    {%- endif %}
    <p>
      <button type="button" class="favorites-tile-share" data-function="share"
              data-share-url="{{ canonical_base_url }}{{ url_for('screening.index', screening=card.screening_id) }}"
              data-movie-title="{{ card.movie_title }}"
              data-share-text="{{ share_text }}"
              aria-label="Compartilhar">Compartilhar</button>
    </p>
    {% if card.screening_url %}
      <p><a href="{{ card.screening_url }}">Veja a postagem original</a></p>
    {% endif %}
    <p>
      {% if g.user %}
        <a href="{{ url_for('screening.update', id=card.screening_id) }}">Edite!</a>
      {% else %}
        <a href="{{ url_for('screening.update', id=card.screening_id) }}">Achou um erro? Ajude a corrigir!</a>
      {% endif %}
    </p>
    {% if card.draft %}
      <p>
        <button class="badge text-bg-warning" data-function="publish" data-screening-id="{{ card.screening_id }}">Publicar</button>
        <button class="badge text-bg-danger" data-function="delete" data-screening-id="{{ card.screening_id }}">Descartar</button>
      </p>
    {% endif %}
  </div>
</details>
```

- [ ] **Step 5: Rewrite `flask_backend/templates/screening/favoritos.html`**

Replace the entire file with:

```html
{% extends "base.html" %}
{% block meta_tags %}
    <meta name="description"
          content="Filmes que você marcou como &quot;quero assistir&quot; no cinemaempoa.">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/cinema.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/favoritos.css') }}">
    {# djlint:off #}
    <style>:root { --cinema-accent: #9c5b00; }</style>
    {# djlint:on #}
{% endblock meta_tags %}
{% block title %}
    Meus Filmes
{% endblock title %}
{% block header %}
    <h1>Meus Filmes</h1>
{% endblock header %}
{% block content %}
    {% if not em_exibicao and not todos %}
        <p class="favorites-empty">Você ainda não marcou nenhum filme. Toque na
        estrela em um filme para adicioná-lo aqui.</p>
    {% else %}
        <h2 class="section-eyebrow">
            <span class="section-eyebrow-dot" aria-hidden="true"></span>
            Em exibição
        </h2>
        {% if em_exibicao %}
            <div class="poster-grid mb-5">
                {% for card in em_exibicao %}
                    {% include "screening/_favorites_tile.html" %}
                {% endfor %}
            </div>
        {% else %}
            <p class="text-muted mb-5">Nenhum dos seus filmes está em cartaz agora.</p>
        {% endif %}
        {% if todos %}
            <h2 class="section-eyebrow">Todos os filmes</h2>
            <p class="favorites-section-subhead">Sem sessões agora. Quando um filme
            volta a passar, ele sobe pra Em exibição.</p>
            <div class="poster-grid">
                {% for card in todos %}
                    {% include "screening/_favorites_tile.html" %}
                {% endfor %}
            </div>
        {% endif %}
    {% endif %}
    <div id="reels-wtw-toast"
         class="toast favorites-toast"
         role="status"
         aria-live="polite"
         aria-atomic="true"
         data-bs-autohide="true"
         data-bs-delay="3000">
        <div class="toast-body">Filme adicionado de volta!</div>
    </div>
    <div id="reels-share-toast"
         class="toast favorites-toast"
         role="status"
         aria-live="polite"
         aria-atomic="true"
         data-bs-autohide="true"
         data-bs-delay="3000">
        <div class="toast-body">Link copiado!</div>
    </div>
    <script src="{{ url_for('static', filename='reels-want-to-watch.js') }}"></script>
    <script src="{{ url_for('static', filename='reels-share.js') }}"></script>
    <script src="{{ url_for('static', filename='favoritos.js') }}"></script>
{% endblock content %}
```

- [ ] **Step 6: Run the full `TestFavoritos` suite again**

Run: `uv run pytest flask_backend/tests/test_routes/test_screening.py -k TestFavoritos -v`

Expected: all 12 tests pass (the 7 pre-existing ones untouched — including `test_share_url_uses_the_canonical_production_domain`, which now depends on Step 4's `canonical_base_url`/`share_text` handling in the new partial — plus the 5 new ones from Step 1).

- [ ] **Step 7: Run the full backend test suite to check for regressions elsewhere**

Run: `uv run pytest flask_backend/tests -q`

Expected: all tests pass — in particular, confirm nothing else in the suite asserts on `favoritos.html` extending `base_reels.html` or on the old single-`cards` template variable (e.g. grep first: `grep -rn "favoritos" flask_backend/tests/ --include="*.py" -l`, then check any hits outside `test_screening.py` for now-stale assumptions).

- [ ] **Step 8: Commit**

```bash
git add flask_backend/routes/screening.py flask_backend/templates/screening/_favorites_tile.html flask_backend/templates/screening/favoritos.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: redesign /favoritos as a two-section poster grid"
```

---

### Task 4: Lint, format, and full test suite

**Files:**
- Modify (formatting only, if needed): any of the files touched in Tasks 1-3.

**Interfaces:**
- Consumes: all files from Tasks 1-3.
- Produces: a fully linted/formatted diff ready for review, per this repo's `CLAUDE.md` requirement to run all four lint/format commands before opening a PR.

- [ ] **Step 1: Run ruff lint + format**

Run: `uv run ruff check --fix && uv run ruff format`

Expected: no errors; if it reformats `screening.py` or `test_screening.py`, review the diff to confirm it's whitespace/style only.

- [ ] **Step 2: Run djlint lint + format on templates**

Run: `uv run djlint flask_backend/templates --lint --profile=jinja`

Expected: no new lint errors from `favoritos.html` or `_favorites_tile.html`. If there are complaints (e.g. attribute ordering), fix them, then run:

Run: `uv run djlint --reformat flask_backend/templates --format-css --format-js`

- [ ] **Step 3: Re-run the full test suite to confirm formatting didn't break anything**

Run: `uv run pytest -q`

Expected: same pass count as Task 3 Step 7 (all tests pass).

- [ ] **Step 4: Commit any formatting fixes**

```bash
git add -A
git status
```

Review the diff before committing — only stage files actually touched by this feature (avoid picking up unrelated in-progress work if this worktree ever shares state with other branches, which it shouldn't since it's isolated).

```bash
git commit -m "chore: lint and format favoritos redesign changes"
```

(Skip this step entirely if Steps 1-2 made no changes.)

---

### Task 5: Manual verification in the browser

**Files:** none (verification only — none of this interactive behavior is covered by pytest, so it needs an actual browser to confirm before this feature can be called done).

**Interfaces:**
- Consumes: the running Flask dev server and a browser.
- Produces: a confirmation (in the task's final report) that each of the following was visually verified, since none of it is covered by Tasks 1-4's automated tests:
  1. Empty state (no favorites) shows the star-tap message.
  2. A favorited movie with an upcoming screening appears under "Em exibição" with a date badge.
  3. A favorited movie with no upcoming screening appears under "Todos os filmes", no badge.
  4. When nothing is currently showing, "Em exibição" shows the "Nenhum dos seus filmes está em cartaz agora." message instead of an empty grid, and the "Todos os filmes" subhead is visible.
  5. When everything is currently showing, "Todos os filmes" (heading + subhead) is omitted entirely.
  6. Clicking a poster (not the star) expands the detail drawer in place — description, sessions, share button, edit link — and clicking another poster in the same section closes the first one (accordion behavior via `<details name="...">`).
  7. Clicking the ★ removes the tile immediately without navigating or opening the drawer, and shows the "Filme adicionado de volta!" toast if you re-add it from elsewhere.
  8. Dark and light theme both render legibly (toggle OS theme or use `prefers-color-scheme` emulation) — check the amber accent, poster placeholder, and badge contrast in both.
  9. Mobile viewport width (e.g. 375px) still shows a usable 3-column grid.

- [ ] **Step 1: Seed test data**

Run: `flask --app flask_backend run --debug` in one terminal (after `flask --app flask_backend init-db` and `flask --app flask_backend seed-db` if the local `development.sqlite` isn't already populated). Use the app's own UI or a quick script to mark at least one movie with an upcoming screening and one with only past screenings as "quero assistir" (the ★ toggle on the homepage), covering states 2 and 3 above at minimum. Use two different browser sessions or clear the `visitor_id` cookie to exercise states 4 and 5 independently if needed (state 4 needs only stale favorites, state 5 needs only current-screening favorites).

- [ ] **Step 2: Walk through states 1-9 above in the browser**

Navigate to `http://localhost:5000/favoritos` in each configuration described above (use browser dev tools to toggle dark/light and viewport width). Confirm each item visually.

- [ ] **Step 3: Report results**

In the final task report, list each of the 9 items above with a pass/fail note. If anything fails, fix it (small template/CSS/JS corrections) and re-verify before considering this task done — do not report success without having actually looked at the rendered page, per this project's verification conventions.
