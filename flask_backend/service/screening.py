import imghdr
import os

from datetime import datetime
from PIL import Image
from typing import List
from werkzeug.utils import secure_filename

from flask_backend.models import ScreeningDate

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}


def _check_if_actually_image(file):
    header = file.read(512)
    file.seek(0)
    format = imghdr.what(None, header)
    return format in ALLOWED_EXTENSIONS


def _allowed_extension(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_image(file) -> tuple[bool, str]:
    """Receives an uploaded file and returns whether it is valid
    based on the application rules"""
    filename = secure_filename(file.filename)
    if not _allowed_extension(filename):
        return (
            False,
            f"Extensão do arquivo inválida. Aceitamos {', '.join(ALLOWED_EXTENSIONS)}.",
        )
    if not _check_if_actually_image(file.stream):
        return (False, f"Arquivo corrompido ou inválido.")
    return True, None


def save_image(file, app) -> str:
    """Saves the received `file` into disk, returning the filename and image's width."""
    filename = secure_filename(file.filename)
    img_savepath = os.path.join(app.config.get("UPLOAD_FOLDER"), filename)
    file.save(img_savepath)
    with open(img_savepath, "rb") as f:
        loaded_image = Image.open(f)
    return filename, loaded_image.width, loaded_image.height


def build_dates(screening_dates: List[str]) -> List[ScreeningDate]:
    """Receives a list of datetime strings in format ['2023-11-11T19:00', '2023-11-11T19:00']
    and returns a list of ScreeningDate objects.

    Raises
        ValueError: string elements in received list are not in %Y-%m-%dT%H:%M format"""
    screening_date_objects = []
    for screening_date in screening_dates:
        parsed_screening_date = datetime.strptime(screening_date, "%Y-%m-%dT%H:%M")
        screening_date_objects.append(
            ScreeningDate(
                date=parsed_screening_date.date(),
                time=str(parsed_screening_date.time())[0:5],
            )
        )
    return screening_date_objects
