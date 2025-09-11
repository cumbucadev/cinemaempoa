import os

from flask import Flask, request, send_from_directory

from flask_backend.db import db_session
from flask_backend.env_config import SESSION_KEY, UPLOAD_DIR


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    if UPLOAD_DIR is not None:
        app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
    else:
        app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")

    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 5  # max 5mb file uploads
    app.config.from_mapping(SECRET_KEY=SESSION_KEY)
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the intance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import db

    db.init_app(app)

    from . import commands

    commands.register_commands(app)

    from .routes import auth

    app.register_blueprint(auth.bp)

    from .routes import screening

    app.register_blueprint(screening.bp)

    from .routes import movie

    app.register_blueprint(movie.bp)

    from .routes import blog

    app.register_blueprint(blog.bp)

    from .routes.admin import blog as admin_blog

    app.register_blueprint(admin_blog.bp)

    from .routes import page

    app.register_blueprint(page.bp)

    @app.route("/robots.txt")
    def static_from_root():
        """Taken from https://stackoverflow.com/a/14625619"""
        return send_from_directory(app.static_folder, request.path[1:])

    @app.route("/sitemaps.txt")
    def serve_static_sitemap():
        return send_from_directory(app.static_folder, request.path[1:])

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    return app
