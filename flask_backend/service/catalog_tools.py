"""The read-only catalog tools the conversational agent calls through the MCP
server in flask_backend/mcp_server.py: what is showing, where and when, and
what each cinema has shown. They only see published screenings
(`Screening.draft == False`) and raise CatalogToolError, with a pt-BR
message, when a call cannot be answered.
"""

import unicodedata
from collections import defaultdict
from datetime import date, datetime
from typing import Callable, Iterable, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import Row
from zoneinfo import ZoneInfo

from flask_backend.constants import CANONICAL_BASE_URL
from flask_backend.models import Cinema, Movie, Screening
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


def _given(text: Optional[str]) -> Optional[str]:
    """`text`, or None when it is blank: agents often send "" for a filter
    they do not mean to use."""
    return text if text and text.strip() else None


def _contains(needle: str, values: Iterable[Optional[str]]) -> bool:
    wanted = normalize(needle)
    return any(wanted in normalize(value) for value in values if value)


def _optional_date(text: Optional[str]) -> Optional[date]:
    return parse_date(text) if _given(text) else None


def _check_order(start: Optional[date], end: Optional[date]) -> None:
    if start and end and end < start:
        raise CatalogToolError(
            f"Período inválido: a data final ({end}) é anterior à inicial ({start})."
        )


def _sessions_in_scope(
    cinema: Optional[str], date_from: Optional[str], date_to: Optional[str]
) -> list[Row]:
    """The published session dates a call counts: those of `cinema`, when
    given, inside the period, when given."""
    start, end = _optional_date(date_from), _optional_date(date_to)
    _check_order(start, end)
    cinema_id = resolve_cinema(cinema).id if _given(cinema) else None
    return catalog.session_dates(cinema_id, start, end)


def _by_movie(sessions: Iterable[Row]) -> dict[int, list[Row]]:
    grouped = defaultdict(list)
    for session in sessions:
        grouped[session.movie_id].append(session)
    return grouped


def _cinema_slugs() -> dict[int, str]:
    return {cinema.id: cinema.slug for cinema in get_all_cinemas()}


def _clamp(limit: int, ceiling: int) -> int:
    return max(1, min(limit, ceiling))


def _movie_url(movie: Movie) -> Optional[str]:
    return f"{CANONICAL_BASE_URL}/movies/{movie.slug}" if movie.slug else None


def _names(rows) -> list[str]:
    return [row.name for row in rows]


SEARCH_MOVIES_MAX = 50

MovieSort = Literal["last_shown_desc", "first_shown_asc", "title"]


class MovieSummary(BaseModel):
    movie_id: int
    title: str
    original_title: Optional[str]
    release_year: Optional[int]
    directors: list[str]
    genres: list[str]
    countries: list[str]
    url: Optional[str]
    first_shown: date
    last_shown: Optional[date]
    next_showing: Optional[date]
    cinemas: list[str]
    sessions: int


class MovieSearchResult(BaseModel):
    today: date
    catalog_since: Optional[date]
    total: int
    truncated: bool
    movies: list[MovieSummary]


# What each text filter of search_movies is looked for in.
_TEXT_FILTERS: dict[str, Callable[[Movie], Iterable[Optional[str]]]] = {
    "title": lambda movie: (movie.title, movie.original_title),
    "director": lambda movie: _names(movie.directors),
    "genre": lambda movie: _names(movie.genres),
    "country": lambda movie: _names(movie.countries),
}


def _matches(movie: Movie, text_filters: dict[str, Optional[str]]) -> bool:
    return all(
        _contains(needle, _TEXT_FILTERS[name](movie))
        for name, needle in text_filters.items()
        if _given(needle)
    )


def _movie_summary(
    movie: Movie, sessions: list[Row], day: date, slugs: dict[int, str]
) -> MovieSummary:
    dates = [session.date for session in sessions]
    return MovieSummary(
        movie_id=movie.id,
        title=movie.title,
        original_title=movie.original_title,
        release_year=movie.release_year,
        directors=_names(movie.directors),
        genres=_names(movie.genres),
        countries=_names(movie.countries),
        url=_movie_url(movie),
        first_shown=min(dates),
        last_shown=max((d for d in dates if d <= day), default=None),
        next_showing=min((d for d in dates if d >= day), default=None),
        cinemas=sorted({slugs[session.cinema_id] for session in sessions}),
        sessions=len(sessions),
    )


def _by_last_shown(movie: MovieSummary) -> tuple:
    """Most recently shown first; movies only scheduled ahead go last,
    soonest first."""
    if movie.last_shown is None:
        return (1, movie.next_showing.toordinal(), movie.movie_id)
    return (0, -movie.last_shown.toordinal(), movie.movie_id)


