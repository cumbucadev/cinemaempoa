import hashlib
import logging
import os
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Dict, List, Optional, Set, Tuple

import filetype
import requests
from PIL import Image, UnidentifiedImageError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from werkzeug.utils import secure_filename

from flask_backend.env_config import APP_ENVIRONMENT
from flask_backend.import_json import ScrappedCinema, ScrappedFeature, ScrappedResult
from flask_backend.models import Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.movies import (
    get_by_title_or_create as get_movie_by_title_or_create,
)
from flask_backend.repository.screenings import (
    create as create_screening,
    get_by_movie_id_and_cinema_id as get_screening_by_movie_id_and_cinema_id,
    get_latest_screening_for_movie,
    get_screening_dates_for_movies,
    get_screenings_for_movies_with_dates_in_range,
    update_screening_dates,
    update_title_cleaning_info,
)
from flask_backend.service.shared import is_screening_date_upcoming
from flask_backend.service.title_cleaning import clean_title
from flask_backend.service.upload import upload_image_to_api, upload_image_to_local_disk
from flask_backend.utils.enums.environment import EnvironmentEnum

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

_WEEKDAY_NAMES_PT = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]


def format_day_label(day: date, today: date) -> str:
    """Portuguese label for a reels-feed day-boundary card: "Hoje, DD/MM",
    "Amanhã, DD/MM", or "<Weekday>, DD/MM" for later days."""
    formatted_date = day.strftime("%d/%m")
    if day == today:
        return f"Hoje, {formatted_date}"
    if day == today + timedelta(days=1):
        return f"Amanhã, {formatted_date}"
    return f"{_WEEKDAY_NAMES_PT[day.weekday()]}, {formatted_date}"


def _check_if_actually_image(file):
    header = file.read(512)
    file.seek(0)
    format = filetype.guess_extension(header)
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
    if APP_ENVIRONMENT != EnvironmentEnum.PRODUCTION:
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
        # Remove seconds from the string before parsing
        screening_date = screening_date[:16]  # Keeps up to YYYY-MM-DDTHH:MM
        try:
            parsed_screening_date = datetime.strptime(screening_date, "%Y-%m-%dT%H:%M")
        except ValueError:
            parsed_screening_date = datetime.strptime(screening_date, "%Y-%m-%d %H:%M")
        screening_date_objects.append(
            ScreeningDate(
                date=parsed_screening_date.date(),
                time=str(parsed_screening_date.time())[0:5],
            )
        )
    return screening_date_objects


def group_screening_dates_by_day(
    screening_dates: List[ScreeningDate], days: List[date]
) -> "OrderedDict[date, List[ScreeningDate]]":
    """Buckets an already date/time-ordered flat list of ScreeningDate by
    their .date field. Every date in `days` gets a (possibly empty) entry,
    in the given order."""
    buckets: "OrderedDict[date, List[ScreeningDate]]" = OrderedDict(
        (day, []) for day in days
    )
    for screening_date in screening_dates:
        if screening_date.date in buckets:
            buckets[screening_date.date].append(screening_date)
    return buckets


def get_soonest_date_in_range(
    screening_dates: List[ScreeningDate], start_date: date, end_date: date
) -> ScreeningDate:
    """Earliest ScreeningDate within [start_date, end_date]. Assumes at
    least one date in screening_dates falls in that range."""
    in_range = [d for d in screening_dates if start_date <= d.date <= end_date]
    return min(in_range, key=lambda d: (d.date, d.time or ""))


