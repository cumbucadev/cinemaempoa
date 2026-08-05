from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, relationship

from flask_backend.constants import (
    CINEMA_COLORS,
    CINEMA_SHORT_NAMES,
    DEFAULT_CINEMA_COLOR,
)
from flask_backend.db import Base

# Ordered list of sources the poster pipeline will try.
# The pipeline tries each source in order and records the result.
POSTER_SOURCES = ["tmdb", "imdb"]

PIPELINE_RUN_STATUSES = ["running", "success", "warning", "error"]

ALERT_ACTIONS = ["posted", "dismissed"]

MOVIE_INSPECTION_STATUSES = ["consistent", "fixed", "needs_review", "error", "reverted"]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(20), unique=True, nullable=False)
    password = Column(String, nullable=False)


movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id"), primary_key=True),
)

movie_directors = Table(
    "movie_directors",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id"), primary_key=True),
    Column("director_id", Integer, ForeignKey("directors.id"), primary_key=True),
)

movie_countries = Table(
    "movie_countries",
    Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id"), primary_key=True),
    Column("country_id", Integer, ForeignKey("countries.id"), primary_key=True),
)


class Genre(Base):
    __tablename__ = "genres"

    id = Column(Integer, primary_key=True)
    tmdb_id = Column(Integer, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True)
    iso_3166_1 = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)


class Collection(Base):
    """A TMDB "collection" (franchise), e.g. "Bacurau Collection".

    Used to detect sequels/prequels deterministically: two movies sharing a
    collection_id have already been established by TMDB as being part of
    the same franchise."""

    __tablename__ = "collections"

    id = Column(Integer, primary_key=True)
    tmdb_id = Column(Integer, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)


class Director(Base):
    __tablename__ = "directors"

    id = Column(Integer, primary_key=True)
    tmdb_id = Column(Integer, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)

    movies: Mapped[List["Movie"]] = relationship(
        secondary=movie_directors, back_populates="directors"
    )


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=True, index=True)
    original_title = Column(String, nullable=True)
    release_year = Column(Integer, nullable=True)
    original_language = Column(String, nullable=True)  # ISO 639-1, e.g. "pt"
    tmdb_id = Column(Integer, nullable=True, index=True)
    tmdb_excluded = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    collection_id = Column(
        Integer, ForeignKey("collections.id"), nullable=True, index=True
    )
    # Set when this movie was created by a tracked pipeline run (e.g.
    # import-json). NULL for movies created manually via /admin or by
    # scripts/dedupper.py.
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    screenings: Mapped[List["Screening"]] = relationship(back_populates="movie")
    genres: Mapped[List["Genre"]] = relationship(secondary=movie_genres)
    directors: Mapped[List["Director"]] = relationship(
        secondary=movie_directors, back_populates="movies"
    )
    countries: Mapped[List["Country"]] = relationship(secondary=movie_countries)
    collection: Mapped[Optional["Collection"]] = relationship()


class Cinema(Base):
    __tablename__ = "cinemas"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    address = Column(String, nullable=True)
    opening_hours = Column(Text, nullable=True)
    instagram_url = Column(String, nullable=True)
    map_embed_url = Column(String, nullable=True)
    photo = Column(String, nullable=True)
    photo_width = Column(Integer, nullable=True)
    photo_height = Column(Integer, nullable=True)

    @property
    def short_name(self) -> str:
        return CINEMA_SHORT_NAMES.get(self.slug, self.name)

    @property
    def color(self) -> str:
        return CINEMA_COLORS.get(self.slug, DEFAULT_CINEMA_COLOR)


class Screening(Base):
    __tablename__ = "screenings"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    cinema_id = Column(Integer, ForeignKey("cinemas.id"), nullable=False)
    url = Column(String, nullable=True)
    # TODO: should image and description belong to the movie?
    image = Column(String, nullable=True)
    image_alt = Column(String, nullable=True)
    description = Column(String, nullable=False)
    # TODO: maybe change this to a _status_ enum?
    draft = Column(Boolean, nullable=False, default=False)

    # TODO: maybe keep image related properties in a separate "medias" table?
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.now)
    # Title as scraped, before title_cleaning.clean_title() strips known
    # annotations (festival/strand prefixes, "+ debate" suffixes, etc).
    raw_title = Column(String, nullable=True)
    # Comma-joined title_cleaning.TitleCleaningRule names matched across all
    # imports seen for this screening (union, never shrinks). Used by the
    # alert pipeline to detect "Mostra"/"Sessão comentada" screenings.
    title_cleaning_rules = Column(String, nullable=True)
    # Set when this screening was created by a tracked pipeline run (e.g.
    # import-json). NULL for screenings created manually via /admin or by
    # scripts/dedupper.py.
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    movie: Mapped["Movie"] = relationship(back_populates="screenings")
    cinema: Mapped["Cinema"] = relationship()
    dates: Mapped[List["ScreeningDate"]] = relationship(back_populates="screening")


