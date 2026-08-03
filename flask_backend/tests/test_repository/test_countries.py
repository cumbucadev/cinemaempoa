"""
Tests flask_backend/repository/countries.py.
"""

from flask_backend.repository.countries import get_all, get_or_create_by_iso_code


class TestGetAll:
    def test_returns_every_country_ordered_by_name(self, app):
        with app.app_context():
            get_or_create_by_iso_code("US", "United States of America")
            get_or_create_by_iso_code("BR", "Brazil")

            countries = get_all()

            assert [c.name for c in countries] == ["Brazil", "United States of America"]