def build_reels_feed(
    screenings: List[Screening],
    movie_dates: List[ScreeningDate],
    today: date,
    window_end: date,
    user_logged_in: bool,
    earliest_datetime: Optional[datetime] = None,
    wanted_movie_ids: Optional[Set[int]] = None,
) -> List[dict]:
    """Builds the mobile reels feed: one card per non-draft screening (all
    screenings if user_logged_in), sorted by each screening's soonest
    future ScreeningDate within [today, window_end]. `movie_dates` is the
    flat, cross-cinema list of ScreeningDate rows for every movie present in
    `screenings` within the same window - grouped here per movie for each
    card's "next dates" list. `wanted_movie_ids` marks cards for the
    current anonymous visitor's want-to-watch picks (see
    docs/superpowers/specs/2026-07-26-want-to-watch-design.md)."""
    if earliest_datetime is None:
        earliest_datetime = datetime.combine(today, time.min)
    if wanted_movie_ids is None:
        wanted_movie_ids = set()

    dates_by_movie: Dict[int, List[ScreeningDate]] = defaultdict(list)
    for screening_date in movie_dates:
        if is_screening_date_upcoming(screening_date, earliest_datetime):
            dates_by_movie[screening_date.screening.movie_id].append(screening_date)

    cards = []
    for screening in screenings:
        if screening.draft and not user_logged_in:
            continue
        future_dates = [
            d
            for d in screening.dates
            if today <= d.date <= window_end
            and is_screening_date_upcoming(d, earliest_datetime)
        ]
        if not future_dates:
            continue
        soonest = min(future_dates, key=lambda d: (d.date, d.time or ""))
        next_dates = sorted(
            dates_by_movie.get(screening.movie_id, []),
            key=lambda d: (d.date, d.time or ""),
        )
        cards.append(
            {
                "screening_id": screening.id,
                "movie_id": screening.movie_id,
                "movie_title": screening.movie.title,
                "directors": [director.name for director in screening.movie.directors],
                "release_year": screening.movie.release_year,
                "description": screening.description,
                "image": screening.image,
                "image_alt": screening.image_alt,
                "cinema_name": screening.cinema.short_name,
                "cinema_color": screening.cinema.color,
                "soonest_date": soonest.date,
                "soonest_time": soonest.time,
                "next_dates": [
                    {
                        "date": screening_date.date,
                        "time": screening_date.time,
                        "cinema_name": screening_date.screening.cinema.short_name,
                    }
                    for screening_date in next_dates
                ],
                "draft": screening.draft,
                "screening_url": screening.url,
                "wanted": screening.movie_id in wanted_movie_ids,
            }
        )

    cards.sort(key=lambda card: (card["soonest_date"], card["soonest_time"] or ""))

    for card in cards:
        card["day_label"] = format_day_label(card["soonest_date"], today)

    return cards


_FAR_FUTURE_DATE = date(9999, 12, 31)


def build_favorites_feed(
    movie_ids: List[int],
    today: date,
    user_logged_in: bool,
    now: Optional[datetime] = None,
) -> List[dict]:
    """Builds the /favoritos feed: every marked movie, sorted the same way
    as the reels feed. A marked movie with an upcoming ScreeningDate gets a
    normal reels card (any future date, unlike the homepage's 7-day
    window - this is a personal list, not a "what's on this week" feed). A
    marked movie with none falls back to its most recent past Screening,
    with no_sessions=True and no dates. For anonymous visitors that fallback
    is the most recent *non-draft* Screening, so a movie never silently
    drops off the list just because its newest Screening row happens to be
    an unpublished draft; a movie with no non-draft Screening at all is
    skipped entirely when not logged in, same as everywhere else drafts are
    visitor-hidden. Logged-in users see the true latest regardless of draft
    status."""
    if not movie_ids:
        return []
    if now is None:
        now = datetime.now()

    screenings = get_screenings_for_movies_with_dates_in_range(
        movie_ids, today, _FAR_FUTURE_DATE
    )
    movie_dates = get_screening_dates_for_movies(
        movie_ids, today, _FAR_FUTURE_DATE, include_drafts=user_logged_in
    )
    cards = build_reels_feed(
        screenings,
        movie_dates,
        today,
        _FAR_FUTURE_DATE,
        user_logged_in,
        earliest_datetime=now,
        wanted_movie_ids=set(movie_ids),
    )
    for card in cards:
        card["no_sessions"] = False

    covered_movie_ids = {card["movie_id"] for card in cards}
    for movie_id in movie_ids:
        if movie_id in covered_movie_ids:
            continue
        stale_screening = get_latest_screening_for_movie(
            movie_id, include_drafts=user_logged_in
        )
        if stale_screening is None:
            continue
        # defensive: get_latest_screening_for_movie already excludes drafts
        # when include_drafts is False, so this should be unreachable here.
        if stale_screening.draft and not user_logged_in:
            continue
        cards.append(
            {
                "screening_id": stale_screening.id,
                "movie_id": stale_screening.movie_id,
                "movie_title": stale_screening.movie.title,
                "directors": [
                    director.name for director in stale_screening.movie.directors
                ],
                "release_year": stale_screening.movie.release_year,
                "description": stale_screening.description,
                "image": stale_screening.image,
                "image_alt": stale_screening.image_alt,
                "cinema_name": stale_screening.cinema.short_name,
                "cinema_color": stale_screening.cinema.color,
                "soonest_date": None,
                "soonest_time": None,
                "next_dates": [],
                "draft": stale_screening.draft,
                "screening_url": stale_screening.url,
                "day_label": None,
                "no_sessions": True,
                "wanted": True,
            }
        )

    return cards


