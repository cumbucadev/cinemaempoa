from io import BytesIO

from PIL import Image, ImageOps

# Modes WebP can't encode directly (or that would lose information encoding
# it directly, e.g. palette-indexed) - flatten to RGBA first.
_MODES_NEEDING_CONVERSION = {"P", "CMYK", "1", "L", "LA"}


def resize_for_display(
    image_bytes: bytes, max_dimension: int = 1200, quality: int = 80
) -> bytes:
    """Resizes an image so its longest edge is at most `max_dimension`
    pixels (never upscaling smaller images) and re-encodes it as WebP.

    This is the single normalization point every image the app stores
    passes through - see issue #229 and the design rationale at
    https://github.com/cumbucadev/cinemaempoa/pull/313#issuecomment-5229285256.
    """
    image = Image.open(BytesIO(image_bytes))
    image.load()
    image = ImageOps.exif_transpose(image)

    if image.mode in _MODES_NEEDING_CONVERSION or image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    width, height = image.size
    longest_edge = max(width, height)
    if longest_edge > max_dimension:
        scale = max_dimension / longest_edge
        new_size = (round(width * scale), round(height * scale))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    output = BytesIO()
    image.save(output, format="WEBP", quality=quality)
    return output.getvalue()