class ScreeningDate(Base):
    __tablename__ = "screening_dates"

    id = Column(Integer, primary_key=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(String, nullable=True)

    screening: Mapped["Screening"] = relationship(back_populates="dates")


class WantToWatch(Base):
    """One row per (movie, anonymous visitor) mark on the reels homepage's
    want-to-watch star. visitor_id is an opaque UUID from a dedicated
    cookie (flask_backend/utils/visitor.py) - not tied to Screening, so a
    mark survives across cinemas and past a specific showtime's dates."""

    __tablename__ = "want_to_watch"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    visitor_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (UniqueConstraint("movie_id", "visitor_id"),)

    movie: Mapped["Movie"] = relationship()


class PipelineRun(Base):
    """One row per invocation of a tracked pipeline CLI command (import-json,
    fetch-posters, fetch-movie-metadata). Powers the
    /admin/pipelines health dashboard and lets a specific run's output be
    looked up exactly via the pipeline_run_id columns on Screening,
    MovieMetadataFetchAttempt and PosterFetchAttempt, instead of guessing
    from timestamps."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)
    # e.g. "import-json", "fetch-posters", "fetch-movie-metadata"
    # - the flask CLI command name.
    pipeline_name = Column(String, nullable=False, index=True)
    # For "import-json" only: the sorted, comma-joined cinema slugs targeted
    # by this invocation (e.g. "capitolio,paulo-amorim,sala-redencao"),
    # since the same CLI command covers cinema groups that run on very
    # different schedules. NULL for the other three pipelines, and also
    # NULL for import-json runs that failed before the JSON could be
    # parsed (the cinema slugs aren't known yet at that point).
    source = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False)  # see PIPELINE_RUN_STATUSES
    # JSON-encoded result counts (e.g. {"processed": 5, "errors": 1}).
    summary = Column(Text, nullable=True)
    error_message = Column(String, nullable=True)


class PosterFetchAttempt(Base):
    """Tracks each attempt to fetch a poster for a screening from an external source.

    A screening that has failed attempts for every source in POSTER_SOURCES
    (and still has no image) is considered as needing manual review.
    """

    __tablename__ = "poster_fetch_attempts"

    id = Column(Integer, primary_key=True)
    screening_id = Column(Integer, ForeignKey("screenings.id"), nullable=False)
    source = Column(String, nullable=False)  # e.g. "tmdb", "imdb"
    status = Column(String, nullable=False)  # "success", "not_found", "error"
    attempted_at = Column(DateTime, nullable=False)
    error_message = Column(String, nullable=True)
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    screening: Mapped["Screening"] = relationship()


class MovieMetadataFetchAttempt(Base):
    """Tracks each attempt to fetch metadata (director, genres) for a movie
    from TMDB.

    A movie that has a failed attempt and is still not linked to a TMDB
    entry is considered as needing manual review.
    """

    __tablename__ = "movie_metadata_fetch_attempts"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    source = Column(String, nullable=False)  # e.g. "tmdb"
    status = Column(String, nullable=False)  # "success", "not_found", "error"
    attempted_at = Column(DateTime, nullable=False)
    error_message = Column(String, nullable=True)
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )

    movie: Mapped["Movie"] = relationship()


class MovieInspection(Base):
    """One audit row per automated consistency check of a movie's TMDB
    match against what the cinema itself published about it (see
    flask_backend/service/movie_inspector.py). Append-only: reverting a
    "fixed" row creates a new row with status="reverted" instead of
    mutating history - same log-not-mutate shape as AlertAction."""

    __tablename__ = "movie_inspections"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    status = Column(String, nullable=False)  # see MOVIE_INSPECTION_STATUSES
    reasoning = Column(Text, nullable=False)
    # The movie's tmdb_id as of just before this check ran - never the
    # replacement id a "fixed" outcome of this same check applied.
    checked_tmdb_id = Column(Integer, nullable=True)
    previous_snapshot = Column(Text, nullable=True)
    new_snapshot = Column(Text, nullable=True)
    pipeline_run_id = Column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=True, index=True
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    movie: Mapped["Movie"] = relationship()


class AlertAction(Base):
    """One posted/dismissed action taken on a Screening from /admin/alerts
    (issue #258). Append-only log - a screening can accumulate several rows
    over its run (e.g. posted once, resurfaces via `remind_at`, dismissed
    later), which is what gives the admin a real posting history instead of
    a single mutable status. Replaces the Alert model."""

    __tablename__ = "alert_actions"

    id = Column(Integer, primary_key=True)
    screening_id = Column(
        Integer, ForeignKey("screenings.id"), nullable=False, index=True
    )
    action = Column(String, nullable=False, index=True)
    # If set, this screening is excluded from Pendentes until this date
    # arrives (see flask_backend/service/screening_alerts.py). NULL means
    # excluded indefinitely.
    remind_at = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    screening: Mapped["Screening"] = relationship()
    created_by: Mapped[Optional["User"]] = relationship()


class GeminiUsageEvent(Base):
    """One row per model actually attempted inside
    gemini_models.call_with_fallback, whether it succeeded or was
    rate-limited. Backs the proactive RPM/RPD pre-check and the reactive
    cooldown in flask_backend/service/gemini_quota.py.

    occurred_at is stored as naive UTC (not this codebase's usual naive
    server-local convention) because the requests-per-day window has to
    line up with Google's actual daily quota reset, which is anchored to
    Pacific time, not server local time."""

    __tablename__ = "gemini_usage_events"

    id = Column(Integer, primary_key=True)
    model_id = Column(String, nullable=False, index=True)
    occurred_at = Column(DateTime, nullable=False, index=True)
    outcome = Column(String, nullable=False)
    quota_metric = Column(String, nullable=True)
    unavailable_until = Column(DateTime, nullable=True)


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=True, index=True)
    content = Column(Text, nullable=False)
    excerpt = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    published = Column(Boolean, nullable=False, default=False)
    featured_image = Column(String, nullable=True)
    featured_image_alt = Column(String, nullable=True)

    author: Mapped["User"] = relationship()
