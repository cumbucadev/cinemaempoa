"""Pipeline that searches for missing screening posters across multiple sources.

Usage (via CLI):
    flask fetch-posters          # process all screenings missing images
    flask fetch-posters --limit 10   # process at most 10
    flask fetch-posters --dry-run    # only list what would be processed
"""

import logging
from dataclasses import dataclass
from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import POSTER_SOURCES
from flask_backend.repository.poster_fetch_attempts import (
    create as create_attempt,
    get_next_source,
    get_screenings_without_poster,
)
from flask_backend.import_json import ScrappedFeature
from flask_backend.service.screening import download_image_from_url, save_image
from flask_backend.service.tmdb import TMDBClient
from scrapers.imdb import IMDBScrapper

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Summary returned after a pipeline run."""

    processed: int = 0
    posters_found: int = 0
    posters_not_found: int = 0
    errors: int = 0
    skipped_all_sources_tried: int = 0


def _try_tmdb(movie_title: str) -> Optional[str]:
    """Attempt to find a poster URL using the TMDB API.

    Returns the image URL on success, None if not found.
    Raises on network / API errors so the caller can record them.
    """
    client = TMDBClient()
    return client.get_poster_url(movie_title)


def _try_imdb(movie_title: str, director: Optional[str] = None) -> Optional[str]:
    """Attempt to find a poster URL by scraping IMDB.

    Returns the image URL on success, None if not found.
    Raises on network / parsing errors so the caller can record them.
    """
    scrapper = IMDBScrapper()
    feature = ScrappedFeature(
        poster=None,
        time=None,
        title=movie_title,
        original_title=None,
        price=None,
        director=director if director else False,
        classification=None,
        general_info=None,
        excerpt="",
        read_more=None,
    )
    return scrapper.get_image(feature)


# Maps source name -> callable that receives (movie_title, **kwargs) and returns
# an image URL or None.
_SOURCE_HANDLERS = {
    "tmdb": lambda title, **_kw: _try_tmdb(title),
    "imdb": lambda title, **kw: _try_imdb(title, director=kw.get("director")),
}


def _extract_director_from_description(description: str) -> Optional[str]:
    """Best-effort extraction of director name from the screening description.

    The import pipeline typically stores the director in a line by itself.
    This is a heuristic that looks for lines starting with 'Direção:' or
    'Diretor:' / 'Diretora:'.
    """
    if not description:
        return None
    for line in description.splitlines():
        stripped = line.strip()
        for prefix in ("Direção:", "Diretor:", "Diretora:", "Director:", "Directed by"):
            if stripped.lower().startswith(prefix.lower()):
                return stripped[len(prefix) :].strip()
    return None


def run_pipeline(current_app, limit: Optional[int] = None, dry_run: bool = False) -> PipelineResult:
    """Main entry point for the poster pipeline.

    For each screening without an image:
    1. Determine the next untried source (following POSTER_SOURCES order).
    2. Attempt to fetch a poster from that source.
    3. Record the attempt (success / not_found / error).
    4. If successful, download and save the image, updating the screening.

    Args:
        current_app: The Flask application (needed by save_image).
        limit: Maximum number of screenings to process. None = all.
        dry_run: If True, only report what would be done without making requests.

    Returns:
        A PipelineResult summarising the run.
    """
    result = PipelineResult()
    screenings = get_screenings_without_poster()

    if limit is not None:
        screenings = screenings[:limit]

    for screening in screenings:
        movie_title = screening.movie.title
        next_source = get_next_source(screening.id)

        if next_source is None:
            result.skipped_all_sources_tried += 1
            logger.debug(
                "Screening %d ('%s'): todas as fontes já tentadas – requer revisão manual",
                screening.id,
                movie_title,
            )
            continue

        if dry_run:
            logger.info(
                "[dry-run] Screening %d ('%s'): tentaria fonte '%s'",
                screening.id,
                movie_title,
                next_source,
            )
            result.processed += 1
            continue

        handler = _SOURCE_HANDLERS.get(next_source)
        if handler is None:
            logger.error("Fonte '%s' não possui handler implementado", next_source)
            result.errors += 1
            continue

        director = _extract_director_from_description(screening.description)
        image_url: Optional[str] = None

        try:
            image_url = handler(movie_title, director=director)
        except Exception as exc:
            logger.warning(
                "Screening %d ('%s') – erro na fonte '%s': %s",
                screening.id,
                movie_title,
                next_source,
                exc,
            )
            create_attempt(
                screening_id=screening.id,
                source=next_source,
                status="error",
                error_message=str(exc)[:500],
            )
            result.errors += 1
            result.processed += 1
            continue

        if image_url is None:
            logger.info(
                "Screening %d ('%s') – fonte '%s': poster não encontrado",
                screening.id,
                movie_title,
                next_source,
            )
            create_attempt(
                screening_id=screening.id,
                source=next_source,
                status="not_found",
            )
            result.posters_not_found += 1
            result.processed += 1
            continue

        # Download and save the image
        img_bytes, filename = download_image_from_url(image_url)
        if img_bytes is None:
            logger.warning(
                "Screening %d ('%s') – poster encontrado em '%s' mas download falhou: %s",
                screening.id,
                movie_title,
                next_source,
                image_url,
            )
            create_attempt(
                screening_id=screening.id,
                source=next_source,
                status="error",
                error_message=f"Download falhou: {image_url}",
            )
            result.errors += 1
            result.processed += 1
            continue

        image_filename, image_width, image_height = save_image(
            img_bytes, current_app, filename
        )

        screening.image = image_filename
        screening.image_width = image_width
        screening.image_height = image_height
        db_session.add(screening)
        db_session.commit()

        logger.info(
            "Screening %d ('%s') – poster salvo via '%s': %s",
            screening.id,
            movie_title,
            next_source,
            image_filename,
        )
        create_attempt(
            screening_id=screening.id,
            source=next_source,
            status="success",
        )
        result.posters_found += 1
        result.processed += 1

    return result


def get_manual_review_summary() -> list[dict]:
    """Return a summary of screenings that need manual poster review.

    Each dict contains screening_id, movie_title, and the list of
    sources already attempted.
    """
    from flask_backend.repository.poster_fetch_attempts import (
        get_attempted_sources,
        get_screenings_needing_manual_review,
    )

    screenings = get_screenings_needing_manual_review()
    summary = []
    for s in screenings:
        attempted = get_attempted_sources(s.id)
        summary.append(
            {
                "screening_id": s.id,
                "movie_title": s.movie.title,
                "sources_attempted": sorted(attempted),
                "total_sources": len(POSTER_SOURCES),
            }
        )
    return summary
