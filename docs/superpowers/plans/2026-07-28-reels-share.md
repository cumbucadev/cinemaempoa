# Reels Card Share Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a share button to each mobile reels card that opens the native share sheet with a deep link back to that exact card, with graceful fallback to the movie's page on desktop or when the shared screening has aged out of the feed.

**Architecture:** The existing `GET /` route gains a `?screening=<id>` query param. Server-side, it resolves to either "render the reels feed with this card highlighted" (mobile, screening still in the 6-day window) or "redirect to `/movies/<slug>`" (desktop, or screening no longer in the window, or missing/invalid). The card partial gets a new share button that calls `navigator.share()` with a link built from that resolution, falling back to clipboard-copy where Web Share isn't supported.

**Tech Stack:** Flask/Jinja templates, vanilla JS (no build step, no JS test runner in this repo), existing GoatCounter analytics, pytest for backend tests.

## Global Constraints

- Run `uv run ruff check --fix`, `uv run ruff format`, and `uv run djlint flask_backend/templates --lint --profile=jinja` before considering any task done (per `CLAUDE.md`).
- Never commit changes to `development.sqlite` / `flask_backend.sqlite`.
- No AI/agent co-author trailer in commits (per `CLAUDE.md`).
- Client-side JS (Web Share API, clipboard fallback) has no automated test coverage in this repo — verify manually in a real mobile browser per `CLAUDE.md`'s UI-testing convention; say so explicitly rather than claiming it's covered.
- Spec: `docs/superpowers/specs/2026-07-28-reels-share-design.md`.

---

## File Structure

- **Modify** `flask_backend/routes/screening.py` — `index()`/`_mobile_index()` gain the `screening` query-param resolution (redirect vs. highlight).
- **Modify** `flask_backend/templates/screening/index_mobile.html` — conditional OG tags + scroll-to-card script, driven by a new `shared_card` template variable.
- **Modify** `flask_backend/templates/screening/_reels_card.html` — new share button in `.reels-actions`, and an `id` on the card section for scroll targeting.
- **Modify** `flask_backend/static/css/reels.css` — share button styling (extends existing `.reels-want-to-watch` rules to also apply to `.reels-share`).
- **Create** `flask_backend/static/reels-share.js` — click handler: Web Share API, clipboard fallback, GoatCounter tracking.
- **Modify** `flask_backend/templates/base_reels.html` — load `reels-share.js`, add `#reels-share-toast` markup.
- **Modify** `flask_backend/tests/test_routes/test_screening.py` — new test class covering the six routing cases and the share button/OG-tag markup.

---

### Task 1: Shared-link resolution in the `/` route

**Files:**
- Modify: `flask_backend/routes/screening.py:66-95` (the `_mobile_index` function and the top of `index()`)
- Test: `flask_backend/tests/test_routes/test_screening.py`

