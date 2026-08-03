"""
Tests flask_backend/repository/genres.py.
"""

from flask_backend.repository.genres import get_all, get_or_create_by_tmdb_id


class TestGetAll:
    def test_returns_every_genre_ordered_by_name(self, app):
        with app.app_context():
            get_or_create_by_tmdb_id(2, "Drama")
            get_or_create_by_tmdb_id(1, "Comédia")

            genres = get_all()

            assert [g.name for g in genres] == ["Comédia", "Drama"]
