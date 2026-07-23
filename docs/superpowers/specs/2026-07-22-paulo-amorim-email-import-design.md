# Paulo Amorim newsletter email import (#251)

## Problem

The Cinemateca Paulo Amorim publishes next week's programming a few days in
advance via an email newsletter, before the website (`grade-semanal`) is
updated. The website also sometimes lags a few days behind at the start of a
new week. This means our current `scrapers/paulo_amorim.py` HTML scraper can
miss or delay picking up new sessions.

This feature adds a second, independent ingestion path for the same cinema:
reading the newsletter email and extracting screenings from it with an LLM,
the same strategy already used for CineBancários
(`scrapers/cinebancarios.py`, `CineBancariosExtractorLLM`). It is strictly
additive — the existing HTML scraper is not touched or replaced.

## Non-goals

- Replacing or modifying the existing `paulo_amorim.py` site scraper.
- Building a general-purpose inbound email pipeline for other cinemas.
- Real-time (webhook-based) email ingestion — daily polling is sufficient
  given the newsletter's cadence.

## Architecture overview

A new scraper module, `scrapers/paulo_amorim_email.py`, mirrors the shape of
the existing `CineBancarios` class: it connects to a dedicated Gmail mailbox
over IMAP (via the `imap-tools` library), pulls unread emails from the
newsletter's sender address, strips each to plain text, and hands the text to
a new LLM extractor class, `PauloAmorimEmailExtractorLLM`
(`scrapers/llms.py`), which follows the same `Movie`/`Movies` pydantic schema
already shared by `CineBancariosExtractorLLM` and `CineCincoExtractorLLM`.
The extractor returns the same JSON shape every other scraper produces, so
the output flows through the existing `import-json` → dedup pipeline
unchanged.

This is registered as a **new, separate room key**, `paulo-amorim-email`, in
`cinemaempoa.py`, distinct from the existing `paulo-amorim` site scraper key.
Both write screenings against the same `paulo-amorim` cinema slug in the
database. The existing dedupper (`flask --app flask_backend run-dedupper`)
already reconciles overlapping movies/screenings between sources by movie
slug, so no new merge logic is required — this is what makes the feature
"additive" without extra bookkeeping.

It gets its own scheduled GitHub Actions workflow,
`import-paulo-amorim-email.yml`, running **daily**, distinct from the site
scraper's every-12-hours cadence in `run-spiders.yml`, using the same
SSH-into-server-and-exec pattern as `import-cinebancarios.yml`.

## Components

**`scrapers/paulo_amorim_email.py`** — new `PauloAmorimEmail` class:

- `__init__`: reads mailbox credentials from `flask_backend.env_config`
  (new `PAULO_AMORIM_EMAIL_ADDRESS` / `PAULO_AMORIM_EMAIL_APP_PASSWORD`
  vars).
- `_fetch_unread_newsletter_emails()`: uses `imap-tools` to search unread
  messages from the known newsletter sender address.
- `_get_text_from_email(msg)`: strips the HTML body to plain text, reusing
  a BeautifulSoup-based approach like `CineBancarios._get_text_from_soup`.
- `_extract_features(text, email_date)`: calls
  `PauloAmorimEmailExtractorLLM`, passing the email's `Date` header for
  year/week context, the same way `pubDate` is passed today for
  CineBancários.
- `get_weekly_features_json()`: orchestrates fetch → extract → cache (via
  the existing `scrapers/llm_cache.py`) → mark the email **seen** only
  after successful processing → return a JSON list of movies.

Marking a message "seen" only on success means a failed run naturally
retries that email on the next scheduled run, instead of silently losing it.

**`scrapers/llms.py`** — new `PauloAmorimEmailExtractorLLM` class, same
shape as the existing extractor classes. Its system prompt is where the
real complexity lives: it must be given the newsletter's date range (e.g.
"23 a 29 de julho de 2026", parsed from the email body/subject), and
instructed to expand each film's `Sessões:` line into explicit
`YYYY-MM-DD HH:MM` entries — including:

