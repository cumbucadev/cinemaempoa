import io

from PIL import Image

from flask_backend.service.image_processing import resize_for_display


def _make_image_bytes(width, height, mode="RGB", fmt="PNG", color=(120, 60, 200)):
    buffer = io.BytesIO()
    Image.new(mode, (width, height), color=color).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer.read()


class TestResizeForDisplay:
    def test_downscales_when_longer_edge_exceeds_max_dimension(self):
        source = _make_image_bytes(2000, 1000)

        result = resize_for_display(source, max_dimension=1200)

        image = Image.open(io.BytesIO(result))
        assert image.size == (1200, 600)

    def test_does_not_upscale_smaller_images(self):
        source = _make_image_bytes(400, 300)

        result = resize_for_display(source, max_dimension=1200)

        image = Image.open(io.BytesIO(result))
        assert image.size == (400, 300)

    def test_output_is_webp(self):
        source = _make_image_bytes(500, 500)

        result = resize_for_display(source)

        image = Image.open(io.BytesIO(result))
        assert image.format == "WEBP"

    def test_preserves_alpha_channel(self):
        source = _make_image_bytes(
            300, 300, mode="RGBA", fmt="PNG", color=(10, 20, 30, 128)
        )

        result = resize_for_display(source)

        image = Image.open(io.BytesIO(result))
        assert image.mode == "RGBA"

    def test_flattens_palette_mode_without_error(self):
        buffer = io.BytesIO()
        Image.new("P", (200, 200)).save(buffer, format="PNG")
        buffer.seek(0)
        source = buffer.read()

        result = resize_for_display(source)

        image = Image.open(io.BytesIO(result))
        assert image.format == "WEBP"

    def test_higher_quality_produces_larger_output(self):
        source = _make_image_bytes(800, 800, color=(200, 40, 90))

        low = resize_for_display(source, quality=10)
        high = resize_for_display(source, quality=95)

        assert len(high) > len(low)

    def test_uses_longest_edge_for_portrait_images(self):
        source = _make_image_bytes(900, 1600)

        result = resize_for_display(source, max_dimension=1200)

        image = Image.open(io.BytesIO(result))
        assert image.size == (675, 1200)
