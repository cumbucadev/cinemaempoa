# Reels card share button

## Problem

The mobile reels feed (`screening/index_mobile.html`, `screening/favoritos.html`,
both built on the `screening/_reels_card.html` partial) lets visitors browse
movies Instagram-Reels/YouTube-Shorts style, but there's no way to share a
specific movie card to social media or messaging apps. Visitors who find
something they want to watch have no quick way to send it to a friend.

## Goals

- A share button on each reels card that opens the device's native share
  sheet (Web Share API) with a deep link to that exact card.
- The deep link, opened later or on another device, lands somewhere useful
  regardless of whether the feed still shows that screening or the visitor
  is on desktop.
- Shared links produce a rich preview (poster, title, description) in
  apps that render Open Graph tags (WhatsApp, Twitter/X, iMessage, etc.).
- Share taps are tracked in GoatCounter, consistent with the existing
  want-to-watch tracking.

## Non-goals

- Custom per-platform share icons/URLs (WhatsApp/Instagram/X buttons) — the
  native share sheet already surfaces whatever apps the user has.
- Sharing the favorites feed itself — shared links always resolve against
  the public main feed, never a visitor's personal favorites view.
- A desktop-specific rendering of the reels card — desktop visitors are
  redirected to the existing movie page instead.

## URL scheme & routing

Shared links point at the existing `/` route with a query param:

```
https://cinemaempoa.com.br/?screening=<screening_id>
```

`GET /` (`flask_backend/routes/screening.py::index`, and the `_mobile_index`
helper it delegates to for mobile user agents) gains this branching, applied
whenever `screening` is present and parses to an int:

1. Look up the screening via `get_screening_by_id(screening_id)`.
2. **Not found** (invalid/deleted id): ignore the param, render today's
   normal behavior (mobile feed or desktop list) unchanged.
3. **Found, but `movie.slug` is null**: ignore the param (same as not found)
   — this shouldn't happen in practice, but degrades safely if it does.
4. **Found, desktop user agent**: redirect (302) to
   `url_for("movie.show", slug=screening.movie.slug)`.
5. **Found, mobile user agent, screening present in the current 6-day
   `build_reels_feed` window**: render the mobile feed as usual, and pass
   the matching card through as `shared_card` (see below) so the template
   can scroll to it and emit per-movie OG tags.
6. **Found, mobile user agent, screening NOT in the current feed window**
   (link opened after the screening's dates passed): redirect (302) to
   `url_for("movie.show", slug=screening.movie.slug)`.

Desktop (case 4) and expired-link (case 6) share one fallback: redirect to
the movie's page.

## UI: the button

`_reels_card.html`'s `.reels-actions` column (currently just the ★
want-to-watch button) gains a second button, and the enclosing
`<section class="reels-card">` gains an id for scroll targeting:

```html
<section class="reels-card" id="reels-card-{{ card.screening_id }}">
  ...
  <div class="reels-actions">
      <button ... data-function="want-to-watch">...</button>
      <button type="button"
              class="reels-share"
              data-function="share"
              data-share-url="{{ url_for('screening.index', screening=card.screening_id, _external=True) }}"
              data-movie-title="{{ card.movie_title }}"
              data-share-text="{{ card.cinema_name }} · {{ card.soonest_date.strftime('%d/%m') }}{% if card.soonest_time %} {{ card.soonest_time }}{% endif %}"
              aria-label="Compartilhar">
          <svg aria-hidden="true" ...>...</svg>
      </button>
  </div>
</section>
```

`.reels-share` reuses `.reels-want-to-watch`'s circular sizing/background/
border from `reels.css` but is its own class (no `[data-wanted]` color
state). The icon is a small inline SVG share glyph rather than a unicode
character, for consistent rendering across browsers/OSes.

Because `_reels_card.html` is shared, this button appears on both the main
feed and `favoritos.html` automatically. Its `data-share-url` always points
at the main feed (`screening.index`), never at the favorites page.

## Client-side behavior

New `flask_backend/static/reels-share.js`, loaded in `base_reels.html`
alongside the existing reels scripts, following the same click-delegation
and GoatCounter pattern as `reels-want-to-watch.js`:

- On click of `[data-function="share"]`, build `{ title, text, url }` from
  the button's data attributes.
- If `navigator.share` exists, call it. A resolved promise fires a
  `reels-share` GoatCounter event. A rejected promise (including the user
  cancelling the share sheet) is swallowed silently — cancelling isn't an
  error and isn't tracked.
- If `navigator.share` doesn't exist (desktop browsers without Web Share
  support), fall back to `navigator.clipboard.writeText(url)`, fire the
  GoatCounter event, and show a small toast ("Link copiado!") using a new
  `#reels-share-toast` element following the same Bootstrap Toast pattern
  as the existing `#reels-wtw-toast`.

## Scroll-to-card on load

When the route resolves case 5 above, `index_mobile.html` receives
`shared_card` (the matching card dict) in addition to `cards`. A small
inline script (near the existing lazy-poster-loading script) does:

```js
{% if shared_card %}
document.getElementById("reels-card-{{ shared_card.screening_id }}")
    ?.scrollIntoView({ behavior: "instant", block: "start" });
{% endif %}
```

This runs before the lazy-poster `IntersectionObserver` registers, so the
target card's poster (already eagerly loaded if it's one of the first two
cards, otherwise lazy) loads correctly once scrolled into view.

## Open Graph tags for rich previews

`index_mobile.html`'s `meta_tags` block becomes conditional on
`shared_card`:

- **`shared_card` present**: `og:title` = movie title, `og:description` =
  movie description, `og:image` = card's poster image — mirroring the
  pattern already used in `blog/show.html`.
- **`shared_card` absent**: today's generic "Programação do dia" tags,
  unchanged.

## Testing

- Route tests: valid/invalid/expired `screening` param, on both mobile and
  desktop user agents, asserting the right render vs. redirect in each of
  the six cases above.
- Template rendering test: `shared_card` present vs. absent produces the
  expected OG tags and the scroll-to-card script block.
- No feasible automated test for `navigator.share`/clipboard fallback
  itself (browser API); covered by manual verification in a real mobile
  browser per this project's UI-testing convention.