- The global weekly note (e.g. "SEGUNDA-FEIRA NÃO HÁ SESSÕES").
- Per-film exclusions (e.g. "não haverá exibição no dia 26, domingo").
- Per-film day restrictions (e.g. "exibições nos dias 23 e 24 – quinta e
  sexta").
- Default case: no exception mentioned means the film plays at the stated
  time on every day of the week's range except the globally-excluded day.

Room name (Sala Paulo Amorim / Sala Eduardo Hirtz / Sala Norberto Lubisco)
folds into `general_info` alongside country/genre/year/duration, matching
how the existing site scraper already appends room info. Emails do not
contain per-film poster images, so `image_url` will typically be empty for
email-sourced movies; this is acceptable since the existing
`fetch-posters`/`poster-review` pipeline already backfills missing posters.

**`cinemaempoa.py`** — add `"paulo-amorim-email"` to `allowed_rooms`, wire
up the new class the same way other rooms are wired, writing to the same
`"paulo-amorim"` cinema slug.

**`flask_backend/env_config.py`** / **`example.env`** — add
`PAULO_AMORIM_EMAIL_ADDRESS` and `PAULO_AMORIM_EMAIL_APP_PASSWORD`.

**`.github/workflows/import-paulo-amorim-email.yml`** — new daily workflow,
structurally a copy of `import-cinebancarios.yml` with a different cron
schedule and room name.

**`pyproject.toml`** — add `imap-tools` as a dependency.

## Data flow

1. Daily workflow triggers → SSH into server → `docker exec ...  python
   cinemaempoa.py -r paulo-amorim-email > import.json` → `flask --app
   flask_backend import-json import.json`.
2. `PauloAmorimEmail.get_weekly_features_json()` connects via IMAP,
   searches for unread messages from the newsletter's known sender
   address.
3. If no unread newsletter email exists (already processed, or hasn't
   arrived yet), returns an empty list. The pipeline run finishes with a
   "warning" status (0 created) — the expected common case most days.
4. If unread email(s) exist: for each, extract text → hash it → check
   `llm_cache` → call Gemini if not cached → parse into the `Movie`/
   `Movies` schema → mark that email as seen.
5. Output JSON is written to `json/<date>.json` (matching the pattern the
   site scraper already uses) and printed to stdout for the `import-json`
   step.
6. `import-json` validates the `paulo-amorim` cinema slug exists, creates
   movies/screenings.
7. The existing `run-dedupper` command reconciles any movie that now
   exists twice — once from the site scraper, once from the email —
   merging screenings under whichever movie record is oldest.

### Edge cases

- LLM extraction fails (rate limit, malformed response): log the error,
  return `None`/empty, do **not** mark the email as seen, so it is
  retried on the next run — same behavior as existing extractors.
- Multiple unread newsletter emails at once (e.g. job didn't run for a
  few days): process all of them in one run, each independently cached
  and marked seen.
- Non-newsletter emails in the inbox (replies, spam): excluded by the
  sender-address search filter, never touched.

## Testing

`tests/scrapers/test_paulo_amorim_email.py`, following existing scraper
test conventions:

- Unit test `_get_text_from_email` against a saved fixture built from a
  real sample newsletter email (stripped of identifying details), kept as
  an HTML/text fixture file like other scraper tests use.
- Unit test the LLM prompt/extraction logic with mocked LLM responses,
  verifying date-range expansion (global Monday exclusion, per-film
  exceptions) against known expected output. This is the highest-risk part
  of the feature and gets the most direct coverage.
- Test `PauloAmorimEmail` with a mocked IMAP client, verifying:
  unread-only fetch, seen-flag only set after success, empty-inbox →
  empty list.

## Deployment

- `PAULO_AMORIM_EMAIL_ADDRESS` / `PAULO_AMORIM_EMAIL_APP_PASSWORD` are
  added to the production `.env` (and documented in `example.env`), not to
  GitHub Actions secrets — the scraper code runs inside the server's
  Docker container, not in the Actions runner, matching how
  `GEMINI_API_KEY` is handled today.
- Manual one-time setup (outside this codebase): create the Gmail
  account, enable 2FA, generate an app password, and subscribe that
  address to the Paulo Amorim newsletter.
