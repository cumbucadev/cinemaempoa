"""Pipeline that enriches movies with director and genre metadata from TMDB.

Usage (via CLI):
    flask fetch-movie-metadata          # process all movies missing metadata
    flask fetch-movie-metadata --limit 10   # process at most 10
    flask fetch-movie-metadata --dry-run    # only list what would be processed
"""

import logging
from dataclasses import dataclass
from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import MOVIE_METADATA_SOURCES
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.repository.genres import (
    get_or_create_by_tmdb_id as get_or_create_genre,
)
from flask_backend.repository.movie_metadata_fetch_attempts import (
    create as create_attempt,
    get_next_source,
    get_movies_without_metadata,
)
from flask_backend.service.tmdb import TMDBClient

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Summary returned after a pipeline run."""

    processed: int = 0
    metadata_found: int = 0
    metadata_not_found: int = 0
    errors: int = 0
    skipped_all_sources_tried: int = 0


def _try_tmdb(movie_title: str) -> Optional[dict]:
    """Attempt to find movie metadata using the TMDB API.

    Returns a dict with "genres" and "directors" on success, None if the
    movie can't be found on TMDB. Raises on network / API errors so the
    caller can record them.
    """
    client = TMDBClient()
    search_result = client.search_movie(movie_title)
    if search_result is None:
        return None
    return client.get_movie_details(search_result["id"])


# Maps source name -> callable that receives (movie_title, **kwargs) and
# returns a {"genres": [...], "directors": [...]} dict or None.
_SOURCE_HANDLERS = {
    "tmdb": lambda title, **_kw: _try_tmdb(title),
}


def run_pipeline(limit: Optional[int] = None, dry_run: bool = False) -> PipelineResult:
    """Main entry point for the movie metadata pipeline.

    For each movie without a director:
    1. Determine the next untried source (following MOVIE_METADATA_SOURCES order).
    2. Attempt to fetch metadata from that source.
    3. Record the attempt (success / not_found / error).
    4. If successful, upsert and attach genres/directors to the movie.

    Args:
        limit: Maximum number of movies to process. None = all.
        dry_run: If True, only report what would be done without making requests.

    Returns:
        A PipelineResult summarising the run.
    """
    result = PipelineResult()
    movies = get_movies_without_metadata()

    if limit is not None:
        movies = movies[:limit]

    for movie in movies:
        next_source = get_next_source(movie.id)

        if next_source is None:
            result.skipped_all_sources_tried += 1
            logger.debug(
                "Filme %d ('%s'): todas as fontes já tentadas – requer revisão manual",
                movie.id,
                movie.title,
            )
            continue

        if dry_run:
            logger.info(
                "[dry-run] Filme %d ('%s'): tentaria fonte '%s'",
                movie.id,
                movie.title,
                next_source,
            )
            result.processed += 1
            continue

        handler = _SOURCE_HANDLERS.get(next_source)
        if handler is None:
            logger.error("Fonte '%s' não possui handler implementado", next_source)
            result.errors += 1
            continue

        try:
            details = handler(movie.title)
        except Exception as exc:
            logger.warning(
                "Filme %d ('%s') – erro na fonte '%s': %s",
                movie.id,
                movie.title,
                next_source,
                exc,
            )
            create_attempt(
                movie_id=movie.id,
                source=next_source,
                status="error",
                error_message=str(exc)[:500],
            )
            result.errors += 1
            result.processed += 1
            continue

        if details is None:
            logger.info(
                "Filme %d ('%s') – fonte '%s': não encontrado",
                movie.id,
                movie.title,
                next_source,
            )
            create_attempt(
                movie_id=movie.id,
                source=next_source,
                status="not_found",
            )
            result.metadata_not_found += 1
            result.processed += 1
            continue

        for d in details.get("directors", []):
            director = get_or_create_director(d["id"], d["name"])
            if director not in movie.directors:
                movie.directors.append(director)

        for g in details.get("genres", []):
            genre = get_or_create_genre(g["id"], g["name"])
            if genre not in movie.genres:
                movie.genres.append(genre)

        db_session.add(movie)
        db_session.commit()

        logger.info(
            "Filme %d ('%s') – metadados salvos via '%s'",
            movie.id,
            movie.title,
            next_source,
        )
        create_attempt(
            movie_id=movie.id,
            source=next_source,
            status="success",
        )
        result.metadata_found += 1
        result.processed += 1

    return result


def get_manual_review_summary() -> list[dict]:
    """Return a summary of movies that need manual metadata review.

    Each dict contains movie_id, movie_title, and the list of sources
    already attempted.
    """
    from flask_backend.repository.movie_metadata_fetch_attempts import (
        get_attempted_sources,
        get_movies_needing_manual_review,
    )

    movies = get_movies_needing_manual_review()
    summary = []
    for movie in movies:
        attempted = get_attempted_sources(movie.id)
        summary.append(
            {
                "movie_id": movie.id,
                "movie_title": movie.title,
                "sources_attempted": sorted(attempted),
                "total_sources": len(MOVIE_METADATA_SOURCES),
            }
        )
    return summary
