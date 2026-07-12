"""Runner CLI entry point.

Usage:
    python runner/main.py --rooms capitolio sala-redencao paulo-amorim \\
        --api-url https://cinemaempoa.com.br \\
        --api-token <token>
"""

import argparse
import logging
import os
import sys

import requests

from shared.schema import ScrappedResult

logger = logging.getLogger(__name__)

VALID_ROOMS = ["capitolio", "sala-redencao", "cinebancarios", "paulo-amorim"]

ROOM_CONFIG = {
    "capitolio": {
        "cls_path": ("runner.scrapers.capitolio", "Capitolio"),
        "url": "https://www.capitolio.org.br",
        "cinema": "Cinemateca Capitólio",
        "slug": "capitolio",
    },
    "sala-redencao": {
        "cls_path": ("runner.scrapers.sala_redencao", "SalaRedencao"),
        "url": "https://www.ufrgs.br/difusaocultural/salaredencao/",
        "cinema": "Sala Redenção",
        "slug": "sala-redencao",
    },
    "cinebancarios": {
        "cls_path": ("runner.scrapers.cinebancarios", "CineBancarios"),
        "url": "http://cinebancarios.blogspot.com",
        "cinema": "CineBancários",
        "slug": "cinebancarios",
    },
    "paulo-amorim": {
        "cls_path": ("runner.scrapers.paulo_amorim", "CinematecaPauloAmorim"),
        "url": "https://www.cinematecapauloamorim.com.br",
        "cinema": "Cinemateca Paulo Amorim",
        "slug": "paulo-amorim",
    },
}


def _load_scraper_class(module_name, class_name):
    import importlib
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def scrape_rooms(rooms):
    """Scrape the requested rooms and return a ScrappedResult-compatible list."""
    cinemas_json = []
    for room in rooms:
        config = ROOM_CONFIG[room]
        module_name, class_name = config["cls_path"]
        cls = _load_scraper_class(module_name, class_name)
        scraper = cls()
        logger.info("Scraping %s...", config["cinema"])
        features = scraper.get_daily_features_json()
        cinemas_json.append(
            {
                "url": config["url"],
                "cinema": config["cinema"],
                "slug": config["slug"],
                "features": features,
            }
        )
    return cinemas_json


def post_import(api_url, api_token, cinemas_json):
    """POST scraped data to /api/import. Returns created count."""
    url = f"{api_url.rstrip('/')}/api/import"
    response = requests.post(
        url,
        json=cinemas_json,
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("created", 0)


def fetch_missing_posters(api_url, api_token):
    """GET /api/screenings/missing-posters. Returns list of screening dicts."""
    url = f"{api_url.rstrip('/')}/api/screenings/missing-posters"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def patch_poster(api_url, api_token, screening_id, poster_url, source):
    """PATCH /api/screenings/{id}/poster."""
    url = f"{api_url.rstrip('/')}/api/screenings/{screening_id}/poster"
    response = requests.patch(
        url,
        json={"url": poster_url, "source": source},
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def find_poster(movie_title):
    """Try TMDB then IMDB. Returns (url, source) or (None, None)."""
    from runner.poster.tmdb import TMDBClient
    from runner.poster.imdb import IMDBScrapper
    from shared.schema import ScrappedFeature

    try:
        client = TMDBClient()
        url = client.get_poster_url(movie_title)
        if url:
            return url, "tmdb"
    except Exception as exc:
        logger.warning("TMDB failed for '%s': %s", movie_title, exc)

    try:
        scrapper = IMDBScrapper()
        feature = ScrappedFeature(
            poster=None,
            time=None,
            title=movie_title,
            original_title=None,
            price=None,
            director=False,
            classification=None,
            general_info=None,
            excerpt="",
            read_more=None,
        )
        url = scrapper.get_image(feature)
        if url:
            return url, "imdb"
    except Exception as exc:
        logger.warning("IMDB failed for '%s': %s", movie_title, exc)

    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Scrape cinema schedules and import them into the web app."
    )
    parser.add_argument(
        "--rooms",
        nargs="+",
        required=False,
        choices=VALID_ROOMS,
        metavar="ROOM",
        help=f"One or more rooms to scrape: {', '.join(VALID_ROOMS)} (required unless --poster-only)",
    )
    parser.add_argument(
        "--api-url",
        required=True,
        help="Base URL of the web app (e.g. https://cinemaempoa.com.br)",
    )
    parser.add_argument(
        "--api-token",
        default=None,
        help="Bearer token for the import API (falls back to IMPORT_API_TOKEN env var)",
    )
    parser.add_argument(
        "--skip-posters",
        action="store_true",
        default=False,
        help="Skip the poster-finding step after import",
    )
    parser.add_argument(
        "--poster-only",
        action="store_true",
        default=False,
        help="Skip scraping and import; only run the poster-finding step",
    )

    args = parser.parse_args()

    if not args.poster_only and not args.rooms:
        parser.error("--rooms is required unless --poster-only is set")

    api_token = args.api_token or os.environ.get("IMPORT_API_TOKEN")
    if not api_token:
        print(
            "Error: --api-token is required (or set IMPORT_API_TOKEN env var)",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.poster_only:
        # Step 1: Scrape
        logger.info("Scraping rooms: %s", args.rooms)
        cinemas_json = scrape_rooms(args.rooms)

        # Step 2: POST to /api/import
        logger.info("Importing to %s...", args.api_url)
        created = post_import(args.api_url, api_token, cinemas_json)
        print(f"Import complete: {created} screening(s) created/updated")

    if args.skip_posters:
        return

    # Step 3: Find missing posters
    logger.info("Fetching screenings without posters...")
    missing = fetch_missing_posters(args.api_url, api_token)
    if not missing:
        print("No screenings missing posters.")
        return

    print(f"{len(missing)} screening(s) need poster(s). Searching...")
    found = 0
    for item in missing:
        screening_id = item["id"]
        movie_title = item["movie_title"]
        poster_url, source = find_poster(movie_title)
        if poster_url is None:
            logger.info("No poster found for '%s'", movie_title)
            continue
        try:
            patch_poster(args.api_url, api_token, screening_id, poster_url, source)
            logger.info("Poster set for screening %d ('%s') via %s", screening_id, movie_title, source)
            found += 1
        except requests.HTTPError as exc:
            logger.warning("Failed to PATCH poster for screening %d: %s", screening_id, exc)

    print(f"Poster search complete: {found}/{len(missing)} poster(s) found")


if __name__ == "__main__":
    main()