def download_image_from_url(image_url) -> Tuple[Optional[BytesIO], Optional[str]]:
    if image_url is None:
        return None, None
    file_extension = image_url.split(".")[-1]
    file_name = (
        hashlib.md5(image_url.encode("utf-8")).hexdigest() + "." + file_extension
    )

    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    r = session.get(image_url)
    if r.ok is False:
        return None, None

    image_bytes = BytesIO(r.content)

    # test that the return is a valid image
    try:
        Image.open(image_bytes)
        image_bytes.seek(0)
    except UnidentifiedImageError:
        return None, None
    return image_bytes, file_name


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


@dataclass
class ImportSummary:
    movies_created: int
    screenings_created: int
    dates_registered: int


def import_scrapped_results(
    scrapped_results: ScrappedResult, current_app, pipeline_run_id: Optional[int] = None
) -> ImportSummary:
    movies_created = 0
    screenings_created = 0
    dates_registered = 0
    scrapped_cinema: ScrappedCinema
    for scrapped_cinema in scrapped_results.cinemas:
        cinema = get_cinema_by_slug(scrapped_cinema.slug)
        scrapped_feature: ScrappedFeature
        for scrapped_feature in scrapped_cinema.features:
            title_cleaning_result = clean_title(scrapped_feature.title)
            if title_cleaning_result.changed:
                logger.info(
                    "Título limpo na importação: '%s' -> '%s' (regras: %s)",
                    title_cleaning_result.raw_title,
                    title_cleaning_result.cleaned_title,
                    ", ".join(title_cleaning_result.matched_rules),
                )
            movie, movie_created = get_movie_by_title_or_create(
                title_cleaning_result.cleaned_title, pipeline_run_id=pipeline_run_id
            )
            if movie_created:
                movies_created += 1

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

            description = description.strip()

            if screenings_dates is None:
                screenings_dates = build_dates(
                    [datetime.now().strftime("%Y-%m-%dT%H:%M")]
                )
            screening = get_screening_by_movie_id_and_cinema_id(movie.id, cinema.id)

            if not screening:
                # only attempt to download the poster if the screening doesn't previously exists
                img, image_filename, image_width, image_height = None, None, None, None
                if scrapped_feature.poster:
                    img, filename = download_image_from_url(scrapped_feature.poster)

                if img is not None:
                    # if we fail to download or validate the image, just ignore it for now
                    image_filename, image_width, image_height = save_image(
                        img, current_app, filename
                    )

                create_screening(
                    movie_id=movie.id,
                    description=description,
                    cinema_id=cinema.id,
                    screening_dates=screenings_dates,
                    image=image_filename,
                    image_width=image_width,
                    image_height=image_height,
                    is_draft=False,
                    image_alt=None,
                    url_origin=scrapped_feature.read_more,
                    raw_title=title_cleaning_result.raw_title,
                    title_cleaning_rules=",".join(title_cleaning_result.matched_rules)
                    or None,
                    pipeline_run_id=pipeline_run_id,
                )
                screenings_created += 1
            else:
                update_title_cleaning_info(
                    screening,
                    title_cleaning_result.raw_title,
                    title_cleaning_result.matched_rules,
                )
                # captured before any of the filtering below mutates what
                # "existing" means, so it reflects what was truly on file
                # before this run - see issue #249
                original_date_time_pairs = {
                    (sd.date, sd.time) for sd in screening.dates
                }
                if cinema.slug == "capitolio":
                    # capitolio may occasionally change
                    # screening times for a given movie
                    # so records for any given day could become obsolete
                    # our strategy is, for every day included in the current run,
                    # we delete existing records and trust the new ones
                    # see issue #163

                    # ex. existing_dates_for_screening = [ 12/12/2025, 13/12/2025, 14/12/2025 ]
                    existing_dates_for_screening = list(screening.dates)

                    # ex. [13/12/2025, 14/12/2025]
                    received_dates_for_screening = [sd.date for sd in screenings_dates]

                    # we skip screening_dates for dates in the
                    # `received_dates_for_screening` list, so they can be recreated
                    # ex. existing_dates = [ 12/12/2025 ]
                    existing_dates = build_dates(
                        [
                            f"{sd.date}T{sd.time}"
                            for sd in existing_dates_for_screening
                            if sd.date not in received_dates_for_screening
                        ]
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

                got_new_date = any(
                    (nd.date, nd.time) not in original_date_time_pairs
                    for nd in screenings_dates
                )
                if got_new_date:
                    dates_registered += 1
    return ImportSummary(
        movies_created=movies_created,
        screenings_created=screenings_created,
        dates_registered=dates_registered,
    )