**Interfaces:**
- Consumes: `get_screening_by_id(screening_id: int) -> Optional[Screening]` (already imported at `flask_backend/routes/screening.py:35`); `is_mobile_user_agent(user_agent: str) -> bool` (already imported at `flask_backend/routes/screening.py:56`); `Screening.movie.slug` (existing relationship/column).
- Produces: `_mobile_index(shared_screening: Optional[Screening] = None)` — used only within this module. `index_mobile.html` now receives an extra `shared_card` context var (a `dict` from `build_reels_feed`'s card list, or `None`) — Task 2 depends on this name and shape.

- [ ] **Step 1: Write the failing tests**

Add this test class near the existing `TestScreeningIndexMobile` class in `flask_backend/tests/test_routes/test_screening.py` (after it, before `def _create_movie(...)`):

```python
class TestScreeningSharedLink:
    def test_mobile_with_screening_in_current_feed_renders_and_highlights_card(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Compartilhável",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert f'id="reels-card-{screening_id}"' in html

    def test_desktop_with_valid_screening_redirects_to_movie_page(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Redirecionado",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(f"/?screening={screening_id}")
        assert response.status_code == 302
        assert response.headers["Location"] == "/movies/filme-redirecionado"

    def test_mobile_with_screening_aged_out_of_feed_redirects_to_movie_page(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Expirado",
                screening_date=date.today() - timedelta(days=30),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/movies/filme-expirado"

    def test_invalid_screening_id_falls_back_to_normal_mobile_feed(
        self, client, setup_cinemas
    ):
        response = client.get("/?screening=999999", headers={"User-Agent": MOBILE_UA})
        assert response.status_code == 200

    def test_non_integer_screening_param_falls_back_to_normal_mobile_feed(
        self, client, setup_cinemas
    ):
        response = client.get("/?screening=abc", headers={"User-Agent": MOBILE_UA})
        assert response.status_code == 200

    def test_screening_with_movie_missing_slug_falls_back_to_normal_mobile_feed(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            cinema = _get_cinema()
            movie = Movie(title="Filme Sem Slug", slug=None)
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="A description",
                dates=[
                    ScreeningDate(
                        date=date.today() + timedelta(days=1), time="20:00"
                    )
                ],
            )
            db_session.add(screening)
            db_session.commit()
            screening_id = screening.id
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        assert response.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -k TestScreeningSharedLink -v`
Expected: `test_mobile_with_screening_in_current_feed_renders_and_highlights_card` and the two redirect tests FAIL (no `id="reels-card-*"` in output yet, and no redirect happens since `screening` is currently ignored by the route). The three fallback tests PASS already (current behavior already renders 200 regardless of the param), which is fine — they lock in behavior Step 3 must preserve.

- [ ] **Step 3: Implement the routing logic**

Replace `flask_backend/routes/screening.py:66-95` with:

```python
def _mobile_index(shared_screening: Optional[Screening] = None):
    now = datetime.now()
    today = now.date()
    window_end = today + timedelta(days=6)
    user_logged_in = g.user is not None

    screenings = get_screenings_in_date_range(today, window_end)
    movie_ids = list({screening.movie_id for screening in screenings})
    movie_dates = get_screening_dates_for_movies(
        movie_ids, today, window_end, include_drafts=user_logged_in
    )
    visitor_id = get_visitor_id(request)
    wanted_movie_ids = get_movie_ids_for_visitor(visitor_id) if visitor_id else set()
    cards = build_reels_feed(
        screenings,
        movie_dates,
        today,
        window_end,
        user_logged_in,
        earliest_datetime=now,
        wanted_movie_ids=wanted_movie_ids,
    )

    shared_card = None
    if shared_screening is not None:
        shared_card = next(
            (card for card in cards if card["screening_id"] == shared_screening.id),
            None,
        )
        if shared_card is None:
            return redirect(url_for("movie.show", slug=shared_screening.movie.slug))

    return render_template(
        "screening/index_mobile.html", cards=cards, shared_card=shared_card
    )


@bp.route("/")
def index():
    screening_id = request.args.get("screening", type=int)
    shared_screening = get_screening_by_id(screening_id) if screening_id else None
    if shared_screening is not None and not shared_screening.movie.slug:
        shared_screening = None

    is_mobile = is_mobile_user_agent(request.headers.get("User-Agent", ""))

    if shared_screening is not None and not is_mobile:
        return redirect(url_for("movie.show", slug=shared_screening.movie.slug))

    if is_mobile:
        return _mobile_index(shared_screening)
```

Note `Optional` must already be importable — check the top of `flask_backend/routes/screening.py`; if `Optional` isn't already imported from `typing`, add it to the existing `from typing import List` line as `from typing import List, Optional`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -k "TestScreeningSharedLink or TestScreeningIndexMobile" -v`
Expected: all PASS, including the pre-existing `TestScreeningIndexMobile` class (no regression to the plain `/` behavior).

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest flask_backend/tests`
Expected: all PASS.

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check --fix flask_backend/routes/screening.py && uv run ruff format flask_backend/routes/screening.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/routes/screening.py flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: resolve shared reels-card deep links on the / route"
```

---

### Task 2: `shared_card` template plumbing — OG tags and scroll-to-card

**Files:**
- Modify: `flask_backend/templates/screening/index_mobile.html`
- Test: `flask_backend/tests/test_routes/test_screening.py`

**Interfaces:**
- Consumes: `shared_card` (dict or `None`) and `cards` (list of dicts) from the render context — produced by Task 1's `_mobile_index`. Card dict fields used: `screening_id`, `movie_title`, `description`, `image`.
- Produces: nothing consumed by later tasks — this is purely template output (meta tags + a scroll script). Task 3 independently relies on `id="reels-card-{{ card.screening_id }}"` existing on each card section, which this task does NOT add (see Task 3) — don't duplicate the `id` here.

- [ ] **Step 1: Write the failing tests**

Add to `TestScreeningSharedLink` in `flask_backend/tests/test_routes/test_screening.py`:

```python
    def test_shared_card_renders_movie_specific_og_tags(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme OG",
                image="poster-og.jpg",
                image_width=100,
                image_height=200,
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        html = response.get_data(as_text=True)
        assert '<meta property="og:title" content="Filme OG">' in html
        assert '<meta property="og:image" content="poster-og.jpg">' in html

    def test_plain_feed_keeps_generic_og_tags(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert "Programação do dia" in html
        assert 'property="og:title"' not in html

    def test_shared_card_scrolls_to_its_card_on_load(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Scroll",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        html = response.get_data(as_text=True)
        assert f'getElementById("reels-card-{screening_id}")' in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -k "og_tags or scrolls_to_its_card or generic_og_tags" -v`
Expected: FAIL — `index_mobile.html` doesn't emit any OG tags or scroll script yet.

- [ ] **Step 3: Implement the template changes**

Replace the top of `flask_backend/templates/screening/index_mobile.html` (currently lines 1-8) with:

```html
{% extends "base_reels.html" %}
{% block title %}
    Programação do dia
{% endblock title %}
{% block meta_tags %}
    {% if shared_card %}
        <meta property="og:title" content="{{ shared_card.movie_title }}">
        <meta property="og:description"
              content="{{ shared_card.description or shared_card.movie_title }}">
        {% if shared_card.image %}<meta property="og:image" content="{{ shared_card.image }}">{% endif %}
    {% else %}
        <meta name="description"
              content="Filmes em cartaz nos próximos dias nas salas de cinema alternativo em Porto Alegre.">
    {% endif %}
{% endblock meta_tags %}
```

Then, right before `{% endblock content %}` at the end of the file, add:

```html
    {% if shared_card %}
        <script>
            document.getElementById("reels-card-{{ shared_card.screening_id }}")
                ?.scrollIntoView({ behavior: "instant", block: "start" });
        </script>
    {% endif %}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -k TestScreeningSharedLink -v`
Expected: `test_shared_card_renders_movie_specific_og_tags` and `test_plain_feed_keeps_generic_og_tags` PASS. `test_shared_card_scrolls_to_its_card_on_load` still FAILs — it needs the `id="reels-card-..."` attribute from Task 3, which doesn't exist yet. That's expected; it will pass once Task 3 lands. Confirm the failure is specifically about the missing `id`, not the script itself, by checking the script tag is present in the HTML output.

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest flask_backend/tests`
Expected: all PASS except `test_shared_card_scrolls_to_its_card_on_load` (known, resolved by Task 3).

- [ ] **Step 6: Lint templates**

Run: `uv run djlint flask_backend/templates/screening/index_mobile.html --lint --profile=jinja` and `uv run djlint --reformat flask_backend/templates/screening/index_mobile.html --format-css --format-js`
Expected: no errors after reformatting.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/templates/screening/index_mobile.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: render per-movie OG tags and scroll-to-card for shared reels links"
```

---

### Task 3: Share button markup and styling on the reels card

**Files:**
- Modify: `flask_backend/templates/screening/_reels_card.html`
- Modify: `flask_backend/static/css/reels.css:313-337`
- Test: `flask_backend/tests/test_routes/test_screening.py`

**Interfaces:**
- Consumes: `card.screening_id`, `card.movie_title`, `card.cinema_name`, `card.soonest_date`, `card.soonest_time` (all already present in the card dict built by `build_reels_feed`/`build_favorites_feed`).
- Produces: `id="reels-card-{{ card.screening_id }}"` on each `.reels-card` section (completes Task 2's scroll-to-card test). `button[data-function="share"]` with `data-share-url`, `data-movie-title`, `data-share-text` attributes — consumed by Task 4's `reels-share.js` (exact attribute names must match).

- [ ] **Step 1: Write the failing tests**

Add to `TestScreeningIndexMobile` in `flask_backend/tests/test_routes/test_screening.py`:

```python
    def test_share_button_is_present_with_deep_link_data(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Compartilhável",
                cinema_slug="capitolio",
                screening_date=date.today() + timedelta(days=1),
                screening_time="21:00",
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'data-function="share"' in html
        assert f'/?screening={screening_id}' in html
        assert 'data-movie-title="Filme Compartilhável"' in html
        assert "Capitólio" in html
```

Also add this assertion to the existing `test_shared_card_scrolls_to_its_card_on_load` test in `TestScreeningSharedLink` (it already asserts the script references the id — this step just makes it pass now that the id will exist).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -k "share_button_is_present or scrolls_to_its_card" -v`
Expected: FAIL — no share button or card `id` exists yet.

- [ ] **Step 3: Implement the markup**

In `flask_backend/templates/screening/_reels_card.html`, change line 1 from:

```html
<section class="reels-card">
```

to:

```html
<section class="reels-card" id="reels-card-{{ card.screening_id }}">
```

Then, inside `<div class="reels-actions">` (currently lines 36-46), add the share button after the existing want-to-watch button:

```html
<div class="reels-actions">
    <button type="button"
            class="reels-want-to-watch"
            data-function="want-to-watch"
            data-movie-id="{{ card.movie_id }}"
            data-wanted="{{ 'true' if card.wanted else 'false' }}"
            aria-pressed="{{ 'true' if card.wanted else 'false' }}"
            aria-label="{{ 'Remover dos meus filmes' if card.wanted else 'Adicionar aos meus filmes' }}">
        <span aria-hidden="true">{{ '★' if card.wanted else '☆' }}</span>
    </button>
    <button type="button"
            class="reels-share"
            data-function="share"
            data-share-url="{{ url_for('screening.index', screening=card.screening_id, _external=True) }}"
            data-movie-title="{{ card.movie_title }}"
            data-share-text="{{ card.cinema_name }} · {{ card.soonest_date.strftime('%d/%m') }}{% if card.soonest_time %} {{ card.soonest_time }}{% endif %}"
            aria-label="Compartilhar">
        <svg width="20"
             height="20"
             viewBox="0 0 24 24"
             fill="none"
             stroke="currentColor"
             stroke-width="2"
             stroke-linecap="round"
             stroke-linejoin="round"
             aria-hidden="true"
             focusable="false">
            <path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"></path>
            <polyline points="16 6 12 2 8 6"></polyline>
            <line x1="12" y1="2" x2="12" y2="15"></line>
        </svg>
    </button>
</div>
```

In `flask_backend/static/css/reels.css`, change the selectors at lines 313 and 331 (currently `.reels-want-to-watch { ... }` and `.reels-want-to-watch:active { ... }`) to also match the new button:

```css
.reels-want-to-watch,
.reels-share {
    width: 2.5rem;
    height: 2.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, 0.25);
    background: rgba(0, 0, 0, 0.35);
    backdrop-filter: blur(2px);
    color: #fff;
    font-size: 1.4rem;
    line-height: 1;
    padding: 0;
    cursor: pointer;
    transition: transform 0.15s ease;
}

.reels-want-to-watch:active,
.reels-share:active {
    transform: scale(0.9);
}
```

Leave `.reels-want-to-watch[data-wanted="true"]` (line 335) untouched — it's specific to the star toggle's filled state and must not apply to the share button.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -v`
Expected: all PASS, including `test_shared_card_scrolls_to_its_card_on_load` from Task 2.

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest flask_backend/tests`
Expected: all PASS.

- [ ] **Step 6: Lint and format**

Run:
```bash
uv run djlint flask_backend/templates/screening/_reels_card.html --lint --profile=jinja
uv run djlint --reformat flask_backend/templates/screening/_reels_card.html --format-css --format-js
uv run ruff check --fix && uv run ruff format
```
Expected: no errors after reformatting.

- [ ] **Step 7: Commit**

```bash
git add flask_backend/templates/screening/_reels_card.html flask_backend/static/css/reels.css flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: add share button markup to reels cards"
```

---

### Task 4: Share button behavior — Web Share API, clipboard fallback, analytics

**Files:**
- Create: `flask_backend/static/reels-share.js`
- Modify: `flask_backend/templates/base_reels.html`

**Interfaces:**
- Consumes: `button[data-function="share"]` with `data-share-url`, `data-movie-title`, `data-share-text` attributes (produced by Task 3). `window.goatcounter.count({...})` (existing global, same usage as `flask_backend/static/reels-want-to-watch.js:36-41`). Bootstrap's `bootstrap.Toast.getOrCreateInstance(toastEl).show()` (existing usage at `flask_backend/static/reels-want-to-watch.js:16`).
- Produces: nothing consumed by other tasks — this is the last piece of the feature.

- [ ] **Step 1: Add the toast markup to `base_reels.html`**

In `flask_backend/templates/base_reels.html`, right after the existing `#reels-wtw-toast` block (currently lines 54-64), add a second toast:

```html
{# djlint:off #}
<div id="reels-share-toast"
     class="toast reels-wtw-toast"
     role="status"
     aria-live="polite"
     aria-atomic="true"
     data-bs-autohide="true"
     data-bs-delay="3000">
    <div class="toast-body">Link copiado!</div>
</div>
{# djlint:on #}
```

(Reuses the `.reels-wtw-toast` CSS class for identical positioning/styling — it's a generic toast style despite the name, not want-to-watch-specific.)

- [ ] **Step 2: Write `reels-share.js`**

Create `flask_backend/static/reels-share.js`:

```js
function trackShare() {
    if (window.goatcounter && window.goatcounter.count) {
        window.goatcounter.count({
            path: "reels-share",
            title: "Shared movie card",
            event: true,
        });
    }
}

function showShareToast() {
    const toastEl = document.getElementById("reels-share-toast");
    if (!toastEl) return;
    bootstrap.Toast.getOrCreateInstance(toastEl).show();
}

document.addEventListener("click", (event) => {
    const button = event.target.closest('[data-function="share"]');
    if (!button) return;

    const shareData = {
        title: button.dataset.movieTitle,
        text: button.dataset.shareText,
        url: button.dataset.shareUrl,
    };

    if (navigator.share) {
        navigator.share(shareData).then(trackShare).catch(() => {});
        return;
    }

    navigator.clipboard.writeText(shareData.url).then(() => {
        trackShare();
        showShareToast();
    });
});
```

- [ ] **Step 3: Load the script in `base_reels.html`**

In `flask_backend/templates/base_reels.html`, add a new `<script>` tag right after the existing `reels-want-to-watch.js` line (currently line 126):

```html
<script src="{{ url_for('static', filename='reels-want-to-watch.js') }}"></script>
<script src="{{ url_for('static', filename='reels-share.js') }}"></script>
```

- [ ] **Step 4: Write a route test confirming the script and toast are wired in**

Add to `TestScreeningIndexMobile` in `flask_backend/tests/test_routes/test_screening.py`:

```python
    def test_share_script_and_toast_markup_are_present(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'src="/static/reels-share.js"' in html
        assert 'id="reels-share-toast"' in html
        assert "Link copiado!" in html
```

- [ ] **Step 5: Run the test to verify it fails, then passes**

Run: `pytest flask_backend/tests/test_routes/test_screening.py -k share_script_and_toast -v`
Expected: FAILs before Steps 1/3, PASSes after.

- [ ] **Step 6: Run the full backend test suite**

Run: `pytest flask_backend/tests`
Expected: all PASS.

- [ ] **Step 7: Manual verification (no automated JS test harness in this repo)**

Start the dev server (`flask --app flask_backend run --debug`), open the mobile reels feed in a real mobile browser (or Chrome DevTools device emulation) at `http://<your-lan-ip>:5000/`, and confirm:
- Tapping the share button on a card opens the native share sheet with the movie title, session text, and a `/?screening=<id>` link.
- On a desktop browser without Web Share support, tapping the button copies the link and shows the "Link copiado!" toast.
- Opening the shared link on mobile scrolls straight to that card; opening it on desktop redirects to `/movies/<slug>`.

State plainly in your summary that this step was (or wasn't) actually run in a browser — don't claim it works from reading the code alone.

- [ ] **Step 8: Lint and format**

Run:
```bash
uv run djlint flask_backend/templates/base_reels.html --lint --profile=jinja
uv run djlint --reformat flask_backend/templates/base_reels.html --format-css --format-js
uv run ruff check --fix && uv run ruff format
```
Expected: no errors after reformatting.

- [ ] **Step 9: Commit**

```bash
git add flask_backend/static/reels-share.js flask_backend/templates/base_reels.html flask_backend/tests/test_routes/test_screening.py
git commit -m "feat: wire up native share sheet and clipboard fallback for reels cards"
```

---

## Self-Review Notes

- **Spec coverage:** URL scheme/routing → Task 1. Button UI → Task 3. Client-side share behavior → Task 4. Scroll-to-card → Tasks 2+3 together. OG tags → Task 2. Analytics → Task 4. All spec sections have a corresponding task.
- **Placeholder scan:** no TBD/TODO; every step has literal code or an exact command.
- **Type/name consistency:** `shared_card` dict keys (`screening_id`, `movie_title`, `description`, `image`) match `build_reels_feed`'s existing card dict exactly (verified against `flask_backend/service/screening.py`). `data-function="share"`, `data-share-url`, `data-movie-title`, `data-share-text` are used identically in Task 3's markup and Task 4's JS. `_mobile_index(shared_screening=None)` signature matches its one call site in `index()`.
