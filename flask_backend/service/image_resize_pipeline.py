"""Backfill pipeline that reprocesses already-stored screening posters and
cinema photos through resize_for_display() (via save_image()), for images
uploaded before issue #229's resize step shipped.

Usage (via CLI):
    flask resize-images          # process all eligible screenings/cinemas
    flask resize-images --limit 10
    flask resize-images --dry-run
"""

import logging
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse

from flask_backend.db import db_session
from flask_backend.repository.cinemas import get_cinemas_with_photo
from flask_backend.repository.screenings import get_screenings_with_image
from flask_backend.service.screening import (
    download_image_from_url,
    get_img_path_from_filename,
    save_image,
)

logger = logging.getLogger(__name__)

# Must match resize_for_display's default max_dimension - an image within
# this bound and already webp is assumed to have already gone through the
# resize pipeline, so reprocessing it would be a no-op.
MAX_DIMENSION = 1200


@dataclass
class ResizePipelineResult:
    processed: int = 0
    resized: int = 0
    skipped_already_processed: int = 0
    errors: int = 0


def _is_already_processed(
    url: Optional[str], width: Optional[int], height: Optional[int]
) -> bool:
    if not url or width is None or height is None:
        return False
    is_webp = urlparse(url).path.lower().endswith(".webp")
    within_bounds = max(width, height) <= MAX_DIMENSION
    return is_webp and within_bounds


def _reprocess(url: str, current_app):
    if url.startswith("http://") or url.startswith("https://"):
        image_bytes, filename = download_image_from_url(url)
        if image_bytes is None:
            raise RuntimeError(f"Falha ao baixar imagem: {url}")
    else:
        filename = os.path.basename(url)
        img_path = get_img_path_from_filename(filename, current_app)
        if img_path is None:
            raise RuntimeError(f"Arquivo local não encontrado: {url}")
        with open(img_path, "rb") as f:
            image_bytes = BytesIO(f.read())
    return save_image(image_bytes, current_app, filename)


def run_pipeline(
    current_app,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> ResizePipelineResult:
    """Reprocesses every screening image / cinema photo that isn't already
    a webp within MAX_DIMENSION, resizing and re-uploading via save_image()
    and updating the corresponding DB row."""
    result = ResizePipelineResult()

    all_screenings = get_screenings_with_image()
    screenings_to_process = [
        s
        for s in all_screenings
        if not _is_already_processed(s.image, s.image_width, s.image_height)
    ]

    all_cinemas = get_cinemas_with_photo()
    cinemas_to_process = [
        c
        for c in all_cinemas
        if not _is_already_processed(c.photo, c.photo_width, c.photo_height)
    ]

    result.skipped_already_processed = (
        len(all_screenings)
        - len(screenings_to_process)
        + len(all_cinemas)
        - len(cinemas_to_process)
    )

    items = [("screening", s) for s in screenings_to_process] + [
        ("cinema", c) for c in cinemas_to_process
    ]
    if limit is not None:
        items = items[:limit]

    for kind, obj in items:
        result.processed += 1
        url = obj.image if kind == "screening" else obj.photo

        if dry_run:
            logger.info("[dry-run] %s #%d: reprocessaria %s", kind, obj.id, url)
            continue

        try:
            new_url, width, height = _reprocess(url, current_app)
        except Exception as exc:
            logger.warning(
                "%s #%d: erro ao reprocessar '%s': %s", kind, obj.id, url, exc
            )
            result.errors += 1
            continue

        if kind == "screening":
            obj.image = new_url
            obj.image_width = width
            obj.image_height = height
        else:
            obj.photo = new_url
            obj.photo_width = width
            obj.photo_height = height
        db_session.add(obj)
        db_session.commit()
        result.resized += 1

    return result
