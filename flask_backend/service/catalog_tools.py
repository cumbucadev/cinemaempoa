"""The read-only catalog tools the conversational agent calls through the MCP
server in flask_backend/mcp_server.py: what is showing, where and when, and
what each cinema has shown. They only see published screenings
(`Screening.draft == False`) and raise CatalogToolError, with a pt-BR
message, when a call cannot be answered.
"""

import unicodedata
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel
from zoneinfo import ZoneInfo

from flask_backend.models import Cinema
from flask_backend.repository import catalog
from flask_backend.repository.cinemas import get_all as get_all_cinemas


class CatalogToolError(Exception):
    """A catalog tool call that cannot be answered. The message is in pt-BR
    and goes back to the agent."""


def today() -> date:
    """Today in Porto Alegre, whatever the container's time zone is."""
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def normalize(text: str) -> str:
    """`text` as the catalog compares it: no accents, no case, `-` and `_`
    read as spaces, and single spaces only."""
    decomposed = unicodedata.normalize("NFKD", text)
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(bare.casefold().replace("-", " ").replace("_", " ").split())


def parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise CatalogToolError(
            f"Data inválida: '{text}'. Use o formato AAAA-MM-DD."
        ) from exc


def _cinema_names(cinema: Cinema) -> set[str]:
    return {normalize(name) for name in (cinema.slug, cinema.name, cinema.short_name)}


def resolve_cinema(text: str) -> Cinema:
    """The cinema `text` names: the one whose slug, name or short name it
    equals, or else the only one it is part of."""
    wanted = normalize(text)
    cinemas = get_all_cinemas()
    exact = [cinema for cinema in cinemas if wanted in _cinema_names(cinema)]
    if exact:
        return exact[0]
    partial = [
        cinema
        for cinema in cinemas
        if any(wanted in name for name in _cinema_names(cinema))
    ]
    if len(partial) == 1:
        return partial[0]
    slugs = ", ".join(sorted(cinema.slug for cinema in cinemas))
    raise CatalogToolError(
        f"Cinema '{text}' não encontrado. Use um destes slugs: {slugs}."
    )


def catalog_period() -> tuple[Optional[date], Optional[date]]:
    """The first and the last date the catalog has a published session on."""
    return catalog.catalog_period()


class MetadataCoverage(BaseModel):
    movies_total: int
    with_tmdb: int
    with_directors: int
    with_genres: int
    with_countries: int


def metadata_coverage() -> MetadataCoverage:
    """How many of the movies with a published screening carry each piece
    of metadata, so an empty answer can be told from a gap in the data."""
    movies = catalog.published_movies()
    return MetadataCoverage(
        movies_total=len(movies),
        with_tmdb=sum(movie.tmdb_id is not None for movie in movies),
        with_directors=sum(bool(movie.directors) for movie in movies),
        with_genres=sum(bool(movie.genres) for movie in movies),
        with_countries=sum(bool(movie.countries) for movie in movies),
    )
