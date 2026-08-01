"""Pipeline that enriches movies with metadata from TMDB (director, genres,
original title, release year, original language, country of origin).

Usage (via CLI):
    flask fetch-movie-metadata          # process all movies missing metadata
    flask fetch-movie-metadata --limit 10   # process at most 10
    flask fetch-movie-metadata --dry-run    # only list what would be processed
"""

import logging
from dataclasses import dataclass
from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository.collections import (
    get_or_create_by_tmdb_id as get_or_create_collection,
)
from flask_backend.repository.countries import (
    get_or_create_by_iso_code as get_or_create_country,
)
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.repository.genres import (
    get_or_create_by_tmdb_id as get_or_create_genre,
)
from flask_backend.repository.movie_metadata_fetch_attempts import (
    create as create_attempt,
    get_movies_needing_enrichment,
    has_attempt,
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


def _try_tmdb(movie_title: str) -> Optional[tuple[int, dict]]:
    """Attempt to find movie metadata on TMDB by searching for `movie_title`.

    Returns (tmdb_id, details) on success, None if nothing is found. Raises
    on network / API errors so the caller can record them.
    """
    client = TMDBClient()
    search_result = client.search_movie(movie_title)
    if search_result is None:
        return None
    return search_result["id"], client.get_movie_details(search_result["id"])


def clear_tmdb_metadata(movie: Movie) -> None:
    """Clears all TMDB-derived data from a movie in-memory: directors,
    genres, countries, collection, and the derived scalar fields. Does not
    touch tmdb_id/tmdb_excluded - callers set those explicitly.

    Does not commit - caller is responsible for db_session.add(movie) +
    db_session.commit().
    """
    movie.directors = []
    movie.genres = []
    movie.countries = []
    movie.collection_id = None
    movie.original_title = None
    movie.release_year = None
    movie.original_language = None


def apply_tmdb_details(movie: Movie, tmdb_id: int, details: dict) -> None:
    """Replaces a movie's TMDB-derived metadata in-memory with `details`:
    upserts directors, genres, countries and collection, sets
    original_title/release_year/original_language, records the tmdb_id
    link, and clears any prior manual tmdb_excluded flag.

    Any metadata from a previous link is cleared first, so this is safe to
    call whether the movie was previously unlinked or linked to a different
    TMDB entry.

    Does not commit - caller is responsible for db_session.add(movie) +
    db_session.commit().
    """
    clear_tmdb_metadata(movie)

    for d in details.get("directors", []):
        director = get_or_create_director(d["id"], d["name"])
        if director not in movie.directors:
            movie.directors.append(director)

    for g in details.get("genres", []):
        genre = get_or_create_genre(g["id"], g["name"])
        if genre not in movie.genres:
            movie.genres.append(genre)

    for c in details.get("countries", []):
        country = get_or_create_country(c["iso_3166_1"], c["name"])
        if country not in movie.countries:
            movie.countries.append(country)

    collection_data = details.get("collection")
    if (
        collection_data
        and collection_data.get("id") is not None
        and collection_data.get("name")
    ):
        collection = get_or_create_collection(
            collection_data["id"], collection_data["name"]
        )
        movie.collection_id = collection.id

    movie.original_title = details.get("original_title")
    movie.release_year = details.get("release_year")
    movie.original_language = details.get("original_language")
    movie.tmdb_id = tmdb_id
    movie.tmdb_excluded = False


def run_pipeline(
    limit: Optional[int] = None,
    dry_run: bool = False,
    pipeline_run_id: Optional[int] = None,
) -> PipelineResult:
    """Main entry point for the movie metadata pipeline.

    For each movie not yet linked to a TMDB entry:
    1. Skip it if a TMDB fetch was already attempted for it (it needs
       manual review instead).
    2. Otherwise fetch metadata from TMDB.
    3. Record the attempt (success / not_found / error).
    4. If successful, upsert and attach genres/directors to the movie.

    Args:
        limit: Maximum number of movies to process. None = all.
        dry_run: If True, only report what would be done without making requests.
        pipeline_run_id: If provided, tag created attempts with this run id.

    Returns:
        A PipelineResult summarising the run.
    """
    result = PipelineResult()
    movies = get_movies_needing_enrichment()

    if limit is not None:
        movies = movies[:limit]

    for movie in movies:
        if has_attempt(movie.id):
            result.skipped_all_sources_tried += 1
            logger.debug(
                "Filme %d ('%s'): TMDB já tentado sem sucesso – requer revisão manual",
                movie.id,
                movie.title,
            )
            continue

        if dry_run:
            logger.info(
                "[dry-run] Filme %d ('%s'): tentaria TMDB",
                movie.id,
                movie.title,
            )
            result.processed += 1
            continue

        try:
            outcome = _try_tmdb(movie.title)
        except Exception as exc:
            logger.warning(
                "Filme %d ('%s') – erro ao consultar TMDB: %s",
                movie.id,
                movie.title,
                exc,
            )
            create_attempt(
                movie_id=movie.id,
                source="tmdb",
                status="error",
                error_message=str(exc)[:500],
                pipeline_run_id=pipeline_run_id,
            )
            result.errors += 1
            result.processed += 1
            continue

        if outcome is None:
            logger.info(
                "Filme %d ('%s') – não encontrado no TMDB",
                movie.id,
                movie.title,
            )
            create_attempt(
                movie_id=movie.id,
                source="tmdb",
                status="not_found",
                pipeline_run_id=pipeline_run_id,
            )
            result.metadata_not_found += 1
            result.processed += 1
            continue

        resolved_tmdb_id, details = outcome
        apply_tmdb_details(movie, resolved_tmdb_id, details)
        db_session.add(movie)
        db_session.commit()

        logger.info(
            "Filme %d ('%s') – metadados salvos via TMDB",
            movie.id,
            movie.title,
        )
        create_attempt(
            movie_id=movie.id,
            source="tmdb",
            status="success",
            pipeline_run_id=pipeline_run_id,
        )
        result.metadata_found += 1
        result.processed += 1

    return result


def get_manual_review_summary() -> list[dict]:
    """Return a summary of movies that need manual metadata review.

    Each dict contains movie_id, movie_title, and the outcome of the last
    TMDB fetch attempt (status, error_message).
    """
    from flask_backend.repository.movie_metadata_fetch_attempts import (
        get_latest_attempt,
        get_movies_needing_manual_review,
    )

    movies = get_movies_needing_manual_review()
    summary = []
    for movie in movies:
        attempt = get_latest_attempt(movie.id)
        summary.append(
            {
                "movie_id": movie.id,
                "movie_title": movie.title,
                "status": attempt.status if attempt else None,
                "error_message": attempt.error_message if attempt else None,
            }
        )
    return summary
