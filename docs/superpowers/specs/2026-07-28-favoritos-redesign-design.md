# Favoritos page redesign

## Problem

`/favoritos` (`flask_backend/routes/screening.py::favoritos`) currently reuses
the full-screen, one-card-at-a-time "reels" swipe format
(`screening/_reels_card.html` inside `base_reels.html`'s `.reels-feed`). That
format is built for browsing a chronological feed of screenings, not for
checking a personal list: there's no way to tell, without swiping through
every card, which of your favorited movies are actually playing right now
versus which ones have no upcoming sessions. The two kinds of movies look
identical.

## Goals

- Split favorited movies into two sections: **Em exibição** (has an upcoming
  screening) and **Todos os filmes** (does not) — mutually exclusive, a movie
  appears in exactly one.
- Make the distinction readable at a glance, not just by section header text.
- Make the promotion mechanic explicit: when a movie in "Todos os filmes"
  gets a new screening announced, it moves to "Em exibição". State this in
  the UI, don't leave it implied.
- Replace the swipe format with a scannable poster grid (Letterboxd-watchlist
  style), poster-forward with minimal text per tile.
- Removing a favorite (★) works directly from the grid — no navigation
  required.
- Tapping a poster reveals more detail (description, sessions, share,
  edit/error-report, admin publish/discard for drafts) inline, without
  leaving the page.
- **Look and feel like the same app** — reuse `/cinemas/<slug>`'s existing
  poster-wall pattern rather than inventing a new visual language (see
  below).

## Non-goals

- No changes to `movie/show.html` / `movie.show` (still not mobile/reels-
  ready, no want-to-watch or share affordance, mixes past/future dates) —
  centralizing on it is a separate future pass.
- No changes to the main reels feed (`screening/index_mobile.html`) or its
  swipe format — this only touches `favoritos.html`.
- No changes to `poster_tile` (`macros/poster_tile.html`) itself. It's a
  plain `<a>` link by design (used by `/cinemas/<slug>`'s two sections, both
  of which just navigate to `movie.show`). Favoritos needs different
  interactive semantics — expand-in-place plus a remove action that must
  *not* navigate — so it gets its own partial that reuses the macro's CSS
  classes (`.poster-tile`, `.poster-tile-img`, `.poster-tile-badge`,
  `.poster-tile-scrim`, `.poster-tile-title`) rather than the macro itself.
- No backend/data-shape changes. `build_favorites_feed`
  (`flask_backend/service/screening.py:234`) already tags every card with
  `no_sessions` (True = no upcoming date, the exact split this design needs)
  plus `wanted`, `next_dates`, `draft`, etc. Splitting into two sections is
  template-only.
- No auth changes — favorites remain the anonymous per-visitor cookie
  mechanism (`flask_backend/utils/visitor.py`), unrelated to `g.user`.

## Visual design: reuse the existing poster-wall pattern

`/cinemas/<slug>` (`cinema/show.html`) already solves the near-identical
problem of "currently showing vs. archive" for a single cinema's movies, with
`flask_backend/static/css/cinema.css` — its own header comment describes it
as a "poster-wall grid... letterboxd-style". Concretely, it already has:

- **`.section-eyebrow` / `.section-eyebrow-dot`** — small uppercase label
  with a hairline rule, plus an accent dot that pulses (respecting
  `prefers-reduced-motion`) for the "live" section ("Em cartaz"); the
  "archive" section ("Já passou por aqui") uses the eyebrow without the dot.
  This is exactly the "lit vs. unlit" signal this redesign needs — no new
  component required.
- **`.poster-grid`** — real CSS Grid, 3/4/5 responsive columns.
- **`.poster-tile` family** — aspect-ratio 2/3 poster, hover/touch scrim
  revealing the title, an optional corner badge, a first-letter placeholder
  for missing images, focus-visible ring in the page's accent color.
- **`--cinema-accent` / `--cinema-accent-text`** — a single accent color
  (set inline per page) driving all of the above, auto-lightened for the
  dark theme via `color-mix`.

Originally this redesign was drafted against the reels visual language
instead (dark photo-backdrop cards, a new display font, a bespoke
"dormant/lit" token system) — but that would leave two different visual
languages in the app for the same underlying idea ("what's showing now vs.
archive"), one on `/cinemas/<slug>` and a different one on `/favoritos`. This
version reuses the existing system instead, extending it only where
favoritos' needs genuinely differ (expand-in-place, a remove-favorite
control) rather than replacing it.

**Page template:** `favoritos.html` switches from `base_reels.html` to
`base.html` (matching `cinema/show.html`, `movie/show.html`) and loads
`cinema.css` instead of `reels.css`.

**Accent color:** favoritos has no single cinema to derive `--cinema-accent`
from (it aggregates across venues), so it sets one directly, reusing the
same amber already used elsewhere in the app to mean "favorited"
(`.reels-want-to-watch[data-wanted="true"]` in `reels.css`), via the same
inline-`<style>` mechanism `cinema/show.html` already uses per-cinema:

```html
<style>:root { --cinema-accent: #9c5b00; }</style>
```

(`cinema.css`'s existing `:root[data-bs-theme="dark"]` rule auto-lightens
this for dark-theme text/dot use, same as it does for any per-cinema color —
no favoritos-specific dark-mode override needed.)

## Copy

- "Em exibição" eyebrow: pulsing dot, as `.section-eyebrow` already renders
  for "Em cartaz" on the cinema page.
- "Todos os filmes" eyebrow: no dot — plain `.section-eyebrow` text, same as
  "Já passou por aqui".
- Todos os filmes subhead (shown whenever the section is non-empty): *"Sem
  sessões agora. Quando um filme volta a passar, ele sobe pra Em exibição."*
- No favorites at all: *"Você ainda não marcou nenhum filme. Toque na
  estrela em um filme para adicioná-lo aqui."*
- Favorites exist but none currently showing: Em exibição section shows
  *"Nenhum dos seus filmes está em cartaz agora."* instead of the grid (the
  Todos os filmes subhead below already explains what happens next).
- Todos os filmes empty (everything currently showing): section (eyebrow +
  subhead) omitted entirely — nothing to explain if there's nothing
  archived.

## Template/markup changes

Route (`screening.py::favoritos`) buckets `cards` from `build_favorites_feed`
by `no_sessions` before rendering:

```python
cards = build_favorites_feed(movie_ids, date.today(), user_logged_in)
em_exibicao = [c for c in cards if not c["no_sessions"]]
todos = sorted(
    (c for c in cards if c["no_sessions"]), key=lambda c: c["movie_title"]
)
return render_template(
    "screening/favoritos.html",
    em_exibicao=em_exibicao,
    todos=todos,
    canonical_base_url=CANONICAL_BASE_URL,
)
```

`em_exibicao` keeps `build_favorites_feed`'s existing soonest-date sort;
`todos` is sorted alphabetically — recency doesn't mean much for an archive
list, alphabetical is easier to scan. `canonical_base_url` (already passed
today, `flask_backend/routes/screening.py:68`) is preserved unchanged — the
share button below still needs it.

`favoritos.html`:

```html
{% extends "base.html" %}
{% block meta_tags %}
    <meta name="description" content="Filmes que você marcou como &quot;quero assistir&quot; no cinemaempoa.">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/cinema.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/favoritos.css') }}">
    {# djlint:off #}
    <style>:root { --cinema-accent: #9c5b00; }</style>
    {# djlint:on #}
{% endblock meta_tags %}
{% block title %}Meus Filmes{% endblock title %}
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
  <div id="reels-wtw-toast" class="toast favorites-toast" role="status" aria-live="polite" aria-atomic="true" data-bs-autohide="true" data-bs-delay="3000">
    <div class="toast-body">Filme adicionado de volta!</div>
  </div>
  <div id="reels-share-toast" class="toast favorites-toast" role="status" aria-live="polite" aria-atomic="true" data-bs-autohide="true" data-bs-delay="3000">
    <div class="toast-body">Link copiado!</div>
  </div>
  <script src="{{ url_for('static', filename='reels-want-to-watch.js') }}"></script>
  <script src="{{ url_for('static', filename='reels-share.js') }}"></script>
  <script src="{{ url_for('static', filename='favoritos.js') }}"></script>
{% endblock content %}
```

`base.html` doesn't load `reels-want-to-watch.js` / `reels-share.js` (only
`base_reels.html` does) since no other `base.html` page has ever used
want-to-watch/share controls before now — favoritos includes them itself
rather than adding them to `base.html` for everyone. Both scripts already
no-op gracefully if their toast element is missing
(`reels-want-to-watch.js:14`, `reels-share.js:12`); the toast markup above
keeps the same `id`s those scripts look up (so they still fire) but a new
`.favorites-toast` class instead of `base_reels.html`'s `.reels-wtw-toast`
(see the CSS section below for why), and the add-toast copy drops "Veja em
Meus Filmes ☰" since you're already on that page.

