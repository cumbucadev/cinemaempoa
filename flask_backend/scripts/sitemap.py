from flask import Flask, url_for

from flask_backend.repository.movies import get_all
from flask_backend.routes import movie, screening

app = Flask(__name__)
app.config["SERVER_NAME"] = "cinemaempoa.com.br"
app.config["PREFERRED_URL_SCHEME"] = "https"

app.register_blueprint(screening.bp)
app.register_blueprint(movie.bp)


def absolute_url(*args, **kwargs):
    with app.app_context():
        return url_for(*args, **kwargs)


def sitemap():
    urls = []

    # pages from routes.screening
    urls.append(absolute_url("screening.index"))
    urls.append(absolute_url("screening.programacao"))

    # pages from routes.movie
    urls.append(absolute_url("movie.index"))
    urls.append(absolute_url("movie.posters"))
    urls.append(absolute_url("movie.posters_cubism"))

    # include urls for all movies with at least one screening
    movies = get_all(include_drafts=False)
    [urls.append(absolute_url("movie.show", slug=movie.slug)) for movie in movies]

    print("\n".join(urls))
