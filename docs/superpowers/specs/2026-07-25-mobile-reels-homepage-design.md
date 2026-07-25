# Mobile reels-style homepage

## Problem

The current homepage (`screening.index`, `/`) lists today's screenings grouped by
cinema, in one long scrolling page. On mobile this requires a lot of scrolling
and effort to find a screening worth watching: there's a lot of vertical space
between screenings, and nothing helps the user immediately understand "this is
a catalog of movie screenings, browse it like a feed."

## Goal

On mobile, replace the list with an Instagram-reels-style feed: one screening
fills the screen at a time. Vertical scrolling snaps from one screening to the
next; horizontal swiping switches between a poster-centric view and a
"more information" view for that same screening. Images for upcoming cards are
preloaded so scrolling feels instant.

Desktop is unaffected — it keeps the current cinema-grouped, today-only list.

## Architecture

`screening.index` (`/`) branches on `User-Agent`:

- **Mobile UA** (regex match on common mobile device tokens, e.g.
  `Mobi|Android|iPhone|iPad`) → new query (see Data below) → new template
  (e.g. `screening/index_mobile.html`) extending a minimal base with no
  navbar/footer. A small floating menu button opens the existing off-canvas
  nav (About, Programação, Acervo, etc.) so site navigation stays reachable.
- **Everything else** → the existing code path, completely untouched.

This is a heuristic, not a true viewport check: a desktop browser resized to
phone width won't see the reels view, and an unusual mobile UA could fall
through to the desktop view. This trade-off was chosen deliberately over the
alternatives (see "Alternatives considered" below) because it fits the
project's existing server-rendered Jinja + vanilla-JS conventions (no build
pipeline, no new dependencies) and gives each device class the smallest,
fastest payload — directly serving the "feels instant" goal.

## Data

One card per `Screening` (i.e. per cinema run of a movie), for any screening
with at least one `ScreeningDate` in the next 7 days (today included, rolling
window — same horizon concept as the existing "next 7 days" framing, chosen
over reusing `/program`'s full-month scope to keep the feed focused on "what's
on soon").

Cards are ordered by each screening's own soonest upcoming date/time within
the window.

Each card carries:

- Poster image (or placeholder — see Edge cases), cinema badge (short name +
  existing per-cinema color), soonest upcoming time
- Movie short info: title, director(s), release year — already available on
  the `Movie`/`Director` models, no schema changes needed
- Full description (info-panel only, same content as today's list view)
- "Next dates": every `ScreeningDate` within the 7-day window for that
  **movie across all cinemas** currently screening it, deduped and sorted.
  Fetched as one batched query across all movie IDs present in the feed (not
  one query per card), to avoid N+1.

**Known consequence:** if the same movie plays at two cinemas, it produces two
separate cards (one per cinema run, each positioned by its own soonest date),
and both cards' info panels show the same cross-cinema "next dates" list.
This falls directly out of "one card per screening" + "aggregate dates across
cinemas," and is accepted as intentional rather than treated as a bug.

## Card UI

**Poster view (default).** Full-viewport-height card. Poster fills the
screen (`object-fit: cover`), with a bottom gradient overlay holding: movie
title, cinema badge, soonest showtime, and the short info line
(director · year). A subtle chevron/edge-peek on the right edge hints at the
horizontal swipe — this is the only discoverability affordance; there is no
separate onboarding tooltip.

**Info view (swipe right from poster).** Same card height. Contains the full
description and the "next dates" list (cinema label + date + time per row).
Swipe left returns to the poster.

## Interactions

- **Vertical scroll → next screening.** `scroll-snap-type: y mandatory` on
  the feed container; each card `scroll-snap-align: start`, full viewport
  height. Pure CSS, no JS required.
- **Horizontal swipe → poster ↔ info.** Same technique nested per card:
  `scroll-snap-type: x mandatory` with two child panels (poster, info). Pure
  CSS.
- **Preloading.** An `IntersectionObserver` watches upcoming cards and swaps
  their poster `<img>` from a `data-src` placeholder to the real `src` 2-3
  cards ahead of the current scroll position, so the image is already
  decoded by the time the user reaches it. Info-panel text needs no
  preloading — it's already in the DOM.

## Edge cases

- **No poster image.** Styled placeholder: cinema-colored background, movie
  title large and centered, same overlay info (badge, time, director/year) —
  keeps the poster-first visual rhythm even without real artwork.
- **Draft screenings (logged-in editors only).** "Rascunho" badge on the
  poster overlay, same as today. The existing publish/delete/edit actions
  move into the info panel as compact text links, kept out of the primary
  poster view since this is a low-frequency, editor-only path.
- **No screenings in the 7-day window.** A single full-height card with a
  friendly empty state, matching the tone of the current
  "Não há sessões hoje" message.
- **Day boundaries.** The first card belonging to a new day (e.g. tomorrow's
  earliest screening) carries a persistent thin date label at its top (e.g.
  "Amanhã, 26/07"), part of that card's normal layout — not a temporary
  toast. No other visual break — the feed stays one continuous vertical
  scroll.

## Out of scope

- Desktop/tablet layout — untouched
- The `/program` (Programação) and `/weekend` pages — untouched
- Any new admin tooling beyond relocating the existing publish/delete/edit
  links into the info panel
- Analytics/tracking of swipe interactions (can be added later if wanted)

## Alternatives considered

**Shared dataset, reshaped via CSS/JS at breakpoint.** Always compute the
7-day flat dataset; desktop re-derives its grouped-by-cinema/today view from
it client-side. Rejected: touches the working desktop query/rendering path
for no desktop-facing benefit, and risks shipping duplicate markup/images to
one device class or the other.

**Separate `/reels` route + client-side viewport redirect.** Dedicated
route/template, reached via a `window.innerWidth` check that redirects at
load time instead of server-side UA detection. More accurate (real viewport,
not device fingerprint), but the redirect adds a flicker/round-trip on first
load, working against the "feels instant" goal, plus added SEO/crawler
complexity.
