import requests
from flask import Blueprint, abort, jsonify, render_template, request

from flask_backend.db import db_session
from flask_backend.repository.movies import get_by_id
from flask_backend.routes.auth import login_required
from flask_backend.service.movie_metadata_pipeline import (
    apply_tmdb_details,
    clear_tmdb_metadata,
)
from flask_backend.service.tmdb import TMDB_IMAGE_BASE_URL, TMDBClient

bp = Blueprint("admin_movies", __name__)


def _movie_state(movie):
    return {
        "id": movie.id,
        "title": movie.title,
        "original_title": movie.original_title,
        "release_year": movie.release_year,
        "original_language": movie.original_language,
        "tmdb_id": movie.tmdb_id,
        "tmdb_excluded": movie.tmdb_excluded,
        "directors": [d.name for d in movie.directors],
        "genres": [g.name for g in movie.genres],
        "collection": movie.collection.name if movie.collection else None,
    }


@bp.route("/admin/movies/<int:movie_id>")
@login_required
def edit(movie_id):
    movie = get_by_id(movie_id)
    if not movie:
        abort(404)
    return render_template("movie/admin/edit.html", movie=movie)


@bp.route("/admin/movies/<int:movie_id>/tmdb-search")
@login_required
def tmdb_search(movie_id):
    movie = get_by_id(movie_id)
    if not movie:
        abort(404)

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    try:
        results = TMDBClient().search_movies(query)
    except requests.RequestException as exc:
        return jsonify({"error": str(exc)}), 502

    candidates = []
    for r in results:
        release_date = r.get("release_date")
        release_year = None
        if release_date:
            try:
                release_year = int(release_date[:4])
            except ValueError:
                release_year = None
        poster_path = r.get("poster_path")
        candidates.append(
            {
                "tmdb_id": r["id"],
                "title": r.get("title"),
                "original_title": r.get("original_title"),
                "release_year": release_year,
                "poster_url": (
                    f"{TMDB_IMAGE_BASE_URL}/w92{poster_path}" if poster_path else None
                ),
            }
        )
    return jsonify(candidates)


@bp.route("/admin/movies/<int:movie_id>/tmdb-link", methods=["POST"])
@login_required
def tmdb_link(movie_id):
    movie = get_by_id(movie_id)
    if not movie:
        abort(404)

    payload = request.get_json(silent=True) or {}
    tmdb_id = payload.get("tmdb_id")
    if not tmdb_id:
        return jsonify({"error": "tmdb_id é obrigatório."}), 400

    try:
        tmdb_id = int(tmdb_id)
    except (ValueError, TypeError):
        return jsonify({"error": "tmdb_id é obrigatório."}), 400

    try:
        details = TMDBClient().get_movie_details(tmdb_id)
    except requests.RequestException as exc:
        return jsonify({"error": str(exc)}), 502

    apply_tmdb_details(movie, tmdb_id, details)
    db_session.add(movie)
    db_session.commit()

    return jsonify(_movie_state(movie))


@bp.route("/admin/movies/<int:movie_id>/tmdb-unlink", methods=["POST"])
@login_required
def tmdb_unlink(movie_id):
    movie = get_by_id(movie_id)
    if not movie:
        abort(404)

    clear_tmdb_metadata(movie)
    movie.tmdb_id = None
    movie.tmdb_excluded = True
    db_session.add(movie)
    db_session.commit()

    return jsonify(_movie_state(movie))
