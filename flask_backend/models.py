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
)
from sqlalchemy.orm import Mapped, relationship

from flask_backend.db import Base

# Ordered list of sources the poster pipeline will try.
# The pipeline tries each source in order and records the result.
POSTER_SOURCES = ["tmdb", "imdb"]

# Ordered list of sources the movie metadata pipeline will try.
MOVIE_METADATA_SOURCES = ["tmdb"]

# Rules evaluated by the alert pipeline (flask_backend/service/alert_rules.py).
ALERT_RULE_NAMES = [
    "new_movie",
    "single_screening",
    "sessao_comentada",
    "mostra",
    "director_debut",
    "returning_director",
    "new_genre_combination",
    "sequel_or_franchise",
]

ALERT_STATUSES = ["pending", "posted", "dismissed"]


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
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    # Set once the alert pipeline's director/genre/collection rules have
    # been evaluated for this movie. NULL means "still due" - see
    # flask_backend/service/alert_pipeline.py.
    metadata_alerts_evaluated_at = Column(DateTime, nullable=True, index=True)
    collection_id = Column(
        Integer, ForeignKey("collections.id"), nullable=True, index=True
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
    # Set once the alert pipeline's core rules have been evaluated for this
    # screening. NULL means "still due" - see
    # flask_backend/service/alert_pipeline.py.
    core_alerts_evaluated_at = Column(DateTime, nullable=True, index=True)

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

    screening: Mapped["Screening"] = relationship()


class MovieMetadataFetchAttempt(Base):
    """Tracks each attempt to fetch metadata (director, genres) for a movie
    from an external source.

    A movie that has failed attempts for every source in MOVIE_METADATA_SOURCES
    is considered as needing manual review.
    """

    __tablename__ = "movie_metadata_fetch_attempts"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    source = Column(String, nullable=False)  # e.g. "tmdb"
    status = Column(String, nullable=False)  # "success", "not_found", "error"
    attempted_at = Column(DateTime, nullable=False)
    error_message = Column(String, nullable=True)

    movie: Mapped["Movie"] = relationship()


class Alert(Base):
    """A candidate social-media post generated by the alert pipeline
    (flask_backend/service/alert_pipeline.py) for an "interesting movie"
    detected in the schedule (new movie, single screening, sessão
    comentada, mostra, director debut/return, new genre combo,
    sequel/franchise). Reviewed and actioned from /admin/alerts."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    rule_name = Column(String, nullable=False, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False, index=True)
    # Only populated for screening-scoped rules (new_movie, single_screening,
    # sessao_comentada, mostra); NULL for movie-scoped rules.
    screening_id = Column(
        Integer, ForeignKey("screenings.id"), nullable=True, index=True
    )
    # Idempotency key, e.g. "new_movie:42", "single_screening:107". Enforced
    # unique so a rule can never fire twice for the same subject.
    dedup_key = Column(String, nullable=False, unique=True, index=True)
    drafted_text = Column(Text, nullable=False)
    # Optional JSON blob with rule-specific detail, for debugging.
    context = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    movie: Mapped["Movie"] = relationship()
    screening: Mapped[Optional["Screening"]] = relationship()
    resolved_by: Mapped[Optional["User"]] = relationship()


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