_MOVIE_SORTS: dict[str, Callable[[MovieSummary], tuple]] = {
    "last_shown_desc": _by_last_shown,
    "first_shown_asc": lambda movie: (movie.first_shown, movie.movie_id),
    "title": lambda movie: (normalize(movie.title), movie.movie_id),
}


def search_movies(
    title: Optional[str] = None,
    director: Optional[str] = None,
    genre: Optional[str] = None,
    country: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    cinema: Optional[str] = None,
    shown_from: Optional[str] = None,
    shown_to: Optional[str] = None,
    sort: MovieSort = "last_shown_desc",
    limit: int = 10,
) -> MovieSearchResult:
    """The movies matching every given filter. `cinema`, `shown_from` and
    `shown_to` pick the session dates that count: a movie needs at least one
    of them, and its dates, cinemas and session count only cover those."""
    day = today()
    sessions = _by_movie(_sessions_in_scope(cinema, shown_from, shown_to))
    slugs = _cinema_slugs()
    text_filters = {
        "title": title,
        "director": director,
        "genre": genre,
        "country": country,
    }
    found = sorted(
        (
            _movie_summary(movie, sessions[movie.id], day, slugs)
            for movie in catalog.movies_by_ids(sessions, year_from, year_to)
            if _matches(movie, text_filters)
        ),
        key=_MOVIE_SORTS[sort],
    )
    kept = found[: _clamp(limit, SEARCH_MOVIES_MAX)]
    return MovieSearchResult(
        today=day,
        catalog_since=catalog_period()[0],
        total=len(found),
        truncated=len(found) > len(kept),
        movies=kept,
    )


SCHEDULE_MAX_DAYS = 14
SCHEDULE_MAX_PAIRS = 60


class DaySessions(BaseModel):
    date: date
    times: list[str]


class ScheduledMovie(BaseModel):
    movie_id: int
    title: str
    directors: list[str]
    genres: list[str]
    url: Optional[str]
    sessions: list[DaySessions]


class CinemaSchedule(BaseModel):
    slug: str
    name: str
    movies: list[ScheduledMovie]


class Schedule(BaseModel):
    today: date
    date_from: date
    date_to: date
    total: int
    truncated: bool
    cinemas: list[CinemaSchedule]


def _day_sessions(sessions: Iterable[Row]) -> list[DaySessions]:
    """The sessions day by day, each day with its known times in order."""
    times = defaultdict(list)
    for session in sessions:
        times[session.date].extend([session.time] if session.time else [])
    return [DaySessions(date=day, times=sorted(times[day])) for day in sorted(times)]


def _first_session(sessions: Iterable[Row]) -> tuple[date, str]:
    return min((session.date, session.time or "") for session in sessions)


def _schedule_pairs(sessions: Iterable[Row]) -> list[tuple[Cinema, Movie, list[Row]]]:
    """One entry per cinema and movie showing there: cinemas by name, a
    cinema's movies by their first session."""
    by_pair = defaultdict(list)
    for session in sessions:
        by_pair[session.cinema_id, session.movie_id].append(session)
    movies = {
        movie.id: movie
        for movie in catalog.movies_by_ids({movie_id for _, movie_id in by_pair})
    }
    cinemas = list(enumerate(get_all_cinemas()))
    position = {cinema.id: index for index, cinema in cinemas}
    by_id = {cinema.id: cinema for _, cinema in cinemas}

    def order(pair):
        (cinema_id, movie_id), pair_sessions = pair
        return (
            position[cinema_id],
            _first_session(pair_sessions),
            normalize(movies[movie_id].title),
            movie_id,
        )

    return [
        (by_id[cinema_id], movies[movie_id], pair_sessions)
        for (cinema_id, movie_id), pair_sessions in sorted(by_pair.items(), key=order)
    ]


def _scheduled_movie(movie: Movie, sessions: list[Row]) -> ScheduledMovie:
    return ScheduledMovie(
        movie_id=movie.id,
        title=movie.title,
        directors=_names(movie.directors),
        genres=_names(movie.genres),
        url=_movie_url(movie),
        sessions=_day_sessions(sessions),
    )


def _cinema_schedules(
    pairs: Iterable[tuple[Cinema, Movie, list[Row]]],
) -> list[CinemaSchedule]:
    schedules: dict[int, CinemaSchedule] = {}
    for cinema, movie, sessions in pairs:
        schedule = schedules.setdefault(
            cinema.id, CinemaSchedule(slug=cinema.slug, name=cinema.name, movies=[])
        )
        schedule.movies.append(_scheduled_movie(movie, sessions))
    return list(schedules.values())


