"""Renders the weekend screening program as share-ready PNG images
(Instagram 4:5 portrait), one per day, splitting a day into multiple
numbered images when its screening list doesn't fit in a single image."""

import base64
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from io import BytesIO
from math import ceil
from typing import List, Optional

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from flask_backend.models import ScreeningDate
from flask_backend.service.screening import group_screening_dates_by_day

logger = logging.getLogger(__name__)

LOCAL_ASSET_PREFIX = "/screening/assets/"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350

MARGIN_X = 60
MARGIN_TOP = 60
MARGIN_BOTTOM = 60

HEADER_HEIGHT = 140
COLUMN_HEADER_HEIGHT = 70
FOOTER_HEIGHT = 60

ROW_VERTICAL_PADDING = 16
LINE_SPACING = 6
MAX_TITLE_LINES = 3

COLUMN_GAP = 20
COLUMN_WIDTHS = {
    "movie": 520,
    "cinema": 260,
    "time": 140,
}

BG_COLOR = (255, 255, 255)
STRIPE_COLOR = (245, 245, 245)
ROW_DIVIDER_COLOR = (222, 222, 222)
HEADER_COLOR = (20, 20, 20)
TEXT_COLOR = (40, 40, 40)
FOOTER_TEXT_COLOR = (130, 130, 130)

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts")
FONT_REGULAR_PATH = os.path.join(FONT_DIR, "FiraSans-Regular.ttf")
FONT_BOLD_PATH = os.path.join(FONT_DIR, "FiraSans-Bold.ttf")

FONT_SIZE_HEADER = 44
FONT_SIZE_SUBHEADER = 28
FONT_SIZE_COLUMN_HEADER = 26
FONT_SIZE_ROW = 24
FONT_SIZE_FOOTER = 20

WATERMARK_TEXT = "cinemaempoa.com.br"

COVER_TITLE_TEXT = "Programação Final de Semana"
FONT_SIZE_COVER_TITLE = 64
FONT_SIZE_COVER_SUBTITLE = 34
COVER_BLUR_RADIUS = 3
COVER_SCRIM_PEAK_ALPHA = 170
COVER_BG_COLOR = (25, 25, 25)

POSTER_LOAD_TIMEOUT_SECONDS = 5
COVER_POSTER_LOAD_BUDGET_SECONDS = 15
MAX_COVER_TILES = 25
POSTER_LOAD_POOL_SIZE = 8

DAY_DEFS = [
    ("friday", "Sexta-feira"),
    ("saturday", "Sábado"),
    ("sunday", "Domingo"),
]

_MONTH_NAMES_PT = {
    1: "janeiro",
    2: "fevereiro",
    3: "março",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}


def _format_weekend_date_range(
    friday_date: date, saturday_date: date, sunday_date: date
) -> str:
    """Formats the three weekend dates as a natural-language Portuguese
    range, e.g. "7, 8 e 9 de agosto". Groups consecutive same-month dates
    together, so a weekend crossing a month boundary (e.g. the last
    weekend of a month) reads as "31 de julho, 1 e 2 de agosto"."""
    dates = [friday_date, saturday_date, sunday_date]

    groups: List[List[date]] = []
    for current_date in dates:
        if groups and groups[-1][-1].month == current_date.month:
            groups[-1].append(current_date)
        else:
            groups.append([current_date])

    parts = []
    for group in groups:
        days = [str(d.day) for d in group]
        month_name = _MONTH_NAMES_PT[group[-1].month]
        day_text = days[0] if len(days) == 1 else f"{', '.join(days[:-1])} e {days[-1]}"
        parts.append(f"{day_text} de {month_name}")

    return ", ".join(parts)


@dataclass
class RowData:
    movie_title: str
    cinema_name: str
    time_label: str


@dataclass
class RowLayout:
    row: RowData
    movie_lines: List[str]
    height: int


@dataclass
class ExportedDayImages:
    day_key: str
    day_label: str
    day_date: date
    images_base64: List[str] = field(default_factory=list)


