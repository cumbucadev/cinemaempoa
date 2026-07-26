# "Want to watch" button — design

Date: 2026-07-26

## Problem

Visitors browsing the reels-styled mobile homepage (mostly arriving from
Instagram links) have no way to mark a movie as something they want to see
later. We want a quick, low-friction toggle (tap a star) with instant
feedback, plus a page to review everything they've marked.

## Scope

This spec covers the MVP: the toggle button, same-browser persistence via an
anonymous visitor identity, and a page to view marked movies.

Explicitly out of scope, deferred to a follow-up spec once this MVP sees
real usage:

- Cross-device / cross-browser recovery (email or alternatives to it)
- Any "you'll lose this, leave your email" nudge before navigating away
- Desktop card layout support (this spec is reels-mobile only)
- Notifications or reminders about upcoming sessions for marked movies

## Why not solved by client-side storage alone

Instagram's in-app browser runs in a context that doesn't reliably share
`localStorage` with the visitor's regular mobile browser, and the exact
behavior varies by platform and isn't something we control. Storing marks
only in `localStorage` would silently lose data whenever a visitor moves
between Instagram's webview and Safari/Chrome — with no visibility into how
often that happens. Server-side storage keyed to a cookie-borne anonymous
identity survives at least "same browser, revisit later," and additionally
gives us aggregate data (which movies people actually want) that pure
client-side storage never could.

Cross-browser/cross-device identity (the deeper version of this problem) is
out of scope for this spec — see "Scope" above.

## Data model

New table, no new `Visitor` entity — `visitor_id` is an opaque, unauthenticated
UUID string used purely as a partition key:

```python
class WantToWatch(Base):
    __tablename__ = "want_to_watch"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    visitor_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (UniqueConstraint("movie_id", "visitor_id"),)

    movie: Mapped["Movie"] = relationship()
```

