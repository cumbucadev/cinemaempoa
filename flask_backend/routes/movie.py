import math

from flask import Blueprint, g, jsonify, render_template, request
from werkzeug.exceptions import abort

from flask_backend.repository.movies import (
    get_all as get_all_movies,
    get_movies_with_similar_titles,
    get_paginated,
)
from flask_backend.routes.auth import login_required

bp = Blueprint("movie", __name__)


@bp.route("/movies")
def index():
    user_logged_in = g.user is not None
    movies = get_all_movies(user_logged_in)
    return render_template(
        "movie/index.html", movies=movies, show_drafts=user_logged_in
    )


@bp.route("/movies/posters")
def posters():
    user_logged_in = g.user is not None
    images = []
    return render_template(
        "movie/movies.html", images=images, show_drafts=user_logged_in
    )


@bp.route("/movies/posters/cubism")
def posters_cubism():
    crop_position = request.args.get("crop_position", "maintain")
    return render_template("movie/cubism.html", crop_position=crop_position)


@bp.route("/movies/posters/images")
def poster_images():
    lazy_loading = request.headers.get("X-LAZY-LOAD", None)
    if lazy_loading is None or lazy_loading != "1":
        abort(400)
    page = request.args.get("page", 0)
    limit = 4
    try:
        page = int(page)
    except ValueError:
        abort(400)

    user_logged_in = g.user is not None
    movies = get_paginated(page, limit, user_logged_in)

    if len(movies) == 0:
        abort(404)

    imgDisplayWidth = 325
    images = []
    image_urls = set()
    for movie in movies:
        for screening in movie.screenings:
            if not screening.image:
                continue
            if screening.image in image_urls:
                continue
            image_urls.add(screening.image)
            if screening.image:
                images.append(
                    {
                        "screening_id": screening.id,
                        "url": screening.image,
                        "width": imgDisplayWidth,
                        "height": math.ceil(
                            imgDisplayWidth
                            / screening.image_width
                            * screening.image_height
                        ),
                    }
                )
    return render_template(
        "movie/movie_posters.html", images=images, show_drafts=user_logged_in
    )


@bp.route("/movies/posters/images/urls")
def poster_images_urls():
    page = request.args.get("page", 0)
    limit = 4
    try:
        page = int(page)
    except ValueError:
        abort(400)

    user_logged_in = g.user is not None
    movies = get_paginated(page, limit, user_logged_in)

    if len(movies) == 0:
        abort(404)

    image_urls = []
    for movie in movies:
        for screening in movie.screenings:
            if not screening.image:
                continue
            if screening.image in image_urls:
                continue
            image_urls.append(screening.image)
    return jsonify(image_urls)


@bp.route("/movies/search", methods=["GET"])
@login_required
def search_movies():
    title = request.args.get("title")
    movies = get_movies_with_similar_titles(title)
    return jsonify([{"title": movie.title} for movie in movies])
