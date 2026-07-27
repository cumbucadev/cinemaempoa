"""
Tests the basic functionality of /admin/cinemas/* endpoints.
"""

import io
from unittest.mock import patch

from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug


class TestAdminCinemasIndex:
    def test_requires_login(self, client, setup_cinemas):
        response = client.get("/admin/cinemas")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_200(self, auth_headers, setup_cinemas):
        response = auth_headers.get("/admin/cinemas")
        assert response.status_code == 200


class TestAdminCinemaUpdate:
    def test_requires_login(self, app, client, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id
        response = client.get(f"/admin/cinemas/{cinema_id}/update")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_unknown_id(self, auth_headers, setup_cinemas):
        response = auth_headers.get("/admin/cinemas/9999/update")
        assert response.status_code == 404

    def test_updates_profile_fields(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id

        response = auth_headers.post(
            f"/admin/cinemas/{cinema_id}/update",
            data={
                "name": "Cinemateca Capitólio",
                "url": "http://www.capitolio.org.br/",
                "address": "Rua dos Andradas, 736",
                "opening_hours": "Ter-Dom, 14h-22h",
                "instagram_url": "https://instagram.com/cinemateca.capitolio",
                "map_embed_url": "https://www.google.com/maps/embed?pb=example",
            },
        )

        assert response.status_code == 302
        with app.app_context():
            updated = get_cinema_by_slug("capitolio")
            assert updated.address == "Rua dos Andradas, 736"
            assert updated.opening_hours == "Ter-Dom, 14h-22h"
            assert updated.instagram_url == "https://instagram.com/cinemateca.capitolio"

    def test_missing_name_shows_error(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id

        response = auth_headers.post(
            f"/admin/cinemas/{cinema_id}/update",
            data={"name": "", "url": "http://www.capitolio.org.br/"},
        )

        assert response.status_code == 200
        assert "obrigatório" in response.get_data(as_text=True)

    def test_uploads_photo(self, app, auth_headers, setup_cinemas):
        with app.app_context():
            cinema_id = get_cinema_by_slug("capitolio").id

        with (
            patch(
                "flask_backend.routes.admin.cinemas.validate_image",
                return_value=(True, None),
            ),
            patch(
                "flask_backend.routes.admin.cinemas.save_image",
                return_value=("photo.jpg", 100, 200),
            ),
        ):
            response = auth_headers.post(
                f"/admin/cinemas/{cinema_id}/update",
                data={
                    "name": "Cinemateca Capitólio",
                    "url": "http://www.capitolio.org.br/",
                    "cinema_photo": (io.BytesIO(b"fake-image-bytes"), "photo.jpg"),
                },
                content_type="multipart/form-data",
            )

        assert response.status_code == 302
        with app.app_context():
            updated = get_cinema_by_slug("capitolio")
            assert updated.photo == "photo.jpg"
            assert updated.photo_width == 100
            assert updated.photo_height == 200
