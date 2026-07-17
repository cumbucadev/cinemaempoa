import io
from unittest.mock import MagicMock, patch

from PIL import Image

from flask_backend.service.upload import (
    upload_image_to_api,
    upload_image_to_local_disk,
)


def _make_png_bytes(width=10, height=20):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


class TestUploadImageToApi:
    def test_upload_image_to_api_returns_url_and_dimensions(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "url": "https://imgbb.example/img.png",
                "width": 100,
                "height": 200,
            }
        }
        with patch(
            "flask_backend.service.upload.requests.post", return_value=mock_response
        ):
            url, width, height = upload_image_to_api(
                app=MagicMock(), image=io.BytesIO(b"fake-bytes")
            )

        mock_response.raise_for_status.assert_called_once()
        assert url == "https://imgbb.example/img.png"
        assert width == 100
        assert height == 200


class TestUploadImageToLocalDisk:
    def test_saves_via_file_save_when_available(self, tmp_path):
        app = MagicMock()
        app.config.get.return_value = str(tmp_path)

        png_bytes = _make_png_bytes(width=15, height=25)
        file = MagicMock()
        file.filename = "poster.png"

        def fake_save(path):
            with open(path, "wb") as f:
                f.write(png_bytes)

        file.save.side_effect = fake_save

        url, width, height = upload_image_to_local_disk(file, app)

        file.save.assert_called_once()
        assert url == "/screening/assets/poster.png"
        assert width == 15
        assert height == 25

    def test_falls_back_to_manual_write_when_save_unavailable(self, tmp_path):
        app = MagicMock()
        app.config.get.return_value = str(tmp_path)

        png_bytes = _make_png_bytes(width=30, height=40)
        # a plain BytesIO has no .save() method, forcing the AttributeError
        # fallback branch that manually opens and writes the file.
        file = io.BytesIO(png_bytes)

        url, width, height = upload_image_to_local_disk(
            file, app, filename="fallback.png"
        )

        assert url == "/screening/assets/fallback.png"
        assert width == 30
        assert height == 40

    def test_uses_explicit_filename_over_file_filename(self, tmp_path):
        app = MagicMock()
        app.config.get.return_value = str(tmp_path)

        png_bytes = _make_png_bytes()
        file = io.BytesIO(png_bytes)

        url, _, _ = upload_image_to_local_disk(file, app, filename="custom-name.png")

        assert url == "/screening/assets/custom-name.png"
