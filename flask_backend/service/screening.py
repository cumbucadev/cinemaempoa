import hashlib
import imghdr
import os
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Tuple

import requests
from PIL import Image
from werkzeug.utils import secure_filename

from flask_backend.env_config import APP_ENVIRONMENT
from flask_backend.import_json import ScrappedCinema, ScrappedFeature, ScrappedResult
from flask_backend.models import ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.movies import (
    get_by_title_or_create as get_movie_by_title_or_create,
)
from flask_backend.repository.screenings import (
    create as create_screening,
    get_by_movie_id_and_cinema_id as get_screening_by_movie_id_and_cinema_id,
    update_screening_dates,
)
from flask_backend.service.upload import upload_image_to_api, upload_image_to_local_disk
from flask_backend.utils.enums.environment import EnvironmentEnum

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


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
        return (False, "Arquivo corrompido ou inválido.")
    return True, None


def save_image(file, app, filename: Optional[str] = None) -> Tuple[str, int, int]:
    """Saves the received `file` into disk or uploads it to imgBB API,
    depending on the current environment"""
    # always save images locally on development
    if APP_ENVIRONMENT == EnvironmentEnum.DEVELOPMENT:
        return upload_image_to_local_disk(file, app, filename)
    # on production, attempt to save to the imgBB API
    try:
        return upload_image_to_api(app, file)
    # on failure, save locally
    except requests.exceptions.HTTPError:
        file.seek(0)
        return upload_image_to_local_disk(file, app, filename)


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


def download_image_from_url(image_url) -> Tuple[Optional[BytesIO], Optional[str]]:
    if image_url is None:
        return None, None
    file_extension = image_url.split(".")[-1]
    file_name = hashlib.md5(image_url.encode("utf-8")).hexdigest() + "." + file_extension

    r = requests.get(image_url)
    if r.ok is False:
        return None, None

    return BytesIO(r.content), file_name


def get_img_filename_from_url(image_url) -> str:
    file_extension = image_url.split(".")[-1]
    return secure_filename(
        hashlib.md5(image_url.encode("utf-8")).hexdigest() + "." + file_extension
    )


def get_img_path_from_filename(file_name, app) -> Optional[str]:
    """returns image path if image from given url already exists locally,
    None otherwise"""
    img_path = os.path.join(app.config.get("UPLOAD_FOLDER"), file_name)
    if os.path.exists(img_path):
        return img_path
    return None


def get_image_metadata(img_path):
    with open(img_path, "rb") as f:
        loaded_image = Image.open(f)
    return loaded_image.width, loaded_image.height


def import_scrapped_results(scrapped_results: ScrappedResult, current_app):
    created_features = 0
    scrapped_cinema: ScrappedCinema
    for scrapped_cinema in scrapped_results.cinemas:
        cinema = get_cinema_by_slug(scrapped_cinema.slug)
        scrapped_feature: ScrappedFeature
        for scrapped_feature in scrapped_cinema.features:
            movie = get_movie_by_title_or_create(scrapped_feature.title)

            description: str = ""
            screenings_dates = None
            if scrapped_feature.time:
                screenings_dates = build_dates(scrapped_feature.time)
            if scrapped_feature.original_title:
                description += f"\n{scrapped_feature.original_title.strip()}"
            if scrapped_feature.price:
                description += f"\n{scrapped_feature.price}"
            if scrapped_feature.director:
                description += f"\n{scrapped_feature.director}"
            if scrapped_feature.classification:
                description += f"\n{scrapped_feature.classification}"
            if scrapped_feature.general_info:
                description += f"\n{scrapped_feature.general_info}"
            if scrapped_feature.excerpt:
                description += f"\n{scrapped_feature.excerpt}"

            if screenings_dates is None:
                screenings_dates = build_dates(
                    [datetime.now().strftime("%Y-%m-%dT%H:%M")]
                )

            image_filename, image_width, image_height = None, None, None
            if scrapped_feature.poster:
                img, filename = download_image_from_url(scrapped_feature.poster)
                image_filename, image_width, image_height = None, None, None
                if img is not None:
                    # if we fail to download or validate the image, just ignore it for now
                    image_filename, image_width, image_height = save_image(
                        img, current_app, filename
                    )
            screening = get_screening_by_movie_id_and_cinema_id(movie.id, cinema.id)
            if not screening:
                create_screening(
                    movie.id,
                    description,
                    cinema.id,
                    screenings_dates,
                    image_filename,
                    image_width,
                    image_height,
                    True,
                )
            else:
                # create new ScreeningDate objects from existing ones
                # to prevent reference errors
                existing_dates = build_dates(
                    [f"{sd.date}T{sd.time}" for sd in screening.dates]
                )
                # append new dates to the list by checking if there is no
                # other date with an equal date and time fields
                for new_date in screenings_dates:
                    already_registered = False
                    for existing_date in existing_dates:
                        same_date = existing_date.date == new_date.date
                        same_time = existing_date.time == new_date.time
                        if same_date and same_time:
                            already_registered = True
                            break
                    if not already_registered:
                        existing_dates.append(new_date)
                update_screening_dates(screening, existing_dates)
            created_features += 1
    return created_features