@dataclass
class CoverMovie:
    movie_id: int
    image_path: str


def _available_rows_height() -> int:
    return (
        CANVAS_HEIGHT
        - MARGIN_TOP
        - HEADER_HEIGHT
        - COLUMN_HEADER_HEIGHT
        - FOOTER_HEIGHT
        - MARGIN_BOTTOM
    )


def _build_row_data(screening_date: ScreeningDate) -> RowData:
    return RowData(
        movie_title=screening_date.screening.movie.title.strip(),
        cinema_name=screening_date.screening.cinema.short_name,
        time_label=screening_date.time.replace(":", "h"),
    )


def _collect_cover_movies(screening_dates: List[ScreeningDate]) -> List[CoverMovie]:
    """Deduplicates screening_dates into one CoverMovie per distinct movie,
    keeping the image from the first occurrence in weekend order (the list
    is assumed already date/time-ordered, same as build_weekend_export_images
    expects). Screenings with no image are skipped entirely."""
    seen_movie_ids = set()
    movies: List[CoverMovie] = []
    for screening_date in screening_dates:
        screening = screening_date.screening
        image_path = screening.image
        if not image_path:
            continue
        movie_id = screening.movie.id
        if movie_id in seen_movie_ids:
            continue
        seen_movie_ids.add(movie_id)
        movies.append(CoverMovie(movie_id=movie_id, image_path=image_path))
    return movies


@lru_cache(maxsize=None)
def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent + LINE_SPACING


