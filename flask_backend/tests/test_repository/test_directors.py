"""
Tests flask_backend/repository/directors.py.
"""

from flask_backend.repository.directors import get_all, get_or_create_by_tmdb_id


class TestGetAll:
    def test_returns_every_director_ordered_by_name(self, app):
        with app.app_context():
            get_or_create_by_tmdb_id(2, "Wim Wenders")
            get_or_create_by_tmdb_id(1, "Agnès Varda")

            directors = get_all()

            assert [d.name for d in directors] == ["Agnès Varda", "Wim Wenders"]
