"""Client for The Movie Database (TMDB) API.

Docs:
    - https://developer.themoviedb.org/reference/search-movie
    - https://developer.themoviedb.org/docs/image-basics
"""

import logging
from typing import Optional

import requests

from flask_backend.env_config import TMDB_API_TOKEN

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
TMDB_API_BASE_URL = "https://api.themoviedb.org/3"

# Available poster sizes: w92, w154, w185, w342, w500, w780, original
DEFAULT_POSTER_SIZE = "w500"


class TMDBClient:
    """Searches TMDB for movie posters using the public API."""

    def __init__(self, api_token: Optional[str] = None):
        token = api_token or TMDB_API_TOKEN
        if token is None:
            raise ValueError(
                "TMDB_API_TOKEN não configurado. "
                "Obtenha um em https://www.themoviedb.org/settings/api"
            )
        self.headers = {
            "Authorization": f"Bearer {token}",
            "accept": "application/json",
        }

    def search_movie(self, title: str, language: str = "pt-BR") -> Optional[dict]:
        """Search TMDB for a movie by title and return the best match.

        Tries pt-BR first; if no results are found, retries with en-US.

        Returns the first result dict or None if nothing is found.
        """
        for lang in [language, "en-US"]:
            url = f"{TMDB_API_BASE_URL}/search/movie"
            params = {"query": title, "language": lang}
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=10)
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.warning("TMDB search failed for '%s' (lang=%s): %s", title, lang, exc)
                raise

            data = response.json()
            results = data.get("results", [])
            if results:
                return results[0]

        return None

    def get_poster_url(
        self, title: str, size: str = DEFAULT_POSTER_SIZE
    ) -> Optional[str]:
        """Search for a movie poster on TMDB by title.

        Returns the full poster image URL, or None if no poster is found.
        """
        movie = self.search_movie(title)
        if movie is None:
            logger.info("TMDB: nenhum resultado para '%s'", title)
            return None

        poster_path = movie.get("poster_path")
        if not poster_path:
            logger.info(
                "TMDB: filme encontrado mas sem poster – '%s' (id=%s)",
                title,
                movie.get("id"),
            )
            return None

        return f"{TMDB_IMAGE_BASE_URL}/{size}{poster_path}"
