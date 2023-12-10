from flask import Blueprint, g, render_template

from flask_backend.repository.movies import get_all as get_all_movies

bp = Blueprint("movie", __name__)


@bp.route("/movies")
def index():
    user_logged_in = g.user is not None
    movies = get_all_movies(user_logged_in)
    return render_template(
        "movie/index.html", movies=movies, show_drafts=user_logged_in
    )