def get_schedule(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    cinema: Optional[str] = None,
) -> Schedule:
    """What each cinema shows, day by day, from `date_from` (today when
    absent) to `date_to` (`date_from` when absent): at most
    SCHEDULE_MAX_DAYS days and SCHEDULE_MAX_PAIRS cinema × movie pairs."""
    day = today()
    start = _optional_date(date_from) or day
    end = _optional_date(date_to) or start
    _check_order(start, end)
    days = (end - start).days + 1
    if days > SCHEDULE_MAX_DAYS:
        raise CatalogToolError(
            f"Período longo demais: get_schedule aceita no máximo "
            f"{SCHEDULE_MAX_DAYS} dias e foram pedidos {days}. Para períodos "
            "maiores, use search_movies com shown_from e shown_to."
        )
    cinema_id = resolve_cinema(cinema).id if _given(cinema) else None
    pairs = _schedule_pairs(catalog.session_dates(cinema_id, start, end))
    kept = pairs[:SCHEDULE_MAX_PAIRS]
    return Schedule(
        today=day,
        date_from=start,
        date_to=end,
        total=len(pairs),
        truncated=len(pairs) > len(kept),
        cinemas=_cinema_schedules(kept),
    )


class CinemaInfo(BaseModel):
    slug: str
    name: str
    short_name: str
    address: Optional[str]
    opening_hours: Optional[str]
    website: str
    instagram_url: Optional[str]
    page_url: str


class CinemaList(BaseModel):
    today: date
    catalog_since: Optional[date]
    catalog_until: Optional[date]
    metadata_coverage: MetadataCoverage
    cinemas: list[CinemaInfo]


def list_cinemas() -> CinemaList:
    """The cinemas, by name, with today's date and what the catalog covers."""
    since, until = catalog_period()
    return CinemaList(
        today=today(),
        catalog_since=since,
        catalog_until=until,
        metadata_coverage=metadata_coverage(),
        cinemas=[
            CinemaInfo(
                slug=cinema.slug,
                name=cinema.name,
                short_name=cinema.short_name,
                address=cinema.address,
                opening_hours=cinema.opening_hours,
                website=cinema.url,
                instagram_url=cinema.instagram_url,
                page_url=f"{CANONICAL_BASE_URL}/cinemas/{cinema.slug}",
            )
            for cinema in get_all_cinemas()
        ],
    )


MOVIE_DESCRIPTION_MAX_CHARS = 1500
MOVIE_UPCOMING_MAX_DATES = 30


class MovieScreening(BaseModel):
    cinema: str
    cinema_name: str
    description: str
    source_url: Optional[str]
    upcoming: list[DaySessions]
    upcoming_total: int
    past_first: Optional[date]
    past_last: Optional[date]
    past_count: int


class MovieDetails(BaseModel):
    today: date
    movie_id: int
    title: str
    original_title: Optional[str]
    release_year: Optional[int]
    original_language: Optional[str]
    directors: list[str]
    genres: list[str]
    countries: list[str]
    url: Optional[str]
    screenings: list[MovieScreening]


def _movie_screening(screening: Screening, day: date) -> MovieScreening:
    upcoming = _day_sessions(d for d in screening.dates if d.date >= day)
    past = sorted({d.date for d in screening.dates if d.date < day})
    return MovieScreening(
        cinema=screening.cinema.slug,
        cinema_name=screening.cinema.name,
        description=screening.description[:MOVIE_DESCRIPTION_MAX_CHARS],
        source_url=screening.url,
        upcoming=upcoming[:MOVIE_UPCOMING_MAX_DATES],
        upcoming_total=len(upcoming),
        past_first=past[0] if past else None,
        past_last=past[-1] if past else None,
        past_count=len(past),
    )


def get_movie(movie_id: int) -> MovieDetails:
    """One movie and each of its published screenings: the cinema's own
    description, the dates still ahead and a summary of the past ones."""
    screenings = catalog.published_screenings(movie_id)
    if not screenings:
        raise CatalogToolError(f"Filme {movie_id} não encontrado.")
    day = today()
    (movie,) = catalog.movies_by_ids([movie_id])
    return MovieDetails(
        today=day,
        movie_id=movie.id,
        title=movie.title,
        original_title=movie.original_title,
        release_year=movie.release_year,
        original_language=movie.original_language,
        directors=_names(movie.directors),
        genres=_names(movie.genres),
        countries=_names(movie.countries),
        url=_movie_url(movie),
        screenings=[_movie_screening(screening, day) for screening in screenings],
    )


SEARCH_DIRECTORS_MAX = 30
DIRECTOR_SAMPLE_TITLES = 3