def _hard_split(
    draw: ImageDraw.ImageDraw, word: str, font: ImageFont.FreeTypeFont, max_width: int
) -> List[str]:
    """Splits a single word (too wide to fit max_width on its own) char by
    char so pagination always makes progress."""
    parts: List[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            parts.append(current)
            current = char
    if current:
        parts.append(current)
    return parts


def _wrap_text_to_width(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> List[str]:
    """Greedy word-wrap using real font metrics. A single word wider than
    max_width is hard-split character by character."""
    words = text.split()
    if not words:
        return [""]

    lines: List[str] = []
    current_line = ""
    for word in words:
        candidate = f"{current_line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current_line = candidate
            continue
        if current_line:
            lines.append(current_line)
            current_line = ""
        if draw.textlength(word, font=font) > max_width:
            split_parts = _hard_split(draw, word, font, max_width)
            lines.extend(split_parts[:-1])
            current_line = split_parts[-1]
        else:
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def _wrap_and_truncate_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> List[str]:
    """Wraps text, then if it exceeds max_lines, truncates the last line and
    appends an ellipsis so a row's height is always bounded by
    max_lines * line_height, guaranteeing pagination progress."""
    lines = _wrap_text_to_width(draw, text, font, max_width)
    if len(lines) <= max_lines:
        return lines

    truncated = lines[:max_lines]
    last_line = truncated[-1]
    ellipsis = "…"
    while last_line and draw.textlength(last_line + ellipsis, font=font) > max_width:
        last_line = last_line[:-1].rstrip()
    truncated[-1] = f"{last_line}{ellipsis}" if last_line else ellipsis
    return truncated


def _measure_row(
    draw: ImageDraw.ImageDraw, row: RowData, font_row: ImageFont.FreeTypeFont
) -> RowLayout:
    lines = _wrap_and_truncate_title(
        draw, row.movie_title, font_row, COLUMN_WIDTHS["movie"], MAX_TITLE_LINES
    )
    text_height = len(lines) * _line_height(font_row)
    height = text_height + 2 * ROW_VERTICAL_PADDING
    return RowLayout(row=row, movie_lines=lines, height=height)


def _distribute_counts(total: int, buckets: int) -> List[int]:
    """Splits `total` items into `buckets` near-equal integer counts (each
    is `total // buckets` or one more), front-loading the remainder so
    leading buckets get the extra item. Used to spread tiles across grid
    rows so every row is exactly full - no row ever gets more than
    ceil(total / buckets) tiles."""
    base = total // buckets
    remainder = total % buckets
    return [base + 1] * remainder + [base] * (buckets - remainder)


def _grid_dimensions(movie_count: int) -> List[int]:
    """Picks a column tier from the number of movies (more movies -> more,
    narrower columns), then spreads tiles across rows (capped at 5) so
    every row is exactly full - a row with fewer tiles than the tier's
    column count gets proportionally bigger tiles instead of leaving blank
    cells. Returns row_counts (tiles per row, one entry per row); sum(row_
    counts) is the max number of tiles shown - movies beyond that are
    dropped by the caller (_collect_cover_movies already orders movies by
    weekend order, so earlier movies win)."""
    if movie_count <= 6:
        cols = 3
    elif movie_count <= 12:
        cols = 4
    else:
        cols = 5

    max_tiles = cols * 5
    tile_count = min(movie_count, max_tiles)
    rows = ceil(tile_count / cols)
    return _distribute_counts(tile_count, rows)


def _segment_lengths(total: int, count: int) -> List[int]:
    """Splits `total` pixels into `count` near-equal integer segments; any
    remainder from integer division is added to the last segment so the
    segments always sum exactly to `total`."""
    base = total // count
    lengths = [base] * count
    lengths[-1] += total - base * count
    return lengths


def _load_poster_bytes(image_path: str, upload_folder: str) -> Optional[bytes]:
    """Loads poster image bytes from either a local upload
    (/screening/assets/<filename>, served straight from disk) or a remote
    URL (production imgBB uploads). Returns None on any failure - missing
    file, network error, or bad response - so a single bad poster never
    breaks the whole cover image."""
    try:
        if image_path.startswith(LOCAL_ASSET_PREFIX):
            filename = image_path[len(LOCAL_ASSET_PREFIX) :]
            file_path = os.path.join(upload_folder, filename)
            with open(file_path, "rb") as f:
                return f.read()
        response = requests.get(image_path, timeout=POSTER_LOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.content
    except (OSError, requests.RequestException) as exc:
        logger.warning(
            "Falha ao carregar poster '%s' para a capa do fim de semana: %s",
            image_path,
            exc,
        )
        return None


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Center-crops (never distorts) `img` to exactly target_w x target_h,
    cropping whichever dimension has excess before resizing."""
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_w = round(src_h * target_ratio)
        offset = (src_w - new_w) // 2
        img = img.crop((offset, 0, offset + new_w, src_h))
    else:
        new_h = round(src_w / target_ratio)
        offset = (src_h - new_h) // 2
        img = img.crop((0, offset, src_w, offset + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def _load_and_decode_poster(
    movie: CoverMovie, upload_folder: str
) -> Optional[Image.Image]:
    """Downloads and decodes a single candidate's poster. Returns None on
    any download or decode failure (logged) rather than raising, so one bad
    poster never breaks the whole cover image."""
    poster_bytes = _load_poster_bytes(movie.image_path, upload_folder)
    if poster_bytes is None:
        return None
    try:
        return Image.open(BytesIO(poster_bytes)).convert("RGB")
    except Exception as exc:
        logger.warning(
            "Poster inválido para o filme %d na capa do fim de semana: %s",
            movie.movie_id,
            exc,
        )
        return None


def _load_cover_posters(
    movies: List[CoverMovie], upload_folder: str
) -> List[Image.Image]:
    """Downloads and decodes candidate posters in parallel (up to
    POSTER_LOAD_POOL_SIZE at a time), drawing from the full movie list -
    not just the first MAX_COVER_TILES - so a run of broken posters early
    in weekend order doesn't starve the grid. Order doesn't matter here:
    the caller only cares about ending up with as many usable posters as
    possible, as fast as possible. Stops as soon as MAX_COVER_TILES
    posters have loaded, cancelling any candidates still queued. The whole
    pass is bounded by COVER_POSTER_LOAD_BUDGET_SECONDS of wall-clock time
    so a slow/hanging image host can't pin the request indefinitely -
    whatever has already loaded by then is returned."""
    posters: List[Image.Image] = []
    executor = ThreadPoolExecutor(max_workers=POSTER_LOAD_POOL_SIZE)
    try:
        futures = [
            executor.submit(_load_and_decode_poster, movie, upload_folder)
            for movie in movies
        ]
        try:
            for future in as_completed(
                futures, timeout=COVER_POSTER_LOAD_BUDGET_SECONDS
            ):
                poster = future.result()
                if poster is not None:
                    posters.append(poster)
                    if len(posters) >= MAX_COVER_TILES:
                        break
        except TimeoutError:
            logger.warning(
                "Orçamento de tempo para carregar posters da capa do fim de "
                "semana excedido; usando os posters já carregados."
            )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return posters


def _compose_poster_grid(
    posters: List[Image.Image], row_counts: List[int]
) -> Image.Image:
    """Composites already-decoded posters into the CANVAS_WIDTH x
    CANVAS_HEIGHT mosaic. `row_counts` gives the number of tiles in each
    row - rows can hold different counts so every row is always exactly
    full, with narrower rows getting wider (bigger) tiles instead of
    leaving blank cells. Each poster is center-cropped to fill its cell
    without distortion. Assumes len(posters) == sum(row_counts)."""
    grid = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), COVER_BG_COLOR)
    row_heights = _segment_lengths(CANVAS_HEIGHT, len(row_counts))

    poster_iter = iter(posters)
    for row, row_tile_count in enumerate(row_counts):
        col_widths = _segment_lengths(CANVAS_WIDTH, row_tile_count)
        y = sum(row_heights[:row])
        for col, w in enumerate(col_widths):
            poster = next(poster_iter)
            x = sum(col_widths[:col])
            grid.paste(_cover_crop(poster, w, row_heights[row]), (x, y))

    return grid


def paginate_rows_for_day(rows: List[RowData]) -> List[List[RowLayout]]:
    """Greedily fills 1080x1350 "pages" (one PNG each) with rows for a
    single day, using real font metrics to size each row before packing.
    Rows are assumed to already be in the desired display order."""
    if not rows:
        return []

    dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    font_row = _load_font(FONT_REGULAR_PATH, FONT_SIZE_ROW)
    available_height = _available_rows_height()

    pages: List[List[RowLayout]] = []
    current_page: List[RowLayout] = []
    current_height = 0
    for row in rows:
        row_layout = _measure_row(dummy_draw, row, font_row)
        if current_page and current_height + row_layout.height > available_height:
            pages.append(current_page)
            current_page, current_height = [], 0
        current_page.append(row_layout)
        current_height += row_layout.height
    if current_page:
        pages.append(current_page)
    return pages


def render_day_image(
    day_label: str,
    day_date: date,
    rows_page: List[RowLayout],
    part_index: int,
    total_parts: int,
) -> bytes:
    """Draws one 1080x1350 canvas: header (day + date [+ part]), column
    headers + divider, striped rows, and the cinemaempoa.com.br footer
    watermark. Returns PNG-encoded bytes."""
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_header = _load_font(FONT_BOLD_PATH, FONT_SIZE_HEADER)
    font_subheader = _load_font(FONT_REGULAR_PATH, FONT_SIZE_SUBHEADER)
    font_col_header = _load_font(FONT_BOLD_PATH, FONT_SIZE_COLUMN_HEADER)
    font_row = _load_font(FONT_REGULAR_PATH, FONT_SIZE_ROW)
    font_footer = _load_font(FONT_REGULAR_PATH, FONT_SIZE_FOOTER)

    x_movie = MARGIN_X
    x_cinema = x_movie + COLUMN_WIDTHS["movie"] + COLUMN_GAP
    x_time = x_cinema + COLUMN_WIDTHS["cinema"] + COLUMN_GAP

    header_text = day_label
    if total_parts > 1:
        header_text = f"{day_label} ({part_index}/{total_parts})"
    draw.text((MARGIN_X, MARGIN_TOP), header_text, font=font_header, fill=HEADER_COLOR)
    date_text = day_date.strftime("%d/%m/%Y")
    draw.text(
        (MARGIN_X, MARGIN_TOP + _line_height(font_header) + 4),
        date_text,
        font=font_subheader,
        fill=TEXT_COLOR,
    )

    col_header_y = MARGIN_TOP + HEADER_HEIGHT
    draw.text((x_movie, col_header_y), "FILME", font=font_col_header, fill=HEADER_COLOR)
    draw.text(
        (x_cinema, col_header_y), "CINEMA", font=font_col_header, fill=HEADER_COLOR
    )
    draw.text(
        (x_time, col_header_y), "HORÁRIO", font=font_col_header, fill=HEADER_COLOR
    )
    divider_y = col_header_y + COLUMN_HEADER_HEIGHT - 12
    draw.line(
        [(MARGIN_X, divider_y), (CANVAS_WIDTH - MARGIN_X, divider_y)],
        fill=ROW_DIVIDER_COLOR,
        width=2,
    )

    y = MARGIN_TOP + HEADER_HEIGHT + COLUMN_HEADER_HEIGHT
    row_line_height = _line_height(font_row)
    for idx, row_layout in enumerate(rows_page):
        if idx % 2 == 1:
            draw.rectangle(
                [(0, y), (CANVAS_WIDTH, y + row_layout.height)], fill=STRIPE_COLOR
            )
        for line_idx, line in enumerate(row_layout.movie_lines):
            draw.text(
                (x_movie, y + ROW_VERTICAL_PADDING + line_idx * row_line_height),
                line,
                font=font_row,
                fill=TEXT_COLOR,
            )
        center_y = y + (row_layout.height - row_line_height) / 2
        draw.text(
            (x_cinema, center_y),
            row_layout.row.cinema_name,
            font=font_row,
            fill=TEXT_COLOR,
        )
        draw.text(
            (x_time, center_y),
            row_layout.row.time_label,
            font=font_row,
            fill=TEXT_COLOR,
        )
        y += row_layout.height
        draw.line(
            [(MARGIN_X, y), (CANVAS_WIDTH - MARGIN_X, y)],
            fill=ROW_DIVIDER_COLOR,
            width=1,
        )

    footer_y = CANVAS_HEIGHT - MARGIN_BOTTOM - FOOTER_HEIGHT / 2
    watermark_width = draw.textlength(WATERMARK_TEXT, font=font_footer)
    draw.text(
        ((CANVAS_WIDTH - watermark_width) / 2, footer_y),
        WATERMARK_TEXT,
        font=font_footer,
        fill=FOOTER_TEXT_COLOR,
    )

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def build_weekend_export_images(
    screening_dates: List[ScreeningDate],
    friday_date: date,
    saturday_date: date,
    sunday_date: date,
) -> List[ExportedDayImages]:
    """Groups screening_dates by weekday, then for each of Friday/Saturday/
    Sunday: builds row data, paginates, renders each page to PNG, and
    base64-encodes it. A day with zero screenings gets images_base64=[]."""
    day_dates = [friday_date, saturday_date, sunday_date]
    buckets = group_screening_dates_by_day(screening_dates, day_dates)

    results = []
    for (day_key, day_label), day_date in zip(DAY_DEFS, day_dates):
        rows = [_build_row_data(sd) for sd in buckets[day_date]]
        pages = paginate_rows_for_day(rows)
        images_b64 = [
            base64.b64encode(
                render_day_image(day_label, day_date, page, idx, len(pages))
            ).decode("ascii")
            for idx, page in enumerate(pages, start=1)
        ]
        results.append(ExportedDayImages(day_key, day_label, day_date, images_b64))
    return results


def _build_vertical_scrim(width: int, height: int, peak_alpha: int) -> Image.Image:
    """Black overlay, near-transparent at the top/bottom edges and darkest
    through the middle band, so centered title text stays readable over a
    busy poster grid without hiding the whole image."""
    scrim = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scrim)
    center = height / 2
    for y in range(height):
        distance = abs(y - center) / center
        alpha = max(int(peak_alpha * (1 - distance)), 0)
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    return scrim


def _draw_cover_text(img: Image.Image, subtitle_text: str) -> None:
    draw = ImageDraw.Draw(img)
    font_title = _load_font(FONT_BOLD_PATH, FONT_SIZE_COVER_TITLE)
    font_subtitle = _load_font(FONT_REGULAR_PATH, FONT_SIZE_COVER_SUBTITLE)

    title_lines = _wrap_text_to_width(
        draw, COVER_TITLE_TEXT, font_title, CANVAS_WIDTH - 2 * MARGIN_X
    )
    title_line_height = _line_height(font_title)
    subtitle_line_height = _line_height(font_subtitle)

    block_height = len(title_lines) * title_line_height + 16 + subtitle_line_height
    y = (CANVAS_HEIGHT - block_height) / 2

    for line in title_lines:
        line_width = draw.textlength(line, font=font_title)
        x = (CANVAS_WIDTH - line_width) / 2
        draw.text((x, y), line, font=font_title, fill=(255, 255, 255))
        y += title_line_height

    y += 16
    subtitle_width = draw.textlength(subtitle_text, font=font_subtitle)
    x = (CANVAS_WIDTH - subtitle_width) / 2
    draw.text((x, y), subtitle_text, font=font_subtitle, fill=(255, 255, 255))


def _draw_cover_watermark(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    font_footer = _load_font(FONT_REGULAR_PATH, FONT_SIZE_FOOTER)
    watermark_width = draw.textlength(WATERMARK_TEXT, font=font_footer)
    footer_y = CANVAS_HEIGHT - MARGIN_BOTTOM - FOOTER_HEIGHT / 2
    draw.text(
        ((CANVAS_WIDTH - watermark_width) / 2, footer_y),
        WATERMARK_TEXT,
        font=font_footer,
        fill=(255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0),
    )


def build_weekend_cover_image(
    screening_dates: List[ScreeningDate],
    upload_folder: str,
    friday_date: date,
    saturday_date: date,
    sunday_date: date,
) -> Optional[str]:
    """Builds the weekend's single base64 PNG cover image: a poster-grid
    mosaic of every distinct movie showing that weekend (first-seen poster
    wins), blurred with a dark scrim, and the "Programação Final de
    Semana" title + date subtitle centered on top. Returns None if no
    screening that weekend has a usable poster image.

    Posters are loaded before the grid is sized (see _load_cover_posters),
    so the layout always matches how many posters actually decoded - a
    weekend where several posters fail to load gets a smaller, denser grid
    instead of a grid sized for the full movie count with blank cells."""
    movies = _collect_cover_movies(screening_dates)
    if not movies:
        return None

    posters = _load_cover_posters(movies, upload_folder)
    if not posters:
        return None

    row_counts = _grid_dimensions(len(posters))
    tiles = posters[: sum(row_counts)]

    grid = _compose_poster_grid(tiles, row_counts)
    blurred = grid.filter(ImageFilter.GaussianBlur(COVER_BLUR_RADIUS)).convert("RGBA")
    scrim = _build_vertical_scrim(CANVAS_WIDTH, CANVAS_HEIGHT, COVER_SCRIM_PEAK_ALPHA)
    composited = Image.alpha_composite(blurred, scrim).convert("RGB")

    subtitle_text = _format_weekend_date_range(friday_date, saturday_date, sunday_date)
    _draw_cover_text(composited, subtitle_text)
    _draw_cover_watermark(composited)

    buffer = BytesIO()
    composited.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
