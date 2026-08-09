"""
Tests flask_backend/repository/cinemas.py.
"""

from flask_backend.repository.cinemas import get_by_slug, get_cinemas_with_photo, update


class TestUpdateCinema:
    def test_updates_profile_fields(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_by_slug("capitolio")
            updated = update(
                cinema,
                name=cinema.name,
                url=cinema.url,
                address="Rua dos Andradas, 736",
                opening_hours="Ter-Dom, 14h-22h",
                instagram_url="https://instagram.com/cinemateca.capitolio",
                map_embed_url="https://www.google.com/maps/embed?pb=example",
            )

            assert updated.address == "Rua dos Andradas, 736"
            assert updated.opening_hours == "Ter-Dom, 14h-22h"
            assert updated.instagram_url == "https://instagram.com/cinemateca.capitolio"
            assert (
                updated.map_embed_url == "https://www.google.com/maps/embed?pb=example"
            )

    def test_keeps_existing_photo_when_none_provided(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_by_slug("capitolio")
            update(
                cinema,
                name=cinema.name,
                url=cinema.url,
                photo="old.png",
                photo_width=100,
                photo_height=200,
            )

            reloaded = get_by_slug("capitolio")
            updated = update(reloaded, name=reloaded.name, url=reloaded.url)

            assert updated.photo == "old.png"
            assert updated.photo_width == 100
            assert updated.photo_height == 200


class TestGetCinemasWithPhoto:
    def test_returns_only_cinemas_with_photo_set(self, app, setup_cinemas):
        with app.app_context():
            cinema = get_by_slug("capitolio")
            update(
                cinema,
                name=cinema.name,
                url=cinema.url,
                photo="https://i.ibb.co/x/capitolio.webp",
                photo_width=900,
                photo_height=600,
            )

            result = get_cinemas_with_photo()

        result_slugs = {c.slug for c in result}
        assert "capitolio" in result_slugs
        assert "sala-redencao" not in result_slugs
