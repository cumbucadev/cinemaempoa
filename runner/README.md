# runner/

Self-contained Python package for scraping cinema schedules and finding movie posters. No Flask or SQLAlchemy dependency — only needs `requirements.runner.txt`.

## Setup

    pip install -r requirements.runner.txt

## Environment Variables

| Variable | Description |
|---|---|
| `IMPORT_API_TOKEN` | Bearer token for the web app API (alternative to `--api-token` flag) |
| `TMDB_API_TOKEN` | Read Access Token from https://www.themoviedb.org/settings/api |
| `GEMINI_API_KEY` | Google Gemini API key (used by CineBancários scraper) |
| `DEEPSEEK_API_KEY` | DeepSeek API key (optional second LLM for CineBancários cross-validation) |

## Usage

### Scrape and import

Scrape one or more cinema rooms and POST the results to the web app:

    python runner/main.py \
        --rooms capitolio sala-redencao paulo-amorim \
        --api-url https://cinemaempoa.com.br \
        --api-token <IMPORT_API_TOKEN>

Available rooms: `capitolio`, `sala-redencao`, `cinebancarios`, `paulo-amorim`

### Scrape only (no poster search)

    python runner/main.py \
        --rooms capitolio \
        --api-url https://cinemaempoa.com.br \
        --api-token <IMPORT_API_TOKEN> \
        --skip-posters

### Poster search only

Find and update posters for existing screenings without rescaping:

    python runner/main.py \
        --poster-only \
        --api-url https://cinemaempoa.com.br \
        --api-token <IMPORT_API_TOKEN>

### All options

    python runner/main.py --help

## Package Structure

```
runner/
  main.py              # CLI entry point
  scrapers/
    capitolio.py       # Cinemateca Capitólio scraper
    cinebancarios.py   # CineBancários scraper (uses LLM)
    paulo_amorim.py    # Cinemateca Paulo Amorim scraper
    sala_redencao.py   # Sala Redenção scraper
    llms.py            # LLM wrapper for CineBancários extraction
  poster/
    tmdb.py            # TMDB API client
    imdb.py            # IMDB scraper
```

## How It Works

1. Scrapers collect features (movies) from each cinema's website
2. Scraped data is POSTed to `POST /api/import` on the web app
3. The runner calls `GET /api/screenings/missing-posters` to find screenings without images
4. For each, it tries TMDB first, then IMDB
5. Found poster URLs are sent via `PATCH /api/screenings/{id}/poster`