class DirectorSummary(BaseModel):
    name: str
    movie_count: int
    sample_titles: list[str]


class DirectorSearchResult(BaseModel):
    total: int
    truncated: bool
    directors: list[DirectorSummary]


def _director_summary(name: str, movies: list[Movie], last_date: dict[int, date]):
    latest_first = sorted(
        movies, key=lambda movie: (-last_date[movie.id].toordinal(), movie.id)
    )
    return DirectorSummary(
        name=name,
        movie_count=len(movies),
        sample_titles=[movie.title for movie in latest_first[:DIRECTOR_SAMPLE_TITLES]],
    )


def search_directors(query: str, limit: int = 10) -> DirectorSearchResult:
    """The directors whose name contains `query`, among those with a movie
    in a published screening: the ones with the most movies first."""
    if not _given(query):
        raise CatalogToolError("Informe em 'query' um trecho do nome do diretor.")
    sessions = _by_movie(catalog.session_dates())
    last_date = {
        movie_id: max(session.date for session in movie_sessions)
        for movie_id, movie_sessions in sessions.items()
    }
    filmographies = defaultdict(list)
    for movie in catalog.movies_by_ids(sessions):
        for director in movie.directors:
            if _contains(query, [director.name]):
                filmographies[director.id, director.name].append(movie)
    found = sorted(
        (
            _director_summary(name, movies, last_date)
            for (_, name), movies in filmographies.items()
        ),
        key=lambda director: (-director.movie_count, normalize(director.name)),
    )
    kept = found[: _clamp(limit, SEARCH_DIRECTORS_MAX)]
    return DirectorSearchResult(
        total=len(found), truncated=len(found) > len(kept), directors=kept
    )


CATALOG_STATS_MAX = 50

StatsGroupBy = Literal["genre", "director", "country", "cinema", "month"]


class StatsGroup(BaseModel):
    key: str
    movies: int
    sessions: int


class CatalogStats(BaseModel):
    group_by: StatsGroupBy
    total_groups: int
    truncated: bool
    movies_in_scope: int
    movies_without_value: Optional[int]
    groups: list[StatsGroup]


# The metadata a movie may lack, by the group_by that counts it.
_MOVIE_VALUES: dict[str, Callable[[Movie], list[str]]] = {
    "genre": lambda movie: _names(movie.genres),
    "director": lambda movie: _names(movie.directors),
    "country": lambda movie: _names(movie.countries),
}


def _session_keys(group_by: str, slugs: dict[int, str]) -> Callable[[Movie, Row], set]:
    """The groups one session date of a movie counts in."""
    if group_by == "cinema":
        return lambda _movie, session: {slugs[session.cinema_id]}
    if group_by == "month":
        return lambda _movie, session: {session.date.strftime("%Y-%m")}
    return lambda movie, _session: set(_MOVIE_VALUES[group_by](movie))


def _stats_groups(
    sessions: Iterable[Row], movies: dict[int, Movie], keys_of
) -> list[StatsGroup]:
    movie_ids = defaultdict(set)
    session_count = defaultdict(int)
    for session in sessions:
        for key in keys_of(movies[session.movie_id], session):
            movie_ids[key].add(session.movie_id)
            session_count[key] += 1
    return [
        StatsGroup(key=key, movies=len(movie_ids[key]), sessions=session_count[key])
        for key in movie_ids
    ]


def _without_value(group_by: str, movies: Iterable[Movie]) -> Optional[int]:
    values_of = _MOVIE_VALUES.get(group_by)
    if values_of is None:
        return None
    return sum(not values_of(movie) for movie in movies)


def _stats_order(group_by: str) -> Callable[[StatsGroup], tuple]:
    if group_by == "month":
        return lambda group: (group.key,)
    return lambda group: (-group.movies, group.key)


def get_catalog_stats(
    group_by: StatsGroupBy,
    cinema: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 10,
) -> CatalogStats:
    """How many distinct movies and session dates each genre, director,
    country, cinema or month has, counting only the session dates of
    `cinema`, when given, inside the period, when given."""
    sessions = _sessions_in_scope(cinema, date_from, date_to)
    movies = {
        movie.id: movie
        for movie in catalog.movies_by_ids({session.movie_id for session in sessions})
    }
    found = sorted(
        _stats_groups(sessions, movies, _session_keys(group_by, _cinema_slugs())),
        key=_stats_order(group_by),
    )
    kept = found[: _clamp(limit, CATALOG_STATS_MAX)]
    return CatalogStats(
        group_by=group_by,
        total_groups=len(found),
        truncated=len(found) > len(kept),
        movies_in_scope=len(movies),
        movies_without_value=_without_value(group_by, movies.values()),
        groups=kept,
    )
