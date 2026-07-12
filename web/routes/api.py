import logging
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from shared.schema import ScrappedResult
from web.db import db_session
from web.env_config import IMPORT_API_TOKEN
from web.repository.cinemas import get_by_slug as get_cinema_by_slug
from web.repository.poster_fetch_attempts import (
    create as create_attempt,
    get_next_source,
    get_screenings_without_poster,
)
from web.repository.screenings import get_screening_by_id
from web.service.screening import download_image_from_url, import_scrapped_results, save_image

bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


def require_api_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if IMPORT_API_TOKEN is None:
            logger.warning("IMPORT_API_TOKEN is not configured")
            return jsonify({"error": "API token not configured"}), 500

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[len("Bearer "):]
        if token != IMPORT_API_TOKEN:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)

    return decorated


@bp.route("/import", methods=["POST"])
@require_api_token
def import_screenings():
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, list):
        return jsonify({"error": "Request body must be a JSON array of cinema objects"}), 400

    try:
        scrapped_result = ScrappedResult.from_jsonable(body)
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid body structure: {exc}"}), 400

    for scrapped_cinema in scrapped_result.cinemas:
        cinema = get_cinema_by_slug(scrapped_cinema.slug)
        if cinema is None:
            return jsonify({"error": f"Unknown cinema slug: {scrapped_cinema.slug}"}), 422

    created = import_scrapped_results(scrapped_result, current_app)
    return jsonify({"created": created}), 200


@bp.route("/screenings/missing-posters", methods=["GET"])
@require_api_token
def missing_posters():
    screenings = get_screenings_without_poster()
    result = []
    for screening in screenings:
        next_source = get_next_source(screening.id)
        if next_source is None:
            continue
        result.append(
            {
                "id": screening.id,
                "movie_title": screening.movie.title,
                "next_source": next_source,
            }
        )
    return jsonify(result), 200


@bp.route("/screenings/<int:screening_id>/poster", methods=["PATCH"])
@require_api_token
def update_poster(screening_id):
    screening = get_screening_by_id(screening_id)
    if screening is None:
        return jsonify({"error": "Screening not found"}), 404

    body = request.get_json(silent=True)
    if body is None or "url" not in body or "source" not in body:
        return jsonify({"error": "Request body must include 'url' and 'source'"}), 400

    image_url = body["url"]
    source = body["source"]

    img_bytes, filename = download_image_from_url(image_url)
    if img_bytes is None:
        create_attempt(
            screening_id=screening.id,
            source=source,
            status="error",
            error_message=f"Download failed: {image_url}",
        )
        return jsonify({"error": "Could not download or validate image from URL"}), 422

    image_filename, image_width, image_height = save_image(img_bytes, current_app, filename)

    screening.image = image_filename
    screening.image_width = image_width
    screening.image_height = image_height
    db_session.add(screening)
    db_session.commit()

    create_attempt(
        screening_id=screening.id,
        source=source,
        status="success",
    )

    return jsonify({"image": image_filename}), 200
