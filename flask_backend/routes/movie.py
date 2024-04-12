from flask import Blueprint, g, render_template, jsonify, after_this_request

from flask_backend.repository.movies import get_all as get_all_movies
from flask_backend.repository.movies import get_movies_with_similar_titles
from flask import request

bp = Blueprint("movie", __name__)


@bp.route("/movies")
def index():
    user_logged_in = g.user is not None
    movies = get_all_movies(user_logged_in)
    return render_template(
        "movie/index.html", movies=movies, show_drafts=user_logged_in
    )


@bp.route("/movies/search", methods=['GET'])
def search_movies():
    @after_this_request
    def add_header(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    title = request.args.get('title')
    movies = get_movies_with_similar_titles(title)
    return jsonify([{'title': movie.title} for movie in movies])
