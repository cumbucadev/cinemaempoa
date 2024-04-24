from flask import Blueprint, g, jsonify, render_template, request

from flask_backend.repository.movies import (
    get_all as get_all_movies,
    get_movies_with_similar_titles,
)
from flask_backend.routes.auth import login_required

bp = Blueprint("movie", __name__)


@bp.route("/movies")
def index():
    user_logged_in = g.user is not None
    movies = get_all_movies(user_logged_in)
    return render_template("movie/index.html", movies=movies, show_drafts=user_logged_in)


@bp.route("/movies/search", methods=["GET"])
@login_required
def search_movies():
    title = request.args.get("title")
    movies = get_movies_with_similar_titles(title)
    return jsonify([{"title": movie.title} for movie in movies])
