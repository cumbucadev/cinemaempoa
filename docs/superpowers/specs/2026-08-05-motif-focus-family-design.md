# Design: Standardize the "Focus" Motif Family

## Status

Design approved.

## Context

`flask_backend/service/motifs.py` (added in the Phase 1 motif detection work,
see `docs/superpowers/specs/2026-08-03-motif-detection-design.md`) currently
has three motifs that share the same underlying shape — "flag a category
with N+ currently-screening movies" — but with inconsistent naming and, in
one case, an inconsistent scope:

- `MultipleMoviesSameDirectorMotif` (`name = "multiple_movies_same_director"`)
  — groups currently-screening movies by director, across all cinemas.
- `CountryClusterMotif` (`name = "country_cluster"`) — groups
  currently-screening movies by production country, across all cinemas.
- `CinemaGenreFocusMotif` (`name = "cinema_genre_focus"`) — the odd one out:
  groups by **(cinema, genre)** pair and compares each cinema's
  current-month genre share against that same cinema's own historical
  baseline (a statistical multiplier check), instead of looking at genre
  distribution across all cinemas the way the other two look across all
  cinemas for their category.

This design brings `CinemaGenreFocusMotif` in line with the other two —
citywide scope, plain count threshold, no per-cinema or historical-baseline
comparison — and standardizes naming across all three as the "Focus" motif
family.

`DirectorReturnMotif` and `AnniversaryMotif` are out of scope: they detect a
different shape (gap-since-last-screening, age-since-release) and don't fit
this family.

## Renames

| Current class | New class | Current `name` | New `name` |
|---|---|---|---|
| `MultipleMoviesSameDirectorMotif` | `DirectorFocusMotif` | `multiple_movies_same_director` | `director_focus` |
| `CountryClusterMotif` | `CountryFocusMotif` | `country_cluster` | `country_focus` |
| `CinemaGenreFocusMotif` | `GenreFocusMotif` | `cinema_genre_focus` | `genre_focus` |

Constants renamed for the same consistency (no logic change to the two
motifs they belong to):

- `MULTIPLE_MOVIES_THRESHOLD` → `DIRECTOR_FOCUS_THRESHOLD` (still `2`)
- `COUNTRY_CLUSTER_THRESHOLD` → `COUNTRY_FOCUS_THRESHOLD` (still `2`)

Grep confirms these names/strings are only referenced inside
`flask_backend/service/motifs.py`, `motif_ranking.py`, and their three test
files (`test_motifs.py`, `test_motif_ranking.py`, `test_motif_commands.py`).
No CLI output contract, template, or route depends on the specific
`motif_name` string values — nothing observed anything is persisted — so
renaming is safe with no compatibility shim needed.

## `GenreFocusMotif` redesign

Drop the historical-share/multiplier statistics entirely and mirror
`CountryFocusMotif`'s structure exactly, with `Genre`/`HAS_GENRE` swapped in
for `Country`/`PRODUCED_IN`, no `Cinema` node, and the same open-ended
"currently screening" window (`sd.date >= today`, no draft screenings) the
other two motifs use instead of a calendar-month window:

```cypher
MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre), (m)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate)
WHERE sd.date >= $today AND s.draft = false
WITH g, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, collect(m.title) AS titles, collect(sd.date) AS dates
WHERE movie_count >= $threshold
RETURN g.id AS genre_id, g.name AS genre_name, movie_count, movie_ids, titles, dates
ORDER BY genre_name
```

New constant `GENRE_FOCUS_THRESHOLD = 2` (same value as
`DIRECTOR_FOCUS_THRESHOLD`/`COUNTRY_FOCUS_THRESHOLD`, confirmed with user —
even though genre counts are citywide sums and could plausibly need a higher
bar, `2` keeps the three motifs' thresholds uniform for this first version
and can be raised later if it proves too noisy in practice).

Other consequences of the simplification:

- Drops the `calendar` import, `CINEMA_GENRE_FOCUS_MULTIPLIER`,
  `CINEMA_GENRE_FOCUS_MIN_COUNT`, and the second (historical) query
  entirely — `GenreFocusMotif.detect()` becomes a single query, single pass,
  matching `CountryFocusMotif.detect()`'s shape line for line.
- `confidence` becomes `1.0` (pure count, like Director/Country Focus)
  instead of `0.7` — there's no longer a statistical judgment call being
  made, just a threshold.
- `metadata` drops `screening_count` and `cinema`, gains `movies` (list of
  titles) — matching Director/Country Focus's metadata shape exactly:
  `{"genre": genre_name, "movies": titles, "next_screening_date": min(dates)}`.
- `evidence.nodes` drops the `cinema_id`, becomes `[genre_id, *movie_ids]`;
  `evidence.edges` becomes `[(mid, genre_id, "HAS_GENRE") for mid in movie_ids]`
  (unchanged from before, since the old edges list never included the
  cinema node/edge to begin with).
- Headline/summary reworded from cinema-specific framing (e.g. `"{cinema}
  em foco: {genre}"`) to citywide framing (e.g. `"{genre} em destaque nos
  cinemas"` / `"{count} filmes de {genre} estão em cartaz atualmente."`),
  matching Country Focus's phrasing pattern.
- `version` bumps to `"2.0"` on `GenreFocusMotif` to reflect the behavior
  change (detection criteria, not just a rename). `DirectorFocusMotif` and
  `CountryFocusMotif` stay at `"1.0"` — renamed only, no logic change.

## Testing

- `test_motifs.py`: rename `TestMultipleMoviesSameDirectorMotif` →
  `TestDirectorFocusMotif`, `TestCountryClusterMotif` →
  `TestCountryFocusMotif`. Replace `TestCinemaGenreFocusMotif`'s
  historical-share fixtures with `TestGenreFocusMotif` built the same way as
  `TestCountryFocusMotif`: threshold-boundary case (exactly `2` vs. `1`
  currently-screening movies in a genre) and the no-match case. Drop the
  now-irrelevant "no historical precedent" and "matches historical share"
  cases.
- `test_motif_ranking.py`: update the `"multiple_movies_same_director"` and
  `"country_cluster"` string literals (lines 127, 201) to
  `"director_focus"`/`"country_focus"`.
- `test_motif_commands.py`: update the `"multiple_movies_same_director"`
  string literals (lines 62, 81) to `"director_focus"`.

## Non-goals

- No change to `DirectorReturnMotif` or `AnniversaryMotif`.
- No reintroduction of a per-cinema genre view — if that's wanted later
  (e.g. "what is this specific cinema known for"), it should be a distinctly
  named motif, not a variant of `GenreFocusMotif`.
- No config system for thresholds — they remain named constants, per the
  existing convention in this module.