New partial `screening/_favorites_tile.html` — a `<details>` (for
expand-in-place) whose `<summary>` reuses the `poster_tile` macro's CSS
classes directly (same visual tile, different tag/interactivity):

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

Note `publish`/`delete` reuse the same `data-function` markers as elsewhere,
but their document-level listeners currently live inline in
`base_reels.html` (`base_reels.html:117-142`), which favoritos no longer
extends. `favoritos.js` (below) picks up that same handling for this page.

## New CSS: `flask_backend/static/css/favoritos.css`

Small, additive to `cinema.css` — everything reusable already lives there:

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

(`.favorites-tile-share` reuses default Bootstrap button/badge styling — no
new rule needed, consistent with how `movie/show.html`'s accordion and
`cinema/show.html`'s header use plain Bootstrap components rather than
bespoke CSS.)

## New JS: `flask_backend/static/favoritos.js`

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

The publish/delete blocks are copied as-is from `base_reels.html:117-142`
(same behavior, same endpoints) since this page no longer extends that
template. `preventDefault()` (not `stopPropagation()`) is what makes the star
safe to click inside `<summary>`: it suppresses the browser's native toggle
at the default-action step, which runs after all bubbling listeners
regardless of registration order — so `reels-want-to-watch.js`'s own
document-level click handler (`reels-want-to-watch.js:19`) still fires
normally and isn't touched by this change.

## Testing

- Route test: `favoritos()` splits cards into `em_exibicao`
  (`no_sessions=False`) and `todos` (`no_sessions=True`, alphabetically
  sorted by title), for both logged-in and anonymous visitors.
- Template rendering tests: empty-favorites message when both lists are
  empty; "nenhum filme em cartaz" message when only `em_exibicao` is empty;
  "Todos os filmes" section omitted entirely when `todos` is empty; tile
  markup renders the date badge only for `em_exibicao` cards.
- No feasible automated test for the `<details>`-driven expand/collapse or
  the star-removal `MutationObserver` (browser behavior); covered by manual
  verification, consistent with this project's existing convention for
  client-side interaction (see the reels-share spec's Testing section).
