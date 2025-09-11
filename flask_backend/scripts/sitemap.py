from flask import Flask, url_for

from flask_backend.repository import blog_posts
from flask_backend.repository.movies import get_all
from flask_backend.routes import blog, movie, page, screening

app = Flask(__name__)
app.config["SERVER_NAME"] = "cinemaempoa.com.br"
app.config["PREFERRED_URL_SCHEME"] = "https"

app.register_blueprint(screening.bp)
app.register_blueprint(movie.bp)
app.register_blueprint(blog.bp)
app.register_blueprint(page.bp)


def absolute_url(*args, **kwargs):
    with app.app_context():
        return url_for(*args, **kwargs)


def sitemap():
    urls = []

    # pages from routes.screening
    urls.append(absolute_url("screening.index"))
    urls.append(absolute_url("screening.programacao"))

    # pages that are not related to any specific resources
    urls.append(absolute_url("page.about"))

    # pages from routes.movie
    urls.append(absolute_url("movie.index"))
    urls.append(absolute_url("movie.posters"))
    urls.append(absolute_url("movie.posters_cubism"))

    # include urls for all movies with at least one screening
    movies = get_all(include_drafts=False)
    [urls.append(absolute_url("movie.show", slug=movie.slug)) for movie in movies]

    # pages from routes.blog
    urls.append(absolute_url("blog.index"))
    posts = blog_posts.get_all(include_unpublished=False)
    [urls.append(absolute_url("blog.show", slug=post.slug)) for post in posts]

    print("\n".join(urls))
