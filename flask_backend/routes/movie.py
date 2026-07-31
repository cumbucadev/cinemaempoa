import math

from flask import Blueprint, g, jsonify, render_template, request
from werkzeug.exceptions import abort

from flask_backend.repository.movies import (
    get_all_paginated as get_all_movies_paginated,
    get_by_slug,
    get_movies_with_similar_titles,
    get_paginated_screenings_with_image,
)
from flask_backend.routes.auth import login_required
from flask_backend.routes.screening import CANONICAL_BASE_URL

bp = Blueprint("movie", __name__)


@bp.route("/movies")
def index():
    user_logged_in = g.user is not None
    try:
        movie = request.args.get("movie", "")
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
    except ValueError:
        abort(400)

    movies, pages, qtt_movies = get_all_movies_paginated(
        movie, page, limit, user_logged_in
    )
    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < pages else None
    return render_template(
        "movie/index.html",
        movies=movies,
        show_drafts=user_logged_in,
        curr_page=page,
        prev_page=prev_page,
        next_page=next_page,
        movie=movie,
        pages=pages,
        limit=limit,
        qtt_movies=qtt_movies,
    )


@bp.route("/movies/posters")
def posters():
    user_logged_in = g.user is not None
    images = []
    return render_template(
        "movie/posters.html", images=images, show_drafts=user_logged_in
    )


@bp.route("/movies/posters/images")
def poster_images():
    lazy_loading = request.headers.get("X-LAZY-LOAD", "0")
    if lazy_loading != "1":
        abort(400)

    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 4))
    except ValueError:
        abort(400)

    user_logged_in = g.user is not None
    screenings_list = get_paginated_screenings_with_image(page, limit, user_logged_in)

    if len(screenings_list) == 0:
        abort(404)

    imgDisplayWidth = 325
    images = []
    image_urls = set()
    for screening in screenings_list:
        if not screening.image:
            continue
        if screening.image in image_urls:
            continue

        image_urls.add(screening.image)
        if screening.image:
            images.append(
                {
                    "screening_id": screening.id,
                    "movie_slug": screening.movie.slug,
                    "url": screening.image,
                    "image_alt": screening.image_alt,
                    "width": imgDisplayWidth,
                    "height": math.ceil(
                        imgDisplayWidth / screening.image_width * screening.image_height
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
    screenings_list = get_paginated_screenings_with_image(page, limit, user_logged_in)

    if len(screenings_list) == 0:
        abort(404)

    image_urls = []
    for screening in screenings_list:
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
    exclude_movie_id = request.args.get("exclude_movie_id", type=int)
    movies = get_movies_with_similar_titles(title, exclude_movie_id=exclude_movie_id)
    return jsonify(
        [
            {"id": movie.id, "title": movie.title, "release_year": movie.release_year}
            for movie in movies
        ]
    )


@bp.route("/movies/<slug>", methods=["GET"])
def show(slug):
    movie = get_by_slug(slug)
    if not movie:
        abort(400)

    images = []
    for screening in movie.screenings:
        if screening.image is not None:
            images.append(screening.image)

    selected_screening_id = request.args.get("screening", type=int)
    valid_screening_ids = {s.id for s in movie.screenings if s.image}
    if selected_screening_id not in valid_screening_ids:
        selected_screening_id = None

    og_image = None
    if selected_screening_id is not None:
        selected_screening = next(
            (s for s in movie.screenings if s.id == selected_screening_id), None
        )
        if selected_screening is not None:
            og_image = selected_screening.image
    elif images:
        og_image = images[0]

    if og_image and not og_image.startswith("http"):
        og_image = CANONICAL_BASE_URL + (
            og_image if og_image.startswith("/") else f"/{og_image}"
        )

    return render_template(
        "movie/show.html",
        movie=movie,
        images=images,
        selected_screening_id=selected_screening_id,
        og_image=og_image,
    )
