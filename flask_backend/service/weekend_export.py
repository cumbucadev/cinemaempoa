"""Renders the weekend screening program as share-ready PNG images
(Instagram 4:5 portrait), one per day, splitting a day into multiple
numbered images when its screening list doesn't fit in a single image."""

import base64
import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from io import BytesIO
from typing import List

from PIL import Image, ImageDraw, ImageFont

from flask_backend.models import ScreeningDate
from flask_backend.service.screening import group_screening_dates_by_day

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
