from flask_backend.db import db_session
from flask_backend.models import Movie, WantToWatch
from flask_backend.repository.want_to_watch import (
    get_movie_ids_for_visitor,
    toggle,
)


def _movie(title="Test Movie"):
    movie = Movie(title=title, slug=title.lower().replace(" ", "-"))
    db_session.add(movie)
    db_session.commit()
    return movie.id


class TestToggle:
    def test_marks_a_movie_for_a_visitor(self, app):
        with app.app_context():
            movie_id = _movie()

            wanted = toggle(movie_id, "visitor-a")

            assert wanted is True
            assert (
                db_session.query(WantToWatch)
                .filter_by(movie_id=movie_id, visitor_id="visitor-a")
                .count()
                == 1
            )

    def test_toggling_twice_removes_the_mark(self, app):
        with app.app_context():
            movie_id = _movie()
            toggle(movie_id, "visitor-a")

            wanted = toggle(movie_id, "visitor-a")

            assert wanted is False
            assert (
                db_session.query(WantToWatch)
                .filter_by(movie_id=movie_id, visitor_id="visitor-a")
                .count()
                == 0
            )

    def test_marks_are_scoped_per_visitor(self, app):
        with app.app_context():
            movie_id = _movie()
            toggle(movie_id, "visitor-a")

            wanted_b = toggle(movie_id, "visitor-b")

            assert wanted_b is True
            assert (
                db_session.query(WantToWatch).filter_by(movie_id=movie_id).count() == 2
            )


class TestGetMovieIdsForVisitor:
    def test_returns_empty_set_for_unknown_visitor(self, app):
        with app.app_context():
            assert get_movie_ids_for_visitor("nobody") == set()

    def test_returns_marked_movie_ids(self, app):
        with app.app_context():
            movie_id_1 = _movie("Movie One")
            movie_id_2 = _movie("Movie Two")
            toggle(movie_id_1, "visitor-a")
            toggle(movie_id_2, "visitor-a")

            result = get_movie_ids_for_visitor("visitor-a")

            assert result == {movie_id_1, movie_id_2}
