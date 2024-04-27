import math

from flask import Blueprint, g, jsonify, render_template, request
from werkzeug.exceptions import abort

from flask_backend.repository.movies import get_all as get_all_movies
from flask_backend.repository.movies import (
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
    page = request.args.get("page", 0)
    try:
        page = int(page)
    except ValueError:
        abort(400)
    user_logged_in = g.user is not None
    qtt_movies = 12 if page == 0 else 4
    movies = get_paginated(page, qtt_movies, user_logged_in)
    if len(movies) == 0:
        abort(404)

    # number of columns in the grid
    num_columns = 3
    # limits how wide a movie image can be on the listing
    imgDisplayWidth = 325
    images = []
    for movie in movies:
        for screening in movie.screenings:
            if screening.image:
                images.append(
                    {
                        "url": screening.image,
                        "width": imgDisplayWidth,
                        "height": math.ceil(
                            imgDisplayWidth
                            / screening.image_width
                            * screening.image_height
                        ),
                    }
                )
    cols_height = [0] * num_columns
    for i in range(0, len(images), 3):
        for j in range(num_columns):
            try:
                cols_height[j] = cols_height[j] + int(images[i + j]["height"])
            except IndexError:
                cols_height[j] = cols_height[j] + 0

    # take the tallest column and add the equivalent margin-bottom for each row
    num_rows = math.ceil(len(images) / num_columns)
    max_column_height = max(cols_height) + (num_rows * 15)
    return render_template(
        "movie/movies.html",
        images=images,
        max_column_height=max_column_height,
        show_drafts=user_logged_in,
        page=page,
    )


@bp.route("/movies/search", methods=["GET"])
@login_required
def search_movies():
    title = request.args.get("title")
    movies = get_movies_with_similar_titles(title)
    return jsonify([{"title": movie.title} for movie in movies])
