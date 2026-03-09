# ruff: noqa: E402

import os
import socket
import threading
from contextlib import closing

import pytest
from werkzeug.serving import make_server

os.environ.setdefault("PYTEST_VERSION", "1")

from flask_backend import create_app
from flask_backend.db import Base, db_session, engine
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate, User
from flask_backend.seeds.cinema_seeds import create_cinemas
from flask_backend.seeds.movie_seeds import create_movies
from flask_backend.seeds.screening_seeds import create_screenings


def _get_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class TestServerThread(threading.Thread):
    def __init__(self, app, host: str, port: int):
        super().__init__(daemon=True)
        self.server = make_server(host, port, app)

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture()
def app():
    app = create_app({"TESTING": True})

    with app.app_context():
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    yield app


@pytest.fixture(autouse=True)
def clean_db(app):
    with app.app_context():
        db_session.query(ScreeningDate).delete()
        db_session.query(Screening).delete()
        db_session.query(Movie).delete()
        db_session.query(Cinema).delete()
        db_session.query(User).delete()
        db_session.commit()


def teardown_db():
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def setup_cinemas(app):
    with app.app_context():
        create_cinemas(db_session)
        db_session.commit()


@pytest.fixture()
def setup_movie(app):
    with app.app_context():
        create_movies(db_session)
        db_session.commit()


@pytest.fixture()
def setup_screenings(app):
    with app.app_context():
        create_screenings(
            db_session, placeholder_url="https://placehold.co/{width}x{height}"
        )
        db_session.commit()


@pytest.fixture()
def seeded_frontend_data(app, setup_cinemas, setup_movie, setup_screenings):
    with app.app_context():
        screenings = db_session.query(Screening).order_by(Screening.id.asc()).all()
        screening_home = screenings[0]
        screening_show = screenings[1]
        screening_grid = screenings[2]

        return {
            "base_paths": {
                "home": "/",
                "show": f"/movies/{screening_show.movie.slug}",
                "posters": "/movies/posters",
            },
            "image_paths": {
                "home": screening_home.image,
                "show": screening_show.image,
                "posters": screening_grid.image,
            },
            "movie_slug": screening_show.movie.slug,
        }


@pytest.fixture()
def live_server(app, seeded_frontend_data):
    host = "127.0.0.1"
    port = _get_free_port()
    server = TestServerThread(app, host, port)
    server.start()

    base_url = f"http://{host}:{port}"

    yield {
        "base_url": base_url,
        **seeded_frontend_data,
    }

    server.shutdown()
    server.join(timeout=5)
    teardown_db()
