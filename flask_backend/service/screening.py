import hashlib
import imghdr
import os
import re
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Tuple

import requests
from PIL import Image
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


def save_image(file, app, filename: Optional[str] = None) -> Tuple[str, int, int]:
    """Saves the received `file` into disk, returning the filename and image's width."""
    if filename:
        filename = secure_filename(filename)
    else:
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


def parse_to_datetime_string(time_str: str) -> Optional[List[str]]:
    """Receives string in format:
    - \\n\\n\\nHorários: 12:00h\\n\\n\\n\\nSala de Cinema\\n\\n
    - 16h
    - 15h30/ 19h30
    - 15h/ 19h
    - 15h15
    - 13 de setembro | quarta-feira | 19h
    - 05 de setembro | terça-feira | 16h30

    Attempts to parse it into a list of strings in format:
    - ["2023-11-11T12:00"]"""
    today_date = datetime.strftime(datetime.now(), "%Y-%m-%d")
    if time_str is None or time_str == "":
        return []

    if time_str.startswith("\n\n\nHorários: "):
        stripped_time = time_str.strip("\n\n\nHorários: ").split("h")
        return [f"{today_date}T{stripped_time[0]}"]

    # check if time_str is in format DD de MMMM | dia-da-semana | HHhMM,
    # and save the match to a variable
    format_match = re.match(
        r"^\d{1,2} de \w+ \| [\w-]+ \| (\d{1,2}h?(?:\d{1,2})?)$", time_str
    )
    if format_match:
        split_match = format_match.group(1).split("h")
        if len(split_match) == 1 or split_match[1] == "":
            return [f"{today_date}T{split_match[0]}:00"]
        return [f"{today_date}T{split_match[0]}:{split_match[1]}"]

    # check if time_str is in format HHhMM using regex
    if re.match(r"^\d{1,2}h\d{1,2}$", time_str):
        return [f"{today_date}T{time_str[0:2]}:{time_str[-2:]}"]

    if "/" in time_str:
        split_time = time_str.split("/")
        formatted_time = []
        for time in split_time:
            if time.strip().endswith("h"):
                formatted_time.append(f"{today_date}T{time.strip()[:-1]}:00")
            else:
                hour_mins = time.strip().split("h")
                formatted_time.append(f"{today_date}T{hour_mins[0]}:{hour_mins[1]}")

        return formatted_time

    if time_str.strip().endswith("h"):
        return [f"{today_date}T{time_str[:-1]}:00"]

    return None


def download_image_from_url(image_url) -> Tuple[Optional[Image.Image], Optional[str]]:
    if image_url is None:
        return None, None
    file_extension = image_url.split(".")[-1]
    file_name = (
        hashlib.md5(image_url.encode("utf-8")).hexdigest() + "." + file_extension
    )
    r = requests.get(image_url)
    if r.ok is False:
        return None, None
    return Image.open(BytesIO(r.content)), file_name
