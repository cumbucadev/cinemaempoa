import math
import mimetypes
import os

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    render_template,
    request,
    send_file,
)
from werkzeug.exceptions import abort

from flask_backend.repository.movies import (
    get_all as get_all_movies,
    get_movies_with_similar_titles,
    get_paginated_with_images,
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
    lazy_loading = request.headers.get("X-LAZY-LOAD", "0")
    if lazy_loading != "1":
        abort(400)

    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 4))
    except ValueError:
        abort(400)

    user_logged_in = g.user is not None
    screenings_list = get_paginated_with_images(page, limit, user_logged_in)

    if len(screenings_list) == 0:
        abort(404)

    imgDisplayWidth = 325
    images = []
    image_urls = set()
    for screening in screenings_list:
        if screening.image in image_urls:
            continue

        image_urls.add(screening.image)
        filename = screening.image.split("/")[-1]
        movie_title = screening.movie.title
        safe_title = "".join(
            c for c in movie_title if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        safe_title = safe_title.replace(" ", "_")
        file_extension = os.path.splitext(filename)[1]
        download_name = f"{safe_title}{file_extension}"

        images.append(
            {
                "screening_id": screening.id,
                "url": screening.image,
                "filename": filename,
                "download_name": download_name,
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
    screenings_list = get_paginated_with_images(page, limit, user_logged_in)

    if len(screenings_list) == 0:
        abort(404)

    image_urls = []
    for screening in screenings_list:
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


@bp.route("/movies/posters/download/<filename>")
def download_poster(filename):
    try:
        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

        if not os.path.exists(file_path):
            abort(404)

        mimetype, _ = mimetypes.guess_type(file_path)
        if mimetype is None:
            mimetype = "application/octet-stream"

        from flask_backend.repository.screenings import get_screening_by_image_filename

        screening = get_screening_by_image_filename(filename)

        if screening:
            movie_title = screening.movie.title
            safe_title = "".join(
                c for c in movie_title if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            safe_title = safe_title.replace(" ", "_")
            file_extension = os.path.splitext(filename)[1]
            download_name = f"{safe_title}{file_extension}"
        else:
            file_extension = os.path.splitext(filename)[1]
            download_name = f"poster{file_extension}"

        return send_file(
            file_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype,
        )
    except Exception as e:
        current_app.logger.error(
            f"Erro ao fazer download do poster {filename}: {str(e)}"
        )
        abort(500)