A mark attaches to the **Movie**, not a specific Screening: the same movie
playing at a different cinema, or resurfacing after this pick's screening
dates pass, still shows as marked. This matches user intent ("I want to
watch this film") better than a specific showtime, and avoids orphaned marks
once a screening's dates pass.

## Visitor identity

- A dedicated `visitor_id` cookie, **separate from Flask's login `session`
  cookie**. `flask_backend/routes/auth.py`'s `login()` and `logout()` both
  call `session.clear()` — if `visitor_id` lived inside that session object,
  logging in or out on the same browser would silently wipe a visitor's
  picks. A separate cookie avoids this collision entirely; an admin who is
  also a regular visitor keeps their picks continuously across login/logout.
- Value: `uuid4()` hex string. `httponly=True`, `samesite="Lax"`.
- `max_age` matches the existing `SESSION_LIFETIME_DAYS` env setting
  (currently 1 year), for consistency with the admin cookie's lifetime.
- Not signed/encrypted. Worst case of tampering is spoofing another random
  visitor's want-to-watch list — anonymous, non-sensitive, low-stakes. Keeps
  the implementation trivial (`request.cookies.get` /
  `response.set_cookie`, no `itsdangerous` needed).
- **Lazily created**: only set on the first `POST` to the toggle endpoint,
  never on a plain page view. Visitors who never tap the button get no
  extra cookie. Reading it for card annotation (homepage, `/favoritos`) is
  read-only and never creates it.

## Backend API

**Repository** — `flask_backend/repository/want_to_watch.py`, following the
existing repository module pattern:

- `toggle(movie_id: int, visitor_id: str) -> bool` — inserts or deletes the
  `(movie_id, visitor_id)` row (delete-if-exists-else-insert); returns the
  new state (`True` = now marked, `False` = now unmarked). Idempotent per
  call, so a request race from a double-tap can't create duplicate rows.
- `get_movie_ids_for_visitor(visitor_id: str) -> set[int]` — used to
  annotate homepage cards and to build `/favoritos`.

**Routes** — added to `flask_backend/routes/screening.py` (movie-id-based
routes already live alongside screening ones there; revisit only if this
makes the file unwieldy):

- `POST /movie/<int:movie_id>/want-to-watch` — toggles the mark for the
  current visitor, creating the `visitor_id` cookie if absent. Returns
  `{"wanted": true|false}` as JSON. No login required. 404s on an invalid
  `movie_id`.
- `GET /favoritos` — renders the visitor's full marked-movie list.

**`build_reels_feed` change:** add an optional `wanted_movie_ids: set[int] |
None` param; when given, each card gets a `card["wanted"]` bool. The
homepage passes the current visitor's set (empty set if no cookie yet).

**`/favoritos` feed construction** (distinct from the homepage's, since a
marked movie with no *current* screening still needs to render — see next
section):

1. Get the visitor's marked movie ID set via
   `get_movie_ids_for_visitor`.
2. Query upcoming screenings for those movie IDs with no fixed 7-day cap
   (this is a personal list, not a "what's on this week" feed) — for movies
   with an upcoming session, build the card the same way the homepage does.
3. For any marked movie ID with zero upcoming screenings, look up its most
   recent past `Screening` row (ordered by `created_at`) and build a card
   from that instead — see "Stale picks" below.

## Stale picks (marked movie no longer showing)

A marked movie with no upcoming screening still shows on `/favoritos` — it
never silently disappears. Its card is built from the movie's **most recent
past `Screening` row** (a `Movie` row only ever exists because some
`Screening` created it, so there's always at least one to fall back to):
same poster, title, cinema, description as that last known screening, with
the dates/"next sessions" section replaced by a short note (e.g. "Não há
sessões previstas no momento") instead of a session list.

## Frontend / UX

- **Icon:** star — outline when unmarked, filled when marked. Positioned in
  the top-right corner of the poster-panel overlay (the first panel,
  visible without swiping — where users spend most of their scrolling
  time), next to but not overlapping the cinema badge.
- **Interaction:** optimistic UI. Tapping flips the icon immediately
  (pop/bounce micro-animation, no toast/snackbar — quiet feedback only),
  then fires `POST /movie/<id>/want-to-watch` in the background. On a
  failed/non-OK response, revert the icon and log to console; no user-facing
  error UI. The button is disabled for the duration of an in-flight request
  to prevent double-tap races.
- **Accessibility:** a real `<button type="button">` (not a link/anchor).
  `aria-label` toggles between "Adicionar aos meus filmes" / "Remover dos
  meus filmes"; `aria-pressed` reflects state.
- **Initial state on load:** the server renders `card.wanted` into each
  card's HTML directly (via a read-only `visitor_id` cookie read on the
  homepage/`/favoritos` request), so the star shows correctly filled with no
  client-side round trip needed on page load.
- **Nav:** add a "Meus Filmes" entry to the offcanvas menu in
  `base_reels.html`, linking to `/favoritos`.

## Error handling & known limitations

- `POST /movie/<id>/want-to-watch` 404s on an invalid `movie_id`.
- No cookie support (rare — e.g. an in-app browser in an aggressive privacy
  mode): the tap still animates optimistically, but the mark won't survive
  a reload — each visit behaves like a first-time visitor. This is a known
  MVP limitation, not solved here; it's the exact cross-context gap the
  deferred email/recovery follow-up spec exists to address.
- Rapid double-taps: client disables the button mid-request; the repository
  toggle is idempotent per call regardless, so no duplicate rows even if a
  race slips through.

## Testing

- Repository: toggle creates/removes rows correctly, a second toggle
  reverses the first, no duplicate rows (unique constraint holds).
- Routes: first toggle sets the `visitor_id` cookie; a subsequent request
  reusing that cookie returns the correct state; `/favoritos` renders
  marked movies with upcoming sessions, marked movies via the stale-pick
  fallback, and the empty state when no cookie/marks exist.
- `build_reels_feed`: cards carry the correct `wanted` flag for a given
  visitor set.
