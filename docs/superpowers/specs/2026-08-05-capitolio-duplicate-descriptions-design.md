# Capitólio duplicate/missing description fields — design

GitHub issue: #222 — "Descrições duplicadas em filmes do capitólio"

## Problem

Screening descriptions built from Capitólio scrapes show duplicated synopsis
text, and sometimes literal `"Não informado"` strings, e.g.
[Ninotchka](https://cinemaempoa.com.br/movies/ninotchka?screening=1215):

```
Não informado
Não informado

Em Paris, a comissária soviética Nina Ivanovna Yakushova (Greta Garbo)
chega encarregada de uma missão oficial [...]
Em Paris, a comissária soviética Nina Ivanovna Yakushova (Greta Garbo)
chega encarregada de uma missão oficial [...]
```

## Root cause

`Screening.description` is built in
`flask_backend/service/screening.py::import_scrapped_results` by
concatenating, in order: `original_title`, `price`, `director`,
`classification`, `general_info`, `excerpt` from each scraped
`ScrappedFeature`. These are the only consumers of these five fields
anywhere in the codebase for scraped features (confirmed by search) — they
exist purely to be concatenated into one free-text description. (`Movie.
original_title`, seen elsewhere in the codebase, is an unrelated DB column
filled later by the TMDB metadata pipeline.)

`scrapers/capitolio.py` used to derive all five fields from a single
`.movie-text` element that bundled director, classification, origin/
year/duration, and synopsis into one text blob, split heuristically by
line prefix (`"Direção"`, `"Classificação"`) and separator characters
(`|`, `(`, `R$`) in `.movie-subtitle`.

Capitólio's site has since restructured its markup: metadata that used to
share `.movie-text` with the synopsis now lives in a separate
`.movie-director` element, and `.movie-text` is now a synopsis-only `<p>`.
The scraper still queries `.movie-text` for *both* purposes:

```python
movie_director = movie.css.select_one(".movie-info .movie-text").get_text()
# ...line-by-line parsing for Direção:/Classificação:, looking in the
# wrong (synopsis) element — never matches, so general_info absorbs the
# entire synopsis...
movie_text = movie.css.select_one(".movie-info .movie-text")
feature_film["excerpt"] = movie_text.get_text()
# ...same synopsis, read again, verbatim.
```

This causes three problems:
1. `general_info` and `excerpt` both end up holding the same synopsis text
   → duplication in the final description.
2. `director` and `classification` are never populated at all anymore,
   since the scraper never reads `.movie-director`.
3. Separately, `original_title`/`price` (from `.movie-subtitle`) fall back
   to the literal string `"Não informado"` whenever the subtitle text
   doesn't contain `|` or `(` — which happens for non-commercial sessions
   Capitólio labels e.g. `"That Cold Day in the Park - Entrada franca"`
   (free admission, no price to parse).

## Design

Since `original_title`/`price`/`director`/`classification`/`general_info`/
`excerpt` are only ever concatenated into one description string, stop
classifying Capitólio's text into those specific fields. Capture two raw
text blobs instead, matching the site's current two content elements:

- `general_info` = `.movie-subtitle` text, followed by `.movie-director`
  text, whitespace-normalized (strip each line, drop blank lines, join
  with `\n`) — kept verbatim, whatever Capitólio wrote (price, "Entrada
  franca", origin/year/duration, `Direção:`, `Classificação:`, language,
  etc.), no attempt to split it further.
- `excerpt` = `.movie-text` text (now correctly synopsis-only), read once.
- `original_title`, `price`, `director`, `classification` are no longer
  set by `capitolio.py` (left `None`). These are already `Optional` on
  `ScrappedFeature`, and `screening.py`'s concatenation already skips
  falsy fields, so this is a no-op change to that shared code path.

This removes the `Direção:`/`Classificação:` prefix matching, the
`|`/`(`/`R$` regex heuristics on `.movie-subtitle`, and the double read of
`.movie-text` — replaced by three direct `get_text()` calls
(`.movie-subtitle`, `.movie-director`, `.movie-text`). No more
`"Não informado"` filler text; no more duplicated synopsis; robust to
whatever copy Capitólio actually publishes, since nothing is assumed about
its internal structure beyond "some text describing the film."

### Data flow (after)

```
.movie-subtitle  ─┐
                   ├─► general_info (raw, newline-joined)
.movie-director  ─┘

.movie-text ───────► excerpt (raw synopsis)
```

`screening.py::import_scrapped_results` is unchanged; it already skips
falsy fields, so `original_title`/`price`/`director`/`classification`
being `None` for Capitólio simply means those lines aren't added to the
description — `general_info` and `excerpt` alone now carry everything.

## Scope

Only `scrapers/capitolio.py` and its tests change. Other cinema scrapers
(`paulo_amorim.py`, `sala_redencao.py`, `cinebancarios.py`, `cine_cinco.
py`) are not touched — issue #222 is specific to Capitólio, and each
site's markup/heuristics differ enough that this isn't a drop-in change
elsewhere. Applying the same simplification to other scrapers can be a
follow-up if it proves valuable there too.

## Testing

- Update `tests/files/files_capitolio/*.html` fixtures to match the live
  site's current markup: separate `.movie-subtitle`, `.movie-director`,
  and `.movie-text` (`<p>`) elements, instead of one combined
  `.movie-text` blob.
- Update `tests/scrapers/test_capitolio.py`:
  - Replace assertions on `feature["director"]` / `feature["price"]` /
    `feature["original_title"]` with assertions on `feature["general_info"]`
    and `feature["excerpt"]`, confirming no duplication between them, and
    that `director`/`classification`/`original_title`/`price` keys are
    never set on the feature dict at all (`capitolio.py` simply stops
    assigning them; `ScrappedFeature.from_jsonable`'s `.get(..., None)`
    already treats a missing key as `None`, so this needs no dataclass
    change).
  - Add a fixture case for a free/"Entrada franca" session (no parseable
    price) to confirm the subtitle text passes through verbatim into
    `general_info` with no `"Não informado"` fallback.
